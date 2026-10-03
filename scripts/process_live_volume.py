"""Process one newly acquired Level-II volume into live object state.

This bridge remains probability-free until trained predictors and leakage-safe
labels exist. All time-evolving diagnostics use only the current scan and
state retained from earlier scans.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from math import asin, atan2, cos, degrees, radians, sin, sqrt

import numpy as np

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.object_detector import detect_reflectivity_objects
from processing.object_tracker import CentroidTracker
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep
from processing.radar_storm_motion import attach_radar_storm_motion
from processing.radar_features import object_field_summary, velocity_object_summary
from processing.vertical_structure import summarize_vertical_structure
from acquisition.rap_environment import acquire_for_radar_time
from processing.rap_features import extract_features
from processing.radar_sites import apply_radar_origin, radar_origin_for_site
from scripts.live_model_features import build_live_feature_frame
from scripts.model_runtime import ModelRuntime


def object_geometry(mask, lat, lon, spacing_km=1.0):
    from shapely.geometry import MultiPoint

    yy, xx = np.where(mask)
    if len(xx) < 3:
        return None, float(len(xx) * spacing_km**2)

    points = [(float(lon[y, x]), float(lat[y, x])) for y, x in zip(yy, xx)]
    hull = MultiPoint(points).convex_hull
    if hull.is_empty:
        return None, float(len(xx) * spacing_km**2)

    # The live-product contract is GeoJSON Polygon. Thin/degenerate footprints
    # can otherwise yield a Point or LineString.
    if hull.geom_type != "Polygon":
        center = hull.centroid
        radius_deg = max(0.0025, float(spacing_km) / 111.0 / 2.0)
        hull = center.buffer(radius_deg, resolution=8)

    return hull.__geo_interface__, float(len(xx) * spacing_km**2)


def object_shape_metrics(rows, cols, lat, lon, spacing_km=1.0):
    """Estimate object major/minor axes and orientation from the footprint.

    The calculation is local-grid/PCA based and is intended as a deterministic
    radar diagnostic, not a geodesic shape retrieval.
    """
    if len(rows) < 3:
        return None, None, None

    xy = np.column_stack((cols.astype(float), rows.astype(float)))
    centered = xy - xy.mean(axis=0)
    cov = np.cov(centered, rowvar=False)
    if cov.shape != (2, 2) or not np.all(np.isfinite(cov)):
        return None, None, None

    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[order], 0.0)
    major = 4.0 * sqrt(float(eigenvalues[0])) * spacing_km
    minor = 4.0 * sqrt(float(eigenvalues[1])) * spacing_km

    vec = eigenvectors[:, order[0]]
    angle_deg = (degrees(atan2(float(vec[0]), float(vec[1]))) + 180.0) % 180.0
    return major, minor, angle_deg


def motion_from_positions(previous, current_lat, current_lon, current_time):
    if not previous or current_lat is None or current_lon is None:
        return None, None
    try:
        previous_time = datetime.fromisoformat(previous["timestamp"].replace("Z", "+00:00"))
        current_dt = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
        dt_hours = (current_dt - previous_time).total_seconds() / 3600.0
        if dt_hours <= 0:
            return None, None

        lat1 = radians(previous["lat"])
        lat2 = radians(current_lat)
        dlat = lat2 - lat1
        dlon = radians(current_lon - previous["lon"])
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        distance_km = 6371.0088 * 2 * asin(sqrt(a))
        speed_kt = distance_km / dt_hours / 1.852

        y = sin(dlon) * cos(lat2)
        x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
        direction = (degrees(atan2(y, x)) + 360.0) % 360.0
        return speed_kt, direction
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, None


def load_state(path: Path):
    if not path.exists():
        return {}, CentroidTracker()

    state = json.loads(path.read_text(encoding="utf-8"))
    tracker = CentroidTracker.from_state(state.get("tracker"))
    return state, tracker



def _json_safe(value):
    """Convert non-finite numeric values to JSON null recursively."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value

