"""Acquire ASOS/METAR observations for modern validation candidates.

Only rows explicitly marked reconstruction_eligible are acquired. The analysis
window is a bounded reconstruction window, not an event-truth label.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from acquisition.asos_iem import request_observations


def acquire(cases_path: Path, output_root: Path) -> dict:
    cases = pd.read_csv(cases_path)
    required = {
        "case_id",
        "reconstruction_eligible",
        "analysis_window_start_utc",
        "analysis_window_end_utc",
    }
    missing = sorted(required - set(cases.columns))
    if missing:
        raise ValueError(f"Manifest missing required fields: {missing}")

    if "observing_stations" not in cases.columns:
        if "observing_station" not in cases.columns:
            raise ValueError("Manifest requires observing_station or observing_stations")
        cases["observing_stations"] = cases["observing_station"].fillna("")

    eligible = cases[
        cases["reconstruction_eligible"].astype(str).str.lower() == "true"
    ].copy()

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_rows, errors = [], []

    for row in eligible.itertuples(index=False):
        case_id = str(row.case_id)
        stations = [
            station.strip()
            for station in str(row.observing_stations).split(";")
            if station.strip()
        ]
        if not stations:
            raise ValueError(f"{case_id}: no observing stations specified")

        start = pd.to_datetime(row.analysis_window_start_utc, utc=True)
        end = pd.to_datetime(row.analysis_window_end_utc, utc=True)
        if end < start:
            raise ValueError(f"{case_id}: analysis window ends before it starts")

        for station in stations:
            try:
                data = request_observations(station, start, end)
                out = output_root / station / f"{case_id}.csv"
                out.parent.mkdir(parents=True, exist_ok=True)
                data.to_csv(out, index=False)
                manifest_rows.append({
                    "case_id": case_id,
                    "station": station,
                    "start_utc": start.isoformat().replace("+00:00", "Z"),
                    "end_utc": end.isoformat().replace("+00:00", "Z"),
                    "row_count": int(len(data)),
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

    pd.DataFrame(manifest_rows).to_csv(
        output_root / "modern_validation_surface_manifest.csv", index=False
    )
    pd.DataFrame(
        errors, columns=["case_id", "station", "error_type", "error_message"]
    ).to_csv(output_root / "modern_validation_surface_errors.csv", index=False)

    return {
        "cases": int(len(eligible)),
        "station_requests": int(len(manifest_rows) + len(errors)),
        "successful": int(len(manifest_rows)),
        "failed": int(len(errors)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(acquire(Path(args.cases), Path(args.output)))


if __name__ == "__main__":
    main()
