"""Run the first end-to-end radar-object reconstruction pilot.

This script is intentionally a file-based research pipeline. It does not decide
whether an object is a snow squall; it creates the object/scan records that the
future probability model will consume.

Input:
    data/raw/level2/<RADAR>/<YYYYMMDD>/*

Output:
    data/derived/pilot_object_scans.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata
from processing.object_detector import detect_reflectivity_objects
from processing.object_tracker import CentroidTracker


def lowest_sweep_field(radar, field_name: str):
    sweep = int(radar.sweep_number["data"][0])
    start = int(radar.sweep_start_ray_index["data"][sweep])
    end = int(radar.sweep_end_ray_index["data"][sweep]) + 1
    return radar.fields[field_name]["data"][start:end]


def process_volume(path: Path, tracker: CentroidTracker):
    radar = read_level2(path)
    fields = resolve_fields(radar)
    reflectivity = fields["reflectivity"]
    if reflectivity is None:
        return []

    data = lowest_sweep_field(radar, reflectivity)
    if np.ma.isMaskedArray(data):
        data = data.filled(np.nan)

    # This first pilot uses native lowest-sweep gates as a candidate field.
    # Cartesian gridding and geographic object polygons are the next refinement.
    objects = detect_reflectivity_objects(data)
    meta = volume_metadata(radar, path)
    timestamp = meta["scan_time_utc"]
    tracked = tracker.update(timestamp, objects)
    for obj in tracked:
        obj["scan_time_utc"] = timestamp
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
            })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("No candidate objects were produced.")

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} object-scan records to {output}")


if __name__ == "__main__":
    main()
