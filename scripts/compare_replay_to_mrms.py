"""Compare Level-II replay object locations with contemporaneous MRMS reflectivity."""
from __future__ import annotations

import argparse
import json
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd


def parse_time(value: str) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True)


def mrms_time_from_name(path: Path) -> pd.Timestamp:
    stamp = path.stem.rsplit("_", 1)[-1]
    return pd.to_datetime(stamp, format="%Y%m%d%H%M", utc=True)


def nearest_mrms(scan_time: pd.Timestamp, files: list[Path]):
    candidates = [(mrms_time_from_name(p), p) for p in files]
    candidates = [(t, p) for t, p in candidates if t <= scan_time]
    if not candidates:
        return None, None
    return max(candidates, key=lambda x: x[0])


def nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.abs(values - target).argmin())


def sample_mrms(path: Path, lat_value: float, lon_value: float, radius_cells: int = 10) -> tuple[float, float]:
    from netCDF4 import Dataset

    with Dataset(path, mode="r") as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
        field = ds.variables["mrms_lcref"]

        i = nearest_index(lat, lat_value)
        j = nearest_index(lon, lon_value)
        point = float(field[i, j])

        r1 = max(0, i - radius_cells)
        r2 = min(len(lat), i + radius_cells + 1)
        c1 = max(0, j - radius_cells)
        c2 = min(len(lon), j + radius_cells + 1)
        values = np.asarray(field[r1:r2, c1:c2], dtype=float)
        valid = values[np.isfinite(values) & (values < 1.0e19)]
        neighborhood_max = float(valid.max()) if valid.size else float("nan")
        return point, neighborhood_max


def build(replay_root: Path, mrms_root: Path, output_csv: Path) -> dict:
    rows = []
    for replay_manifest in sorted(replay_root.glob("*/replay_manifest.json")):
        case_id = replay_manifest.parent.name
        replay = json.loads(replay_manifest.read_text(encoding="utf-8"))
        mrms_files = sorted((mrms_root / case_id).glob("mrms_lcref_*.nc"))
        if not mrms_files:
            continue

        for record in replay.get("records", []):
            scan_time = parse_time(record["scan_time_utc"])
            mrms_time, mrms_path = nearest_mrms(scan_time, mrms_files)
            if mrms_path is None:
                continue
            geo_path = replay_manifest.parent / record["output_file"]
            payload = json.loads(geo_path.read_text(encoding="utf-8"))
            for feature in payload.get("features", []):
                props = feature.get("properties", {})
                lat = props.get("centroid_lat")
                lon = props.get("centroid_lon")
                if lat is None or lon is None:
                    continue
                point, neighborhood_max = sample_mrms(
                    mrms_path, float(lat), float(lon)
                )
                rows.append({
                    "case_id": case_id,
                    "scan_time_utc": scan_time.isoformat(),
                    "track_id": props.get("track_id"),
                    "centroid_lat": float(lat),
                    "centroid_lon": float(lon),
                    "level2_max_reflectivity_dbz": props.get("max_reflectivity_dbz"),
                    "mrms_valid_time_utc": mrms_time.isoformat(),
                    "mrms_age_minutes": (scan_time - mrms_time).total_seconds() / 60.0,
                    "mrms_point_reflectivity_dbz": point,
                    "mrms_neighborhood_max_dbz": neighborhood_max,
                })

    df = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    summary = {
        "object_records_compared": int(len(df)),
        "scan_count_compared": int(df["scan_time_utc"].nunique()) if not df.empty else 0,
        "cases_compared": sorted(df["case_id"].astype(str).unique().tolist()) if not df.empty else [],
        "max_mrms_age_minutes": float(df["mrms_age_minutes"].max()) if not df.empty else None,
        "scoring_status": "not_scored",
    }
    output_csv.with_suffix(".json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--mrms-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.replay_root), Path(args.mrms_root), Path(args.output))


if __name__ == "__main__":
    main()
