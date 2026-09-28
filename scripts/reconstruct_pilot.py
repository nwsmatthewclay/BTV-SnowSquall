"""Run the first geographic radar-object reconstruction pilot.

The pilot grids each lowest radar sweep onto a common Cartesian grid before
detecting objects. Failed volume reads are retained in a machine-readable
error log so missing historical scans cannot disappear silently.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, Polygon

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.object_detector import detect_reflectivity_objects
from processing.object_tracker import CentroidTracker
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep
from processing.radar_sites import apply_radar_origin, radar_origin_for_site
from processing.motion import add_motion_features
from processing.radar_features import object_field_summary, velocity_object_summary
from processing.vertical_structure import summarize_vertical_structure


def object_geometry(mask, lat, lon, spacing_km=1.0):
    yy, xx = np.where(mask)
    if len(xx) < 3:
        return None, np.nan, np.nan, np.nan

    points = [(float(lon[y, x]), float(lat[y, x])) for y, x in zip(yy, xx)]
    hull = MultiPoint(points).convex_hull
    if hull.is_empty:
        return None, np.nan, np.nan, np.nan

    area_km2 = float(len(xx) * spacing_km * spacing_km)
    coords = np.asarray(hull.exterior.coords) if isinstance(hull, Polygon) else np.empty((0, 2))
    if len(coords) >= 2:
        dx = np.ptp(coords[:, 0]) * 111.0 * np.cos(np.deg2rad(np.nanmean(lat)))
        dy = np.ptp(coords[:, 1]) * 111.0
        length_km = float(max(dx, dy))
        width_km = float(min(dx, dy))
    else:
        length_km = width_km = np.nan

    return hull.wkt, area_km2, length_km, width_km


def process_volume(path: Path, tracker: CentroidTracker, radar_origin=None):
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

    objects = detect_reflectivity_objects(data)
    meta = volume_metadata(radar, path)
    timestamp = meta["scan_time_utc"]
    tracked = tracker.update(timestamp, objects)

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
                    gradient = np.hypot(
                        *np.gradient(field, 1.0, edge_order=1)
                    )
                    stats = object_field_summary(
                        finite, "zdr", gradient[footprint], "_dbkm"
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
                    gradient = np.hypot(
                        *np.gradient(field, 1.0, edge_order=1)
                    )
                    obj.update(
                        velocity_object_summary(
                            finite, gradient[footprint]
                        )
                    )

    return tracked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/level2")
    parser.add_argument("--output", default="data/derived/pilot_object_scans.csv")
    parser.add_argument(
        "--error-log",
        default=None,
        help="CSV path for failed radar volumes; defaults beside --output.",
    )
    args = parser.parse_args()

    input_root = Path(args.input)
    output = Path(args.output)
    error_log = (
        Path(args.error_log)
        if args.error_log
        else output.with_name(f"{output.stem}_errors.csv")
    )

    files = sorted(p for p in input_root.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"No Level-II files found below {input_root}")

    trackers = {}
    rows = []
    errors = []

    for path in files:
        radar = path.parts[-3] if len(path.parts) >= 3 else "UNKNOWN"
        tracker = trackers.setdefault(radar, CentroidTracker())

        try:
            radar_origin = radar_origin_for_site(radar)
            objects = process_volume(path, tracker, radar_origin=radar_origin)
        except Exception as exc:
            errors.append({
                "radar_site": radar,
                "source_file": str(path),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
            print(f"SKIP {path}: {type(exc).__name__}: {exc}")
            continue

        for obj in objects:
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
                "geometry_wkt": obj.get("geometry_wkt"),
            }
            derived_keys = (
                "motion_distance_km", "motion_speed_kt", "motion_direction_deg",
                "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient",
                "vertical_valid_points", "zdr_mean_db", "zdr_p90_db",
                "zdr_gradient_dbkm", "rhohv_mean", "rhohv_max", "rhohv_p90",
                "rhohv_min", "kdp_mean_degkm", "kdp_p90_degkm",
                "velocity_mean_kt", "velocity_std_kt", "velocity_p90_abs_kt",
                "velocity_gradient_ktkm",
            )
            for key in derived_keys:
                row[key] = obj.get(key)
            rows.append(row)

    if not rows:
        raise SystemExit("No candidate objects were produced.")

    frame = pd.DataFrame(rows)
    frame = add_motion_features(frame)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)

    error_log.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        errors,
        columns=["radar_site", "source_file", "error_type", "error_message"],
    ).to_csv(error_log, index=False)

    print(f"Wrote {len(rows)} geographic object-scan records to {output}")
    print(f"Failed radar volumes logged: {len(errors)} -> {error_log}")


if __name__ == "__main__":
    main()
