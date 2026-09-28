"""Run the first geographic radar-object reconstruction pilot.

Input:
    data/raw/level2/<RADAR>/<YYYYMMDD>/*

Output:
    data/derived/pilot_object_scans.csv

The pilot grids each lowest radar sweep onto a common Cartesian grid before
detecting objects. This is the key transition from radar-native pixels to
trackable geographic storm objects.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, Polygon

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.object_detector import detect_reflectivity_objects
from processing.object_tracker import CentroidTracker
from processing.radar_grid import grid_field_2d, grid_latlon, grid_lowest_sweep
from processing.motion import add_motion_features


def object_geometry(mask, lat, lon, spacing_km=1.0):
    """Create a geographic footprint from an object mask.

    A convex hull is used for the first pilot; later versions can preserve
    concave storm boundaries from the connected-component footprint.
    """
    yy, xx = np.where(mask)
    if len(xx) < 3:
        return None, np.nan, np.nan, np.nan

    points = [(float(lon[y, x]), float(lat[y, x])) for y, x in zip(yy, xx)]
    hull = MultiPoint(points).convex_hull
    if hull.is_empty:
        return None, np.nan, np.nan, np.nan

    # Approximate planar dimensions from the grid spacing. The projected
    # Cartesian grid is locally metric; this first pilot only needs stable
    # geometry descriptors for object tracking/model development.
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
    fields = resolve_fields(radar)
    reflectivity = fields["reflectivity"]
    if reflectivity is None:
        return []

    origin_lat = origin_lon = None
    if radar_origin:
        origin_lat, origin_lon = radar_origin

    grid = grid_lowest_sweep(
        radar,
        reflectivity,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        grid_size_km=180.0,
        spacing_km=1.0,
    )
    data = grid_field_2d(grid, reflectivity)
    lat, lon = grid_latlon(grid)

    objects = detect_reflectivity_objects(data)
    meta = volume_metadata(radar, path)
    timestamp = meta["scan_time_utc"]
    tracked = tracker.update(timestamp, objects)

    for obj in tracked:
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

    return tracked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/level2")
    parser.add_argument("--output", default="data/derived/pilot_object_scans.csv")
    args = parser.parse_args()

    input_root = Path(args.input)
    files = sorted(p for p in input_root.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"No Level-II files found below {input_root}")

    trackers = {}
    rows = []

    for path in files:
        radar = path.parts[-3] if len(path.parts) >= 3 else "UNKNOWN"
        tracker = trackers.setdefault(radar, CentroidTracker())

        try:
            objects = process_volume(path, tracker)
        except Exception as exc:
            print(f"SKIP {path}: {type(exc).__name__}: {exc}")
            continue

        for obj in objects:
            rows.append({
                "radar_site": radar,
                "source_file": str(path),
                "scan_time_utc": obj.get("scan_time_utc"),
                "object_id": obj["object_id"],
                "pixel_count": obj["pixel_count"],
                "max_reflectivity_dbz": obj["max_reflectivity_dbz"],
                "mean_reflectivity_dbz": obj["mean_reflectivity_dbz"],
                "core_pixel_count": obj["core_pixel_count"],
                "row_centroid": obj["row_centroid"],
                "column_centroid": obj["column_centroid"],
                "centroid_lat": obj.get("centroid_lat"),
                "centroid_lon": obj.get("centroid_lon"),
                "area_km2": obj.get("area_km2"),
                "length_km": obj.get("length_km"),
                "width_km": obj.get("width_km"),
                "geometry_wkt": obj.get("geometry_wkt"),
            })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("No candidate objects were produced.")

    frame = pd.DataFrame(rows)
    frame = add_motion_features(frame)
    frame.to_csv(output, index=False)

    print(f"Wrote {len(rows)} geographic object-scan records to {output}")


if __name__ == "__main__":
    main()
