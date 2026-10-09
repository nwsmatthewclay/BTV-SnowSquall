"""Process one newly acquired Level-II volume into live object state.

Publishes transparent research-weighted 15/30/45/60 guidance while keeping
learned operational release models separately gated. All time-evolving
diagnostics use only the current scan and prior retained state.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from math import asin, atan2, cos, degrees, radians, sin, sqrt

import numpy as np

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.object_detector import ObjectDetectionConfig, detect_reflectivity_objects
from processing.object_tracker import CentroidTracker
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep, grid_lowest_available_sweep
from processing.radar_storm_motion import attach_radar_storm_motion
from processing.radar_features import object_field_summary, velocity_object_summary
from processing.vertical_structure import summarize_vertical_structure
from acquisition.rap_environment import acquire_for_radar_time, acquire_forecast_for_radar_time
from processing.rap_features import extract_features
from processing.radar_sites import apply_radar_origin, radar_origin_for_site
from scripts.live_model_features import build_live_feature_frame
from scripts.model_runtime import ModelRuntime
from snow_squall.environment_contract import assess_environment
from snow_squall.environment_risk import environment_risk_features

# RAP is hourly in live mode; allow one late/missing cycle without dropping the environmental score.
LIVE_ENV_MAX_AGE_MINUTES = 120.0


def object_geometry(mask, lat, lon, spacing_km=1.0):
    """Return a compact polygon tracing the detected radar-object mask.

    ProbSevere-style object identification is based on spatially segmented
    radar features, so the viewer should receive the feature footprint rather
    than a generic ellipse. Marching-squares contours preserve the actual
    watershed mask while avoiding hundreds of individual grid-cell polygons.
    """
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union
    from skimage.measure import find_contours

    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or not np.any(mask):
        return None, 0.0

    contours = find_contours(mask.astype(float), 0.5)
    if not contours:
        return None, float(np.sum(mask) * spacing_km**2)

    def grid_to_geo(contour):
        rows = np.asarray(contour[:, 0], dtype=float)
        cols = np.asarray(contour[:, 1], dtype=float)
        rows = np.clip(rows, 0, lat.shape[0] - 1.000001)
        cols = np.clip(cols, 0, lat.shape[1] - 1.000001)
        r0 = np.floor(rows).astype(int)
        c0 = np.floor(cols).astype(int)
        r1 = np.minimum(r0 + 1, lat.shape[0] - 1)
        c1 = np.minimum(c0 + 1, lat.shape[1] - 1)
        fr = rows - r0
        fc = cols - c0
        latv = (
            lat[r0, c0] * (1-fr) * (1-fc)
            + lat[r1, c0] * fr * (1-fc)
            + lat[r0, c1] * (1-fr) * fc
            + lat[r1, c1] * fr * fc
        )
        lonv = (
            lon[r0, c0] * (1-fr) * (1-fc)
            + lon[r1, c0] * fr * (1-fc)
            + lon[r0, c1] * (1-fr) * fc
            + lon[r1, c1] * fr * fc
        )
        finite = np.isfinite(latv) & np.isfinite(lonv)
        return np.column_stack((lonv[finite], latv[finite]))

    polygons = []
    for contour in contours:
        if len(contour) < 4:
            continue
        coords = grid_to_geo(contour)
        if len(coords) < 4:
            continue
        poly = Polygon(coords)
        if poly.is_empty or not poly.is_valid or poly.area <= 0:
            poly = poly.buffer(0)
        if not poly.is_empty and poly.area > 0:
            polygons.append(poly)

    if not polygons:
        return None, float(np.sum(mask) * spacing_km**2)

    # The largest contour is the radar-object exterior. Preserve interior
    # contours as holes only when they are genuinely contained by that exterior.
    outer = max(polygons, key=lambda p: p.area)
    holes = []
    for poly in polygons:
        if poly is outer:
            continue
        if outer.contains(poly.representative_point()):
            holes.append(list(poly.exterior.coords))
    if holes:
        outer = Polygon(list(outer.exterior.coords), holes=holes).buffer(0)

    # Remove pixel-scale staircase noise while preserving the meteorological
    # footprint. At 1-km gridding this is roughly a 0.1-km tolerance.
    tolerance = max(0.0005, float(spacing_km) / 111000.0 * 0.75)
    outer = outer.simplify(tolerance, preserve_topology=True).buffer(0)
    if outer.is_empty:
        return None, float(np.sum(mask) * spacing_km**2)

    return outer.__geo_interface__, float(np.sum(mask) * spacing_km**2)

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
    model_runtimes: dict[int, ModelRuntime] | None = None,
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

    # Keep the established reflectivity grid path for compatibility with
    # existing live test doubles, while independently selecting the lowest
    # valid sweep for every additional moment (especially base velocity).
    reflectivity_grid = grid_lowest_sweep(
        radar,
        [reflectivity],
        grid_size_km=180.0,
        spacing_km=1.0,
    )
    data = grid_field_2d(reflectivity_grid, reflectivity)
    lat, lon = grid_latlon(reflectivity_grid)

    # Grid each additional moment from its lowest valid sweep independently.
    # All moments use identical Cartesian geometry so they remain collocated.
    gridded = {"reflectivity": data}
    for canonical, actual in radar_fields.items():
        if not actual or canonical == "reflectivity":
            continue
        field_grid = grid_lowest_available_sweep(
            radar,
            actual,
            grid_size_km=180.0,
            spacing_km=1.0,
        )
        if field_grid is not None:
            gridded[canonical] = grid_field_2d(field_grid, actual)
    field_gradients = {}
    for canonical in ("zdr", "velocity"):
        field = gridded.get(canonical)
        if field is None:
            continue
        field_gradients[canonical] = np.hypot(
            *np.gradient(field, 1.0, edge_order=1)
        )

    # Live objects should represent coherent cells/bands rather than isolated
    # high-gradient pixels. Keep the general detector unchanged for training
    # while using a more spatially coherent configuration for the live view.
    live_detection_config = ObjectDetectionConfig(
        # ProbSevere-style detection is intentionally permissive: identify the
        # coherent radar object first, then let the snow-squall probability
        # model decide whether the object is meteorologically threatening.
        min_pixels=8,
        close_iterations=1,
        open_iterations=0,
        split_merged=False,
        min_candidate_rank_score=0.0,
        use_watershed=True,
        watershed_seed_dbz=25.0,
        watershed_max_dbz=57.0,
        watershed_min_distance_px=6,
        watershed_min_saliency_pixels=8,
        retain_coherent_objects=True,
    )
    detections = detect_reflectivity_objects(
        data,
        config=live_detection_config,
        velocity=gridded.get("velocity"),
    )
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

    rap_forecast_30_result = None
    try:
        rap_forecast_30_result = acquire_forecast_for_radar_time(radar_dt, target_minutes=30)
    except Exception as exc:
        print(f"RAP +30 min forecast warning: {type(exc).__name__}: {exc}")

    previous_reflectivity, previous_radar_time = load_previous_radar_field(state_path)
    radar_motion = None
    if previous_reflectivity is not None and previous_radar_time is not None:
        try:
            previous_dt = (radar_dt - datetime.fromisoformat(previous_radar_time.replace("Z", "+00:00")).astimezone(timezone.utc)).total_seconds() / 60.0
            radar_motion = attach_radar_storm_motion(previous_reflectivity, data, previous_dt, spacing_km=1.0)
        except (TypeError, ValueError, OverflowError):
            radar_motion = None

    tracked = tracker.update(timestamp, detections, radar_motion=radar_motion)

    # Whole-scan base-radar context accompanies every detected object. This is
    # distinct from object-footprint statistics and is available to the model.
    finite_base_refl = data[np.isfinite(data)]
    velocity_grid = gridded.get("velocity")
    finite_base_vel = velocity_grid[np.isfinite(velocity_grid)] if velocity_grid is not None else np.asarray([], dtype=float)
    base_context = {
        "base_reflectivity_mean_dbz": float(np.mean(finite_base_refl)) if finite_base_refl.size else None,
        "base_reflectivity_max_dbz": float(np.max(finite_base_refl)) if finite_base_refl.size else None,
        "base_reflectivity_p90_dbz": float(np.percentile(finite_base_refl, 90)) if finite_base_refl.size else None,
        "base_reflectivity_valid_fraction": float(finite_base_refl.size / data.size) if data.size else 0.0,
        "base_velocity_mean_kt": float(np.mean(finite_base_vel) * 1.94384449244) if finite_base_vel.size else None,
        "base_velocity_std_kt": float(np.std(finite_base_vel) * 1.94384449244) if finite_base_vel.size else None,
        "base_velocity_p90_abs_kt": float(np.percentile(np.abs(finite_base_vel), 90) * 1.94384449244) if finite_base_vel.size else None,
        "base_velocity_valid_fraction": float(finite_base_vel.size / velocity_grid.size) if velocity_grid is not None and velocity_grid.size else 0.0,
        "scan_has_reflectivity": bool(finite_base_refl.size),
        "scan_has_base_velocity": bool(finite_base_vel.size),
        "detected_object_count": int(len(tracked)),
    }

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

        # Publish the consecutive-scan track in geographic coordinates so the
        # viewer can draw the actual object motion rather than pinning every
        # scan to the current footprint.
        track_position_history = []
        for position in obj.get("track_position_history", []) or []:
            try:
                py = int(round(float(position["row"])))
                px = int(round(float(position["column"])))
                if 0 <= py < lat.shape[0] and 0 <= px < lat.shape[1]:
                    plat = float(lat[py, px])
                    plon = float(lon[py, px])
                    if np.isfinite(plat) and np.isfinite(plon):
                        track_position_history.append({
                            "timestamp": position.get("timestamp"),
                            "lat": plat,
                            "lon": plon,
                            "age_scans": int(position.get("age_scans", 0)),
                        })
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

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
            "base_reflectivity_mean_dbz": base_context["base_reflectivity_mean_dbz"],
            "base_reflectivity_max_dbz": base_context["base_reflectivity_max_dbz"],
            "base_reflectivity_p90_dbz": base_context["base_reflectivity_p90_dbz"],
            "base_reflectivity_valid_fraction": base_context["base_reflectivity_valid_fraction"],
            "base_velocity_mean_kt": base_context["base_velocity_mean_kt"],
            "base_velocity_std_kt": base_context["base_velocity_std_kt"],
            "base_velocity_p90_abs_kt": base_context["base_velocity_p90_abs_kt"],
            "base_velocity_valid_fraction": base_context["base_velocity_valid_fraction"],
            "scan_has_reflectivity": base_context["scan_has_reflectivity"],
            "scan_has_base_velocity": base_context["scan_has_base_velocity"],
            "detected_object_count": base_context["detected_object_count"],
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

        environment_forecast_30 = {"status": "unavailable", "source": "RAP", "fields": {}}
        forecast_30_valid_time = None
        if rap_forecast_30_result is not None and centroid_lat is not None and centroid_lon is not None:
            forecast_30_match, forecast_30_path = rap_forecast_30_result
            forecast_30_valid_time = forecast_30_match.valid_time
            try:
                environment_forecast_30 = extract_features(
                    forecast_30_path,
                    centroid_lat,
                    centroid_lon,
                    radar_dt,
                    expected_valid_time=forecast_30_match.valid_time,
                    allow_future=True,
                )
                environment_forecast_30["forecast_run_time_utc"] = forecast_30_match.cycle_time.isoformat().replace("+00:00", "Z")
                environment_forecast_30["forecast_valid_time_utc"] = forecast_30_match.valid_time.isoformat().replace("+00:00", "Z")
                environment_forecast_30["forecast_lead_hours"] = int(forecast_30_match.lead_hours)
                environment_forecast_30["target_minutes"] = 30
                environment_forecast_30["actual_valid_offset_minutes"] = round((forecast_30_match.valid_time - radar_dt).total_seconds() / 60.0, 1)
            except Exception as exc:
                environment_forecast_30 = {
                    "source": "RAP",
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "fields": {},
                }

        environment_readiness = assess_environment(
            {**environment.get("fields", {}), "environment": environment, "timestamp": timestamp},
            radar_time=timestamp,
            max_age_minutes=LIVE_ENV_MAX_AGE_MINUTES,
        )
        forecast_reference_time = (
            forecast_30_valid_time.isoformat().replace("+00:00", "Z")
            if forecast_30_valid_time is not None else timestamp
        )
        environment_forecast_30_readiness = assess_environment(
            {**environment_forecast_30.get("fields", {}), "environment": environment_forecast_30, "timestamp": forecast_reference_time},
            radar_time=forecast_reference_time,
        )
        environment_fields = environment.get("fields") or {}
        environment_forecast_30_fields = environment_forecast_30.get("fields") or {}

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
            "velocity_gradient_p90_ktkm": obj.get("velocity_gradient_p90_ktkm"),
            "velocity_background_kt": obj.get("velocity_background_kt"),
            "velocity_contrast_kt": obj.get("velocity_contrast_kt"),
            "velocity_rescue": obj.get("velocity_rescue"),
            "detection_evidence": obj.get("detection_evidence"),
            "candidate_rank_score": obj.get("candidate_rank_score"),
            "candidate_rank_tier": obj.get("candidate_rank_tier"),
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
            "track_first_scan_utc": obj.get("track_first_scan_utc"),
            "track_age_min": obj.get("track_age_min"),
            "track_status": obj.get("track_status", "active"),
            "track_missed_scans": obj.get("track_missed_scans"),
            "track_position_history": track_position_history,
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
            "environment_model_ready": bool(environment_readiness["ready"]),
            "environment_missing_fields": environment_readiness["missing_fields"],
            "environment_age_minutes": environment_readiness["age_minutes"],
            "environment_forecast_30min": environment_forecast_30,
            "environment_forecast_30min_model_ready": bool(environment_forecast_30_readiness["ready"]),
            "environment_forecast_30min_missing_fields": environment_forecast_30_readiness["missing_fields"],
            "environment_forecast_30min_age_minutes": environment_forecast_30_readiness["age_minutes"],
            "environment_forecast_30min_valid_time_utc": environment_forecast_30.get("forecast_valid_time_utc"),
            "environment_forecast_30min_run_time_utc": environment_forecast_30.get("forecast_run_time_utc"),
            "environment_forecast_30min_lead_hours": environment_forecast_30.get("forecast_lead_hours"),
            **environment_fields,
            **environment_risk_features(environment_fields),
            **{f"expected_30min_{key}": value for key, value in environment_forecast_30_fields.items()},
            "data_quality": "degraded" if obj.get("touches_grid_edge", False) else "good",
            "model_version": "live-object-foundation-v2",
        })

    # Optional learned-model scoring is deliberately opt-in and release-gated
    # for live execution. Archived replay may explicitly score candidate bundles.
    if model_runtimes is None:
        model_runtimes = {}
    if model_dir and not model_runtimes:
        root = Path(model_dir)
        if any((root / name).exists() for name in (
            "candidate_ensemble_refresh_15m", "candidate_ensemble_expansion_15m",
            "baseline_refresh_15m", "baseline_expansion_15m",
        )):
            model_runtimes = ModelRuntime.load_horizon_set(root)
        else:
            single = ModelRuntime.load(root)
            if single.model is not None and single.horizon_minutes in {15, 30, 45, 60}:
                model_runtimes[single.horizon_minutes] = single
    # The transparent research component model is always available when a live
    # object exists. Learned horizon models remain separate diagnostics until
    # their release gate is satisfied.
    from scripts.probability_components import horizon_component_scores

    model_scored = False
    model_errors = {}
    probability_mode = "research_weighted_components"
    model_versions = {}
    learned_probability_by_feature = {}

    # Optional learned-model scoring is retained for comparison/replay. It no
    # longer replaces the transparent 50/50 radar/environment component probability.
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
                        for_horizon = learned_probability_by_feature.setdefault(id(feature), {})
                        if scores:
                            for_horizon[str(horizon)] = float(scores[0])
                        model_scored = model_scored or bool(scores)
                except Exception as exc:
                    model_errors[f"{track_id}:{horizon}"] = f"{type(exc).__name__}: {exc}"

    # Build the requested transparent 0-100 component scores and the final
    # weighted 0-100 probability for every horizon.
    for feature in features:
        component_result = horizon_component_scores(feature)
        feature["radar_component_score"] = component_result["radar"]["score"]
        feature["environment_component_score"] = component_result["environment"]["score"]
        feature["probability_component_weights"] = {
            "radar": 0.50,
            "environment": 0.50,
        }
        feature["probability_components"] = component_result["components"]
        feature["probability_component_detail"] = {
            "radar": component_result["radar"]["detail"],
            "environment": component_result["environment"]["detail"],
        }
        feature["research_probabilities_raw"] = {
            f"{h}min": float(v) / 100.0
            for h, v in component_result["probabilities"].items()
        }
        feature["research_probabilities"] = dict(feature["research_probabilities_raw"])
        # The transparent component model's base score represents the current
        # object state (NOW). Horizon scores remain forward guidance at +15/+30/+45/+60.
        now_score = (
            component_result["radar"]["score"] * 0.50
            + component_result["environment"]["score"] * 0.50
        )
        feature["research_probability_now"] = round(float(now_score) / 100.0, 4)
        feature["probability_now"] = feature["research_probability_now"]
        feature["research_probabilities"]["now"] = feature["research_probability_now"]
        feature["research_interval_probabilities"] = {}
        feature["probability_projection"] = "now_plus15_plus30_plus45_plus60"
        feature["probability_trend"] = "scored"

        learned = learned_probability_by_feature.get(id(feature), {})
        if learned:
            feature["learned_model_probabilities"] = {
                f"{int(h)}min": float(v) for h, v in learned.items()
            }
        else:
            feature["learned_model_probabilities"] = {}

        for horizon in (15, 30, 45, 60):
            feature[f"probability_{horizon}min"] = component_result["probabilities"][horizon] / 100.0

    if features:
        probability_mode = "research_weighted_components"

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
            "probability_status": ("research_scored" if features else ("model_error" if model_errors else "not_scored")),
            "probability_mode": probability_mode,
            "environment_status": (
                "attached" if rap_result is not None else "unavailable"
            ),
            "environment_source": "RAP",
            "radar_origin": list(radar_origin) if radar_origin is not None else None,
            "model_versions": model_versions,
            "model_targets": {
                str(h): runtime.metadata.get("target")
                for h, runtime in model_runtimes.items()
            },
            "model_horizons_minutes": sorted(int(h) for h in model_runtimes),
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

    # Keep a compact environmental history in tracker state as a second,
    # durable source for the browser viewer. This prevents the -30 min RAP
    # column from disappearing if the standalone JSONL history is interrupted.
    env_history = state.setdefault("environment_history", {})
    for feature in features:
        # features is the internal list of property dictionaries. The
        # GeoJSON wrapper is created later when result is built, so reading
        # feature["properties"] here silently produced an empty history.
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else feature
        track_id = str(props.get("track_id"))
        env = props.get("environment") or {}
        fields = env.get("fields") or {}
        if not track_id or not fields:
            continue
        snapshot = {
            "timestamp": props.get("timestamp"),
            "track_id": track_id,
            "environment": {
                "source": env.get("source"),
                "source_valid_time_utc": env.get("source_valid_time_utc"),
                "age_minutes": env.get("age_minutes"),
                "fields": _json_safe(fields),
            },
        }
        history = env_history.setdefault(track_id, [])
        stamp = snapshot.get("timestamp")
        if stamp and not any(str(x.get("timestamp")) == str(stamp) for x in history):
            history.append(snapshot)
        history.sort(key=lambda x: str(x.get("timestamp", "")))
        env_history[track_id] = history[-24:]

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
