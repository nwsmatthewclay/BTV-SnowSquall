"""Process one newly acquired Level-II volume into live object state.

This is the first bridge between real-time acquisition and the object-based
snow-squall pipeline. It is intentionally probability-free: no model score is
invented until trained predictors and leakage-safe labels exist.
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


def object_geometry(mask, lat, lon, spacing_km=1.0):
    from shapely.geometry import MultiPoint

    yy, xx = np.where(mask)
    if len(xx) < 3:
        return None, float(len(xx) * spacing_km**2)

    points = [(float(lon[y, x]), float(lat[y, x])) for y, x in zip(yy, xx)]
    hull = MultiPoint(points).convex_hull
    if hull.is_empty:
        return None, float(len(xx) * spacing_km**2)

    return hull.__geo_interface__, float(len(xx) * spacing_km**2)


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


def save_state(path: Path, state: dict, tracker: CentroidTracker):
    path.parent.mkdir(parents=True, exist_ok=True)
    state["tracker"] = tracker.to_state()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


def process_volume(path: Path, state_path: Path, output_path: Path):
    state, tracker = load_state(state_path)
    source_name = path.name

    processed = set(state.get("processed_sources", []))
    if source_name in processed:
        print(f"SKIP already processed: {source_name}")
        return False

    radar = read_level2(path)
    fields = resolve_fields(radar)
    reflectivity = fields.get("reflectivity")
    if reflectivity is None:
        raise RuntimeError("No reflectivity field found in Level-II volume")

    grid = grid_lowest_sweep(
        radar,
        reflectivity,
        grid_size_km=180.0,
        spacing_km=1.0,
    )
    data = grid_field_2d(grid, reflectivity)
    lat, lon = grid_latlon(grid)

    detections = detect_reflectivity_objects(data)
    metadata = volume_metadata(radar, path)
    timestamp = metadata["scan_time_utc"]

    if not timestamp:
        raise RuntimeError("Unable to determine radar scan time")

    tracked = tracker.update(timestamp, detections)

    features = []
    current_positions = {}
    previous_positions = state.get("object_positions", {})

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
        current_positions[str(obj["object_id"])] = {
            "timestamp": timestamp,
            "lat": centroid_lat,
            "lon": centroid_lon,
        }

        features.append({
            "track_id": str(obj["object_id"]),
            "timestamp": timestamp,
            "radar_site": metadata.get("radar_id"),
            "geometry": geometry,
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "pixel_count": obj["pixel_count"],
            "area_km2": area_km2,
            "max_reflectivity_dbz": obj["max_reflectivity_dbz"],
            "mean_reflectivity_dbz": obj["mean_reflectivity_dbz"],
            "core_pixel_count": obj["core_pixel_count"],
            "motion_speed_kt": speed_kt,
            "motion_dir_deg": direction_deg,
            "probability_15min": None,
            "probability_30min": None,
            "probability_45min": None,
            "probability_60min": None,
            "probability_trend": "unknown",
            "drivers": [],
            "data_quality": "good",
            "model_version": "live-object-foundation-v1",
        })

    result = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": f.pop("geometry"),
                "properties": f,
            }
            for f in features
        ],
        "metadata": {
            "scan_time_utc": timestamp,
            "source_file": source_name,
            "fields": fields,
            "object_count": len(features),
            "probability_status": "not_scored",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(output_path)

    processed.add(source_name)
    state["processed_sources"] = sorted(processed)[-500:]
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
    args = parser.parse_args()

    process_volume(Path(args.input), Path(args.state), Path(args.output))


if __name__ == "__main__":
    main()
