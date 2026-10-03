"""Run the first geographic radar-object reconstruction pilot.

The pilot grids each lowest radar sweep onto a common Cartesian grid before
detecting objects. Failed volume reads are retained in a machine-readable
error log so missing historical scans cannot disappear silently.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.object_detector import detect_reflectivity_objects
from processing.object_tracker import CentroidTracker
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep
from processing.radar_sites import apply_radar_origin, radar_origin_for_site
from processing.motion import add_motion_features
from processing.radar_storm_motion import attach_radar_storm_motion
from processing.radar_features import object_field_summary, velocity_object_summary
from processing.vertical_structure import summarize_vertical_structure


def object_geometry(mask, lat, lon, spacing_km=1.0):
    """Return the actual raster-cell footprint outline, not a convex hull.

    Convex-hulling the detected pixels can bridge concavities and turn a real
    snow-squall cell/band into giant triangular or wedge-shaped polygons. The
    replay geometry should follow the detected grid cells themselves.
    """
    yy, xx = np.where(mask)
    if len(xx) == 0:
        return None, np.nan, np.nan, np.nan

    finite = (
        np.isfinite(lat[yy, xx]) &
        np.isfinite(lon[yy, xx])
    )
    yy, xx = yy[finite], xx[finite]
    if len(xx) == 0:
        return None, np.nan, np.nan, np.nan

    dlat = np.nanmedian(np.abs(np.diff(lat, axis=0)))
    dlon = np.nanmedian(np.abs(np.diff(lon, axis=1)))
    fallback = float(spacing_km) / 111.0
    if not np.isfinite(dlat) or dlat <= 0:
        dlat = fallback
    if not np.isfinite(dlon) or dlon <= 0:
        mean_lat = np.nanmean(lat[yy, xx])
        dlon = fallback / max(0.2, np.cos(np.deg2rad(mean_lat)))

    cells = [
        box(
            float(lon[y, x] - dlon / 2.0),
            float(lat[y, x] - dlat / 2.0),
            float(lon[y, x] + dlon / 2.0),
            float(lat[y, x] + dlat / 2.0),
        )
        for y, x in zip(yy, xx)
    ]
    geom = unary_union(cells).buffer(0)
    if geom.is_empty:
        return None, np.nan, np.nan, np.nan
    if geom.geom_type != "Polygon":
        polygons = [part for part in getattr(geom, "geoms", ()) if part.geom_type == "Polygon"]
        if not polygons:
            return None, np.nan, np.nan, np.nan
        geom = max(polygons, key=lambda part: part.area)

    area_km2 = float(len(xx) * spacing_km * spacing_km)
    minx, miny, maxx, maxy = geom.bounds
    mean_lat = np.nanmean(lat[yy, xx])
    dx = (maxx - minx) * 111.0 * np.cos(np.deg2rad(mean_lat))
    dy = (maxy - miny) * 111.0
    length_km = float(max(dx, dy))
    width_km = float(min(dx, dy))
    return geom.wkt, area_km2, length_km, width_km


def object_shape_metrics(rows, cols, spacing_km=1.0):
    """Estimate major/minor axes and orientation from an object footprint."""
    if len(rows) < 3:
        return np.nan, np.nan, np.nan
    xy=np.column_stack((cols.astype(float),rows.astype(float)))
    centered=xy-xy.mean(axis=0)
    cov=np.cov(centered,rowvar=False)
    if cov.shape!=(2,2) or not np.all(np.isfinite(cov)): return np.nan,np.nan,np.nan
    eigenvalues,eigenvectors=np.linalg.eigh(cov)
    order=np.argsort(eigenvalues)[::-1]
    eigenvalues=np.maximum(eigenvalues[order],0.0)
    major=4.0*np.sqrt(float(eigenvalues[0]))*spacing_km
    minor=4.0*np.sqrt(float(eigenvalues[1]))*spacing_km
    vec=eigenvectors[:,order[0]]
    orientation=(np.degrees(np.arctan2(float(vec[0]),float(vec[1])))+180.0)%180.0
    return float(major),float(minor),float(orientation)

def process_volume(path: Path, tracker: CentroidTracker, radar_origin=None, previous_reflectivity=None, previous_time=None):
    radar = read_level2(path)
    apply_radar_origin(radar, radar_origin)
    fields = resolve_fields(radar)
    reflectivity = fields["reflectivity"]
    if reflectivity is None:
        return []

    origin_lat = origin_lon = None
    if radar_origin:
        origin_lat, origin_lon = radar_origin

    available_fields = [name for name in fields.values() if name]
    grid = grid_lowest_sweep(
        radar,
        available_fields,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        grid_size_km=180.0,
        spacing_km=1.0,
    )
    data = grid_field_2d(grid, reflectivity)
    lat, lon = grid_latlon(grid)
    gridded = {
        canonical: grid_field_2d(grid, actual)
        for canonical, actual in fields.items()
        if actual
    }
    field_gradients = {}
    for canonical in ("zdr", "velocity"):
        field = gridded.get(canonical)
        if field is None:
            continue
        field_gradients[canonical] = np.hypot(
            *np.gradient(field, 1.0, edge_order=1)
        )

    objects = detect_reflectivity_objects(data, velocity=gridded.get("velocity"))
    meta = volume_metadata(radar, path)
    timestamp = meta["scan_time_utc"]
    radar_motion = None
    if previous_reflectivity is not None and previous_time is not None:
        prev_dt = (pd.to_datetime(timestamp, utc=True) - pd.to_datetime(previous_time, utc=True)).total_seconds() / 60.0
        radar_motion = attach_radar_storm_motion(
            previous_reflectivity, data, prev_dt, spacing_km=1.0
        )
    tracked = tracker.update(timestamp, objects, radar_motion=radar_motion)

    reader_backend = meta.get("reader_backend")
    for obj in tracked:
        obj["reader_backend"] = reader_backend
        cy = int(round(obj["row_centroid"]))
        cx = int(round(obj["column_centroid"]))
        if 0 <= cy < data.shape[0] and 0 <= cx < data.shape[1]:
            footprint = np.zeros_like(data, dtype=bool)
            rows = np.asarray(obj.get("row_indices", []), dtype=int)
            cols = np.asarray(obj.get("column_indices", []), dtype=int)
            footprint[rows, cols] = True
            geometry_wkt, area_km2, length_km, width_km = object_geometry(
                footprint, lat, lon, spacing_km=1.0
            )
            obj["centroid_lat"] = float(lat[cy, cx])
            obj["centroid_lon"] = float(lon[cy, cx])
        else:
            geometry_wkt, area_km2, length_km, width_km = None, np.nan, np.nan, np.nan
            obj["centroid_lat"] = np.nan
            obj["centroid_lon"] = np.nan

        obj["scan_time_utc"] = timestamp
        obj["geometry_wkt"] = geometry_wkt
        obj["area_km2"] = area_km2
        obj["length_km"] = length_km
        obj["width_km"] = width_km

        if np.isfinite(obj.get("centroid_lat", np.nan)) and np.isfinite(obj.get("centroid_lon", np.nan)):
            vertical = summarize_vertical_structure(
                radar,
                float(obj["centroid_lat"]),
                float(obj["centroid_lon"]),
                reflectivity,
                radar_origin=radar_origin,
            )
            obj.update(vertical)

        if 0 <= cy < data.shape[0] and 0 <= cx < data.shape[1]:
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
                    obj["zdr_mean_db"] = stats["zdr_mean"]
                    obj["zdr_p90_db"] = stats["zdr_p90"]
                    obj["zdr_gradient_dbkm"] = stats["zdr_gradient_dbkm"]
                elif canonical == "rhohv":
                    stats = object_field_summary(finite, "rhohv")
                    obj["rhohv_mean"] = stats["rhohv_mean"]
                    obj["rhohv_max"] = stats["rhohv_max"]
                    obj["rhohv_p90"] = stats["rhohv_p90"]
                    obj["rhohv_min"] = float(np.nanmin(finite)) if finite.size else np.nan
                elif canonical == "kdp":
                    stats = object_field_summary(finite, "kdp")
                    obj["kdp_mean_degkm"] = stats["kdp_mean"]
                    obj["kdp_p90_degkm"] = stats["kdp_p90"]
                elif canonical == "velocity":
                    gradient = field_gradients.get("velocity")
                    obj.update(
                        velocity_object_summary(
                            finite,
                            gradient[footprint] if gradient is not None else None,
                        )
                    )

    return tracked, data, timestamp, gridded.get("velocity")


def _process_radar_files(radar: str, files: list[Path]):
    """Reconstruct one radar serially so its tracker remains scan-order causal."""
    tracker = CentroidTracker()
    previous_fields = {}
    rows = []
    context_rows = []
    errors = []
    radar_origin = radar_origin_for_site(radar)

    for path in files:
        try:
            result = process_volume(
                path,
                tracker,
                radar_origin=radar_origin,
                previous_reflectivity=previous_fields.get(radar, (None, None))[0],
                previous_time=previous_fields.get(radar, (None, None))[1],
            )
            objects, current_reflectivity, current_timestamp, current_velocity = result
            previous_fields[radar] = (current_reflectivity, current_timestamp)
        except Exception as exc:
            errors.append({
                "radar_site": radar,
                "source_file": str(path),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
            print(f"SKIP {path}: {type(exc).__name__}: {exc}")
            continue

        finite_refl = current_reflectivity[np.isfinite(current_reflectivity)]
        finite_vel = (
            current_velocity[np.isfinite(current_velocity)]
            if current_velocity is not None
            else np.asarray([], dtype=float)
        )
        context = {
            "radar_site": radar,
            "source_file": str(path),
            "scan_time_utc": current_timestamp,
            "scan_has_reflectivity": bool(finite_refl.size),
            "scan_has_base_velocity": bool(finite_vel.size),
            "base_reflectivity_mean_dbz": float(np.mean(finite_refl)) if finite_refl.size else np.nan,
            "base_reflectivity_max_dbz": float(np.max(finite_refl)) if finite_refl.size else np.nan,
            "base_reflectivity_p90_dbz": float(np.percentile(finite_refl, 90)) if finite_refl.size else np.nan,
            "base_reflectivity_valid_fraction": float(finite_refl.size / current_reflectivity.size) if current_reflectivity.size else 0.0,
            "base_velocity_mean_kt": float(np.mean(finite_vel) * 1.94384449244) if finite_vel.size else np.nan,
            "base_velocity_std_kt": float(np.std(finite_vel) * 1.94384449244) if finite_vel.size else np.nan,
            "base_velocity_p90_abs_kt": float(np.percentile(np.abs(finite_vel), 90) * 1.94384449244) if finite_vel.size else np.nan,
            "base_velocity_valid_fraction": float(finite_vel.size / current_velocity.size) if current_velocity is not None and current_velocity.size else 0.0,
            "detected_object_count": int(len(objects)),
        }
        context_rows.append(context)

        # A detector miss is not allowed to erase the radar/environment state
        # from the supervised population. This fallback is deliberately marked
        # as context-only so downstream QC can distinguish it from a real object.
        if not objects:
            rows.append({
                "radar_site": radar,
                "source_file": str(path),
                "scan_time_utc": current_timestamp,
                "object_id": 0,
                "detector_object_id": 0,
                "track_id": 0,
                "context_only": 1,
                "pixel_count": 0,
                "max_reflectivity_dbz": context["base_reflectivity_max_dbz"],
                "mean_reflectivity_dbz": context["base_reflectivity_mean_dbz"],
                "core_pixel_count": 0,
                "touches_grid_edge": False,
                "row_centroid": np.nan,
                "column_centroid": np.nan,
                "centroid_lat": radar_origin[0] if radar_origin else np.nan,
                "centroid_lon": radar_origin[1] if radar_origin else np.nan,
                "area_km2": 0.0,
                "length_km": np.nan,
                "width_km": np.nan,
                "shape_major_km": np.nan,
                "shape_minor_km": np.nan,
                "orientation_deg": np.nan,
                "aspect_ratio": np.nan,
                "geometry_wkt": None,
                "core_fraction": 0.0,
                "reflectivity_gradient_p90_dbkm": np.nan,
                "gradient_fraction_above_5dbkm": np.nan,
                "background_reflectivity_dbz": np.nan,
                "reflectivity_contrast_db": np.nan,
                "bbox_aspect_ratio": np.nan,
                "object_mode": "scan_context",
                "velocity_mean_kt": context["base_velocity_mean_kt"],
                "velocity_std_kt": context["base_velocity_std_kt"],
                "velocity_p90_abs_kt": context["base_velocity_p90_abs_kt"],
                "velocity_gradient_ktkm": np.nan,
                "velocity_gradient_p90_ktkm": np.nan,
                "velocity_background_kt": np.nan,
                "velocity_contrast_kt": np.nan,
                "velocity_rescue": False,
            })

        for obj in objects:
            rows_arr = np.asarray(obj.get("row_indices", []), dtype=int)
            cols_arr = np.asarray(obj.get("column_indices", []), dtype=int)
            major_km, minor_km, orientation_deg = object_shape_metrics(
                rows_arr, cols_arr, spacing_km=1.0
            )
            row = {
                "radar_site": radar,
                "source_file": str(path),
                "scan_time_utc": obj.get("scan_time_utc"),
                "reader_backend": obj.get("reader_backend"),
                "object_id": obj["object_id"],
                "pixel_count": obj["pixel_count"],
                "max_reflectivity_dbz": obj["max_reflectivity_dbz"],
                "mean_reflectivity_dbz": obj["mean_reflectivity_dbz"],
                "core_pixel_count": obj["core_pixel_count"],
                "touches_grid_edge": obj.get("touches_grid_edge", False),
                "row_centroid": obj["row_centroid"],
                "column_centroid": obj["column_centroid"],
                "centroid_lat": obj.get("centroid_lat"),
                "centroid_lon": obj.get("centroid_lon"),
                "area_km2": obj.get("area_km2"),
                "length_km": obj.get("length_km"),
                "width_km": obj.get("width_km"),
                "shape_major_km": major_km,
                "shape_minor_km": minor_km,
                "orientation_deg": orientation_deg,
                "aspect_ratio": (
                    major_km / minor_km
                    if np.isfinite(major_km)
                    and np.isfinite(minor_km)
                    and minor_km > 0
                    else np.nan
                ),
                "geometry_wkt": obj.get("geometry_wkt"),
                "core_fraction": float(obj["core_pixel_count"]) / max(1, int(obj["pixel_count"])),
                "track_id": obj.get("track_id", obj.get("object_id")),
                "detector_object_id": obj.get("detector_object_id", obj.get("object_id")),
                "context_only": int(bool(obj.get("context_only", False))),
                "base_reflectivity_mean_dbz": context["base_reflectivity_mean_dbz"],
                "base_reflectivity_max_dbz": context["base_reflectivity_max_dbz"],
                "base_reflectivity_p90_dbz": context["base_reflectivity_p90_dbz"],
                "base_reflectivity_valid_fraction": context["base_reflectivity_valid_fraction"],
                "base_velocity_mean_kt": context["base_velocity_mean_kt"],
                "base_velocity_std_kt": context["base_velocity_std_kt"],
                "base_velocity_p90_abs_kt": context["base_velocity_p90_abs_kt"],
                "base_velocity_valid_fraction": context["base_velocity_valid_fraction"],
                "scan_has_reflectivity": context["scan_has_reflectivity"],
                "scan_has_base_velocity": context["scan_has_base_velocity"],
                "detected_object_count": context["detected_object_count"],
                "reflectivity_gradient_p90_dbkm": obj.get("reflectivity_gradient_p90_dbkm"),
                "gradient_fraction_above_5dbkm": obj.get("gradient_fraction_above_5dbkm"),
                "background_reflectivity_dbz": obj.get("background_reflectivity_dbz"),
                "reflectivity_contrast_db": obj.get("reflectivity_contrast_db"),
                "bbox_aspect_ratio": obj.get("bbox_aspect_ratio", obj.get("aspect_ratio")),
                "object_mode": obj.get("object_mode"),
                "velocity_gradient_p90_ktkm": obj.get("velocity_gradient_p90_ktkm"),
                "velocity_background_kt": obj.get("velocity_background_kt"),
                "velocity_contrast_kt": obj.get("velocity_contrast_kt"),
                "velocity_rescue": obj.get("velocity_rescue"),
                "candidate_rank_score": obj.get("candidate_rank_score"),
                "candidate_rank_tier": obj.get("candidate_rank_tier"),
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
            }
            for key in (
                "motion_distance_km", "motion_speed_kt", "motion_direction_deg",
                "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient",
                "vertical_valid_points", "zdr_mean_db", "zdr_p90_db",
                "zdr_gradient_dbkm", "rhohv_mean", "rhohv_max", "rhohv_p90",
                "rhohv_min", "kdp_mean_degkm", "kdp_p90_degkm",
                "velocity_mean_kt", "velocity_std_kt", "velocity_p90_abs_kt",
                "velocity_gradient_ktkm", "radar_motion_speed_kt",
                "radar_motion_direction_deg", "radar_motion_u_kt", "radar_motion_v_kt",
                "radar_motion_confidence",
            ):
                if key in obj:
                    row[key] = obj.get(key)
            rows.append(row)

    return rows, errors, context_rows



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/level2")
    parser.add_argument("--output", default="data/derived/pilot_object_scans.csv")
    parser.add_argument("--context-output", default=None, help="Scan-level radar context CSV used to audit reflectivity/velocity completeness.")
    parser.add_argument(
        "--error-log",
        default=None,
        help="CSV path for failed radar volumes; defaults beside --output.",
    )
    args = parser.parse_args()

    input_root = Path(args.input)
    output = Path(args.output)
    context_output = Path(args.context_output) if args.context_output else output.with_name(f"{output.stem}_context.csv")
    error_log = (
        Path(args.error_log)
        if args.error_log
        else output.with_name(f"{output.stem}_errors.csv")
    )

    files = sorted(p for p in input_root.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"No Level-II files found below {input_root}")

    grouped: dict[str, list[Path]] = {}
    for path in files:
        radar = path.parts[-3] if len(path.parts) >= 3 else "UNKNOWN"
        grouped.setdefault(radar, []).append(path)

    rows = []
    contexts = []
    errors = []
    # Radar sites are independent; preserve chronological ordering within each
    # radar while processing the two sites concurrently.
    workers = min(2, max(1, len(grouped)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process_radar_files, radar, sorted(radar_files)): radar
            for radar, radar_files in sorted(grouped.items())
        }
        for future in as_completed(futures):
            radar = futures[future]
            try:
                radar_rows, radar_errors, radar_context = future.result()
            except Exception as exc:
                errors.append({
                    "radar_site": radar,
                    "source_file": "",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                continue
            rows.extend(radar_rows)
            errors.extend(radar_errors)
            contexts.extend(radar_context)

    if not rows:
        raise SystemExit("No radar rows were produced.")

    rows.sort(key=lambda r: (
        str(r.get("radar_site", "")),
        str(r.get("scan_time_utc", "")),
        int(r.get("object_id", 0) or 0),
    ))
    errors.sort(key=lambda r: (str(r.get("radar_site", "")), str(r.get("source_file", ""))))

    frame = pd.DataFrame(rows)
    frame = add_motion_features(frame)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    context_frame = pd.DataFrame(contexts)
    context_frame.to_csv(context_output, index=False)
    pd.DataFrame(
        errors,
        columns=["radar_site", "source_file", "error_type", "error_message"],
    ).to_csv(error_log, index=False)

    print(f"Wrote {len(rows)} object scans to {output}")
    print(f"Radar reconstruction failures: {len(errors)}")


if __name__ == "__main__":
    main()
