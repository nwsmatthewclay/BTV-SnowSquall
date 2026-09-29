"""Acquire fixed-network ASOS/METAR context for modern candidate episodes."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from acquisition.asos_iem import request_observations


def build(manifest_path: Path, output_root: Path, stations_path: Path) -> dict:
    manifest = pd.read_csv(manifest_path)
    stations = pd.read_csv(stations_path)
    required = {"case_id", "window_start_utc", "window_end_utc"}
    missing = sorted(required - set(manifest.columns))
    if missing:
        raise ValueError(f"Reconstruction manifest missing: {missing}")

    stations = stations.dropna(subset=["station"])
    rows, errors = [], []
    for case in manifest.drop_duplicates("case_id").itertuples(index=False):
        case_id = str(case.case_id)
        start = pd.to_datetime(case.window_start_utc, utc=True)
        end = pd.to_datetime(case.window_end_utc, utc=True)
        for station in stations["station"].astype(str):
            try:
                data = request_observations(station, start, end)
                out = output_root / station / f"{case_id}.csv"
                out.parent.mkdir(parents=True, exist_ok=True)
                data.to_csv(out, index=False)
                rows.append({
                    "case_id": case_id,
                    "station": station,
                    "start_utc": start.isoformat().replace("+00:00", "Z"),
                    "end_utc": end.isoformat().replace("+00:00", "Z"),
                    "row_count": int(len(data)),
                    "status": "downloaded",
                    "output": str(out),
                })
                print(f"{case_id} {station}: {len(data)} observations")
            except Exception as exc:
                errors.append({
                    "case_id": case_id,
                    "station": station,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                print(f"FAILED {case_id} {station}: {type(exc).__name__}: {exc}")

    pd.DataFrame(rows).to_csv(output_root / "surface_context_manifest.csv", index=False)
    pd.DataFrame(
        errors, columns=["case_id", "station", "error_type", "error_message"]
    ).to_csv(output_root / "surface_context_errors.csv", index=False)
    return {"case_station_pairs": len(rows), "failed": len(errors)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--stations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(build(Path(args.manifest), Path(args.output), Path(args.stations)))


if __name__ == "__main__":
    main()