def radar_motion_cache_path(state_path: Path) -> Path:
    return state_path.with_name(state_path.stem + ".previous_reflectivity.npz")

def load_previous_radar_field(state_path: Path):
    cache = radar_motion_cache_path(state_path)
    if not cache.exists():
        return None, None
    try:
        with np.load(cache, allow_pickle=False) as data:
            field = np.asarray(data["reflectivity"], dtype=np.float32)
            raw = data["timestamp"]
            timestamp = str(raw.item() if hasattr(raw, "item") else raw)
        return field, timestamp
    except (OSError, KeyError, ValueError, TypeError):
        return None, None

def save_previous_radar_field(state_path: Path, field, timestamp: str):
    cache = radar_motion_cache_path(state_path)
    tmp = cache.with_suffix(cache.suffix + ".tmp")
    with tmp.open("wb") as handle:
        np.savez_compressed(handle, reflectivity=np.asarray(field, dtype=np.float32), timestamp=np.asarray(timestamp))
    tmp.replace(cache)

def save_state(path: Path, state: dict, tracker: CentroidTracker):
    path.parent.mkdir(parents=True, exist_ok=True)
    state["tracker"] = tracker.to_state()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)




def history_rows_as_of(rows, as_of_timestamp: str):
    """Return only history rows available at the current scan time."""
    try:
        cutoff = datetime.fromisoformat(str(as_of_timestamp).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return []

    filtered = []
    for row in rows or []:
        try:
            timestamp = datetime.fromisoformat(str(row.get("timestamp")).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if timestamp <= cutoff:
            filtered.append(row)
    filtered.sort(key=lambda row: str(row.get("timestamp", "")))
    return filtered


def score_with_runtime(frame, runtime: ModelRuntime, research_replay: bool = False):
    """Score a frame using the live release gate or an explicit replay override.

    Candidate models are scoreable only when research_replay is explicitly true.
    Ordinary/live execution remains release-gated.
    """
    if runtime.model is None:
        return None, "no_model"
    if runtime.enabled:
        return runtime.score(frame), "released"
    if research_replay:
        return runtime.score_candidate(frame), "research_replay"
    return None, "candidate_blocked"

def process_volume(
    path: Path,
    state_path: Path,
    output_path: Path,
    history_jsonl_path: Path | None = None,
    history_csv_path: Path | None = None,
    model_dir: Path | None = None,
    research_replay: bool = False,
):
    state, tracker = load_state(state_path)
    source_name = path.name

    processed = set(state.get("processed_sources", []))
    if source_name in processed:
        print(f"SKIP already processed: {source_name}")
        return False

    radar = read_level2(path)
    preliminary_meta = volume_metadata(radar, path)
    radar_site = preliminary_meta.get("radar_id")
    if not radar_site:
        for candidate in path.parts:
            if len(candidate) == 4 and candidate.upper().isalnum():
                radar_site = candidate.upper()
                break

    if state.get("radar_site") and state["radar_site"] != radar_site:
        raise RuntimeError(f"Tracker state belongs to {state['radar_site']}, not {radar_site}")

    radar_origin = radar_origin_for_site(radar_site)
    if radar_origin is not None:
        apply_radar_origin(radar, radar_origin)

    radar_fields = resolve_fields(radar)
    reflectivity = radar_fields.get("reflectivity")
    if reflectivity is None:
        raise RuntimeError("No reflectivity field found in Level-II volume")

    available_fields = [name for name in radar_fields.values() if name]
    grid = grid_lowest_sweep(
        radar,
        available_fields,
        grid_size_km=180.0,
        spacing_km=1.0,
    )
    data = grid_field_2d(grid, reflectivity)
    lat, lon = grid_latlon(grid)
    gridded = {
        canonical: grid_field_2d(grid, actual)
        for canonical, actual in radar_fields.items()
        if actual and actual in (getattr(grid, "fields", {}) or {})
    }
    field_gradients = {}
    for canonical in ("zdr", "velocity"):
        field = gridded.get(canonical)
        if field is None:
            continue
        field_gradients[canonical] = np.hypot(
            *np.gradient(field, 1.0, edge_order=1)
        )

    detections = detect_reflectivity_objects(data)
    metadata = volume_metadata(radar, path)
    metadata["radar_origin"] = list(radar_origin) if radar_origin is not None else None
    raw_timestamp = metadata["scan_time_utc"]

    if not raw_timestamp:
        raise RuntimeError("Unable to determine radar scan time")

    radar_dt = datetime.fromisoformat(
        str(raw_timestamp).replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    timestamp = radar_dt.isoformat().replace("+00:00", "Z")
    rap_result = None
    try:
        rap_result = acquire_for_radar_time(radar_dt)
    except Exception as exc:
        print(f"RAP acquisition warning: {type(exc).__name__}: {exc}")

    previous_reflectivity, previous_radar_time = load_previous_radar_field(state_path)
    radar_motion = None
    if previous_reflectivity is not None and previous_radar_time is not None:
        try:
            previous_dt = (radar_dt - datetime.fromisoformat(previous_radar_time.replace("Z", "+00:00")).astimezone(timezone.utc)).total_seconds() / 60.0
            radar_motion = attach_radar_storm_motion(previous_reflectivity, data, previous_dt, spacing_km=1.0)
        except (TypeError, ValueError, OverflowError):
            radar_motion = None

    tracked = tracker.update(timestamp, detections, radar_motion=radar_motion)
    save_previous_radar_field(state_path, data, timestamp)
    features = []
    current_positions = {}
    previous_positions = state.get("object_positions", {})
    previous_metrics = state.get("object_metrics", {})

    for obj in tracked:
        rows = np.asarray(obj.get("row_indices", []), dtype=int)
        cols = np.asarray(obj.get("column_indices", []), dtype=int)
        footprint = np.zeros_like(data, dtype=bool)
        valid = (
            (rows >= 0) & (rows < data.shape[0]) &
            (cols >= 0) & (cols < data.shape[1])
        )
        footprint[rows[valid], cols[valid]] = True

        geometry, area_km2 = object_geometry(footprint, lat, lon)
        major_km, minor_km, orientation_deg = object_shape_metrics(
            rows[valid], cols[valid], lat, lon
        )

        cy = int(round(obj["row_centroid"]))
        cx = int(round(obj["column_centroid"]))
        centroid_lat = float(lat[cy, cx]) if 0 <= cy < lat.shape[0] and 0 <= cx < lat.shape[1] else None
        centroid_lon = float(lon[cy, cx]) if 0 <= cy < lon.shape[0] and 0 <= cx < lon.shape[1] else None

        speed_kt, direction_deg = motion_from_positions(
            previous_positions.get(str(obj["object_id"])),
            centroid_lat,
            centroid_lon,
            timestamp,
        )

        track_key = str(obj["object_id"])
        previous = previous_metrics.get(track_key, {})
        max_z = float(obj["max_reflectivity_dbz"])
        mean_z = float(obj["mean_reflectivity_dbz"])
        previous_max_z = previous.get("max_reflectivity_dbz")
        previous_mean_z = previous.get("mean_reflectivity_dbz")
        previous_time = previous.get("timestamp")

        z_trend = None
        if previous_max_z is not None and previous_time:
            try:
                dt_hours = (
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    - datetime.fromisoformat(previous_time.replace("Z", "+00:00"))
                ).total_seconds() / 3600.0
                if dt_hours > 0:
                    z_trend = (max_z - float(previous_max_z)) / dt_hours
            except (TypeError, ValueError):
                z_trend = None

        area_growth = None
        previous_area = previous.get("area_km2")
        if previous_area is not None and previous_area > 0:
            area_growth = (area_km2 - float(previous_area)) / float(previous_area)

        age_scans = int(
            tracker.tracks.get(obj["object_id"]).age_scans
            if obj["object_id"] in tracker.tracks else 1
        )

        current_positions[track_key] = {
            "timestamp": timestamp,
            "lat": centroid_lat,
            "lon": centroid_lon,
        }
        state.setdefault("object_metrics", {})
        state["object_metrics"][track_key] = {
            "timestamp": timestamp,
            "max_reflectivity_dbz": max_z,
            "mean_reflectivity_dbz": mean_z,
            "area_km2": area_km2,
        }

        rich_radar = {}
        for canonical in ("zdr", "rhohv", "kdp", "velocity"):
            field = gridded.get(canonical)
            if field is None:
                continue
            values = field[footprint]
            finite = values[np.isfinite(values)]
            if canonical == "zdr":
                gradient = field_gradients.get("zdr")
                stats = object_field_summary(
                    finite, "zdr", gradient[footprint] if gradient is not None else None, "_dbkm"
                )
                rich_radar["zdr_mean_db"] = stats["zdr_mean"]
                rich_radar["zdr_p90_db"] = stats["zdr_p90"]
                rich_radar["zdr_gradient_dbkm"] = stats["zdr_gradient_dbkm"]
            elif canonical == "rhohv":
                stats = object_field_summary(finite, "rhohv")
                rich_radar["rhohv_mean"] = stats["rhohv_mean"]
                rich_radar["rhohv_max"] = stats["rhohv_max"]
                rich_radar["rhohv_p90"] = stats["rhohv_p90"]
                rich_radar["rhohv_min"] = float(np.nanmin(finite)) if finite.size else np.nan
            elif canonical == "kdp":
                stats = object_field_summary(finite, "kdp")
                rich_radar["kdp_mean_degkm"] = stats["kdp_mean"]
                rich_radar["kdp_p90_degkm"] = stats["kdp_p90"]
            elif canonical == "velocity":
                gradient = field_gradients.get("velocity")
                rich_radar.update(
                    velocity_object_summary(
                        finite, gradient[footprint] if gradient is not None else None
                    )
                )
        if centroid_lat is not None and centroid_lon is not None:
            try:
                rich_radar.update(
                    summarize_vertical_structure(
                        radar,
                        centroid_lat,
                        centroid_lon,
                        reflectivity,
                        radar_origin=radar_origin,
                    )
                )
            except Exception as exc:
                print(f"Vertical radar diagnostic warning: {type(exc).__name__}: {exc}")
        environment = {"status": "unavailable", "source": "RAP", "fields": {}}
        if rap_result is not None and centroid_lat is not None and centroid_lon is not None:
            rap_match, rap_path = rap_result
            try:
                environment = extract_features(
                    rap_path,
                    centroid_lat,
                    centroid_lon,
                    radar_dt,
                    expected_valid_time=rap_match.valid_time,
                )
            except Exception as exc:
                environment = {
                    "source": "RAP",
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "fields": {},
                }

        features.append({
            "track_id": track_key,
            "timestamp": timestamp,
            "radar_site": metadata.get("radar_id"),
            "geometry": geometry,
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "pixel_count": int(obj["pixel_count"]),
            "area_km2": area_km2,
            "length_km": major_km,
            "width_km": minor_km,
            "orientation_deg": orientation_deg,
            "aspect_ratio": (major_km / minor_km) if major_km is not None and minor_km and minor_km > 0 else None,
            "bbox_aspect_ratio": obj.get("bbox_aspect_ratio"),
            "object_mode": obj.get("object_mode"),
            "is_band": 1 if obj.get("object_mode") == "band" else 0,
            "reflectivity_gradient_p90_dbkm": obj.get("reflectivity_gradient_p90_dbkm"),
            "gradient_fraction_above_5dbkm": obj.get("gradient_fraction_above_5dbkm"),
            "background_reflectivity_dbz": obj.get("background_reflectivity_dbz"),
            "reflectivity_contrast_db": obj.get("reflectivity_contrast_db"),
            "max_reflectivity_dbz": max_z,
            "mean_reflectivity_dbz": mean_z,
            "core_pixel_count": int(obj["core_pixel_count"]),
            "touches_grid_edge": bool(obj.get("touches_grid_edge", False)),
            "core_fraction": float(obj["core_pixel_count"]) / max(1, int(obj["pixel_count"])),
            "track_association_status": obj.get("track_association_status"),
            "track_association_distance_px": obj.get("track_association_distance_px"),
            "track_association_gate_px": obj.get("track_association_gate_px"),
            "track_association_cost": obj.get("track_association_cost"),
            "track_age_scans": obj.get("track_age_scans"),
            "track_missed_scans": obj.get("track_missed_scans"),
            "track_competing_track_count": obj.get("track_competing_track_count"),
            "track_competing_object_count": obj.get("track_competing_object_count"),
            "track_merge_candidate": obj.get("track_merge_candidate"),
            "track_split_candidate": obj.get("track_split_candidate"),
            "echo_top_km": rich_radar.get("echo_top_km"),
            "top_minus_base_km": rich_radar.get("top_minus_base_km"),
            "vertical_reflectivity_gradient": rich_radar.get("vertical_reflectivity_gradient"),
            "vertical_valid_points": rich_radar.get("vertical_valid_points"),
            "zdr_mean_db": rich_radar.get("zdr_mean_db"),
            "zdr_p90_db": rich_radar.get("zdr_p90_db"),
            "zdr_gradient_dbkm": rich_radar.get("zdr_gradient_dbkm"),
            "rhohv_mean": rich_radar.get("rhohv_mean"),
            "rhohv_max": rich_radar.get("rhohv_max"),
            "rhohv_p90": rich_radar.get("rhohv_p90"),
            "rhohv_min": rich_radar.get("rhohv_min"),
            "kdp_mean_degkm": rich_radar.get("kdp_mean_degkm"),
            "kdp_p90_degkm": rich_radar.get("kdp_p90_degkm"),
            "velocity_mean_kt": rich_radar.get("velocity_mean_kt"),
            "velocity_std_kt": rich_radar.get("velocity_std_kt"),
            "velocity_p90_abs_kt": rich_radar.get("velocity_p90_abs_kt"),
            "velocity_gradient_ktkm": rich_radar.get("velocity_gradient_ktkm"),
            "motion_speed_kt": speed_kt,
            "motion_dir_deg": direction_deg,
            "motion_direction_deg": direction_deg,
            "radar_motion_speed_kt": obj.get("radar_motion_speed_kt"),
            "radar_motion_direction_deg": obj.get("radar_motion_direction_deg"),
            "radar_motion_u_kt": obj.get("radar_motion_u_kt"),
            "radar_motion_v_kt": obj.get("radar_motion_v_kt"),
            "radar_motion_confidence": obj.get("radar_motion_confidence"),
            "age_scans": age_scans,
            "reflectivity_trend_dbz_per_hr": z_trend,
            "area_growth_fraction": area_growth,
            "probability_15min": None,
            "probability_30min": None,
            "probability_45min": None,
            "probability_60min": None,
            "probability_trend": "unknown",
            "drivers": [],
            "environment_status": environment.get("status", "unavailable"),
            "environment": environment,
            "data_quality": "degraded" if obj.get("touches_grid_edge", False) else "good",
            "model_version": "live-object-foundation-v2",
        })

    # Optional learned-model scoring is deliberately opt-in and release-gated
    # for live execution. Archived replay may explicitly score candidate bundles.
    model_runtimes = (
        ModelRuntime.load_horizon_set(model_dir)
        if model_dir and any((Path(model_dir) / name).exists() for name in (
            "candidate_ensemble_refresh_15m", "candidate_ensemble_expansion_15m",
            "baseline_refresh_15m", "baseline_expansion_15m",
        ))
        else ({ModelRuntime.load(model_dir).horizon_minutes: ModelRuntime.load(model_dir)} if model_dir and ModelRuntime.load(model_dir).model is not None else {})
    )
    model_scored = False
    model_errors = {}
    probability_mode = "none"
    model_versions = {}
    if features and model_runtimes:
        prior_rows_by_track = {}
        prior_path = history_jsonl_path or Path("data/derived/live_object_history.jsonl")
        if prior_path.exists():
            try:
                for line in prior_path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                        prior_rows_by_track.setdefault(str(row.get("track_id")), []).append(row)
                    except json.JSONDecodeError:
                        continue
            except OSError:
                prior_rows_by_track = {}

        for horizon, runtime in model_runtimes.items():
            model_versions[str(horizon)] = runtime.metadata.get("model_version")
            for feature in features:
                track_id = str(feature.get("track_id"))
                current_row = dict(feature)
                env = current_row.get("environment") or {}
                environment_fields = env.get("fields") or {}
                current_row.update(environment_fields)
                history = history_rows_as_of(
                    prior_rows_by_track.get(track_id, []),
                    current_row.get("timestamp"),
                )
                frame = build_live_feature_frame(history + [current_row], track_id)
                try:
                    scores, score_mode = score_with_runtime(frame.tail(1), runtime, research_replay=research_replay)
                    if score_mode != "candidate_blocked":
                        probability_mode = score_mode
                    if scores is not None and scores:
                        feature[f"probability_{horizon}min"] = float(scores[0])
                        feature["probability_trend"] = "scored"
                        model_scored = True
                except Exception as exc:
                    model_errors[f"{track_id}:{horizon}"] = f"{type(exc).__name__}: {exc}"

    result = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": f.pop("geometry", None),
                "properties": f,
            }
            for f in features
        ],
        "metadata": {
            "scan_time_utc": timestamp,
            "source_file": source_name,
            "fields": radar_fields,
            "object_count": len(features),
            "probability_status": ("scored" if model_scored else ("model_error" if model_errors else "not_scored")),
            "probability_mode": probability_mode,
            "environment_status": (
                "attached" if rap_result is not None else "unavailable"
            ),
            "environment_source": "RAP",
            "radar_origin": list(radar_origin) if radar_origin is not None else None,
            "model_version": model_runtime.metadata.get("model_version") if model_runtime.model is not None else None,
            "model_target": model_runtime.metadata.get("target") if model_runtime.model is not None else None,
            "model_horizon_minutes": model_runtime.horizon_minutes if model_runtime.model is not None else None,
            "model_errors": model_errors,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_safe(result), indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(output_path)

    # Persist this scan as an object-timestep training record. The history
    # writer is append-only and de-duplicates by (timestamp, track_id).
    from scripts.append_live_object_history import append_history

    append_history(
        output_path,
        history_jsonl_path or Path("data/derived/live_object_history.jsonl"),
        history_csv_path or Path("data/derived/live_object_history.csv"),
    )

    processed.add(source_name)
    state["processed_sources"] = sorted(processed)[-500:]
    state["radar_site"] = radar_site
    state["last_scan_time_utc"] = timestamp
    state["last_source"] = source_name
    state["last_object_count"] = len(features)
    state["object_positions"] = current_positions
    state["updated_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state, tracker)

    print(f"Processed {source_name}: {len(features)} object(s)")
    print(f"Wrote {output_path}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--state", default="data/derived/live_tracker_state.json")
    parser.add_argument("--output", default="data/derived/live_objects.geojson")
    parser.add_argument("--history-jsonl", default=None)
    parser.add_argument("--history-csv", default=None)
    parser.add_argument("--model-dir", default=None, help="Optional released model bundle directory; candidate bundles remain disabled.")
    args = parser.parse_args()

    process_volume(
        Path(args.input),
        Path(args.state),
        Path(args.output),
        history_jsonl_path=Path(args.history_jsonl) if args.history_jsonl else None,
        history_csv_path=Path(args.history_csv) if args.history_csv else None,
        model_dir=Path(args.model_dir) if args.model_dir else None,
    )


if __name__ == "__main__":
    main()
