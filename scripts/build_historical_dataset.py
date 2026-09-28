"""Build an ML-ready historical object dataset from reconstructed radar scans.

This stage enriches object scans with verified case metadata and time-matched
RAP environment. It deliberately does not invent event end times or future
labels when the source case metadata does not provide them.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from processing.environment import acquire_for_radar_time, extract_features


def parse_time(value):
    if not value or pd.isna(value):
        return None
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


def load_cases(path: Path):
    df = pd.read_csv(path)
    df["event_start_dt"] = df["event_start_utc"].map(parse_time)
    return df.set_index("case_id")


def choose_case(scan_time, cases):
    candidates = []
    for case_id, case in cases.iterrows():
        start = case["event_start_dt"]
        if start is None:
            continue
        delta_min = abs((scan_time - start).total_seconds()) / 60.0
        if delta_min <= 180:
            candidates.append((delta_min, case_id, case))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])


def enrich(input_csv: Path, output_csv: Path, cases_csv: Path, rap_dir: Path, ruc_dir: Path):
    objects = pd.read_csv(input_csv)
    objects["scan_dt"] = pd.to_datetime(objects["scan_time_utc"], utc=True, errors="coerce")
    objects = objects.dropna(subset=["scan_dt"]).copy()
    cases = load_cases(cases_csv)

    cache = {}
    rows = []

    for _, obj in objects.iterrows():
        scan_time = obj["scan_dt"].to_pydatetime().astimezone(timezone.utc)
        case_match = choose_case(scan_time, cases)

        row = obj.to_dict()
        row["case_id"] = None
        row["case_source_study"] = None
        row["case_event_start_utc"] = None
        row["case_observing_station"] = None
        row["case_peak_wind_kt"] = None
        row["case_min_visibility_km"] = None
        row["case_hybrid"] = None
        row["case_time_relation"] = "unmatched"

        if case_match:
            _, case_id, case = case_match
            row.update({
                "case_id": case_id,
                "case_source_study": case["source_study"],
                "case_event_start_utc": case["event_start_utc"],
                "case_observing_station": case["observing_station"],
                "case_peak_wind_kt": case["peak_wind_kt"],
                "case_min_visibility_km": case["min_visibility_km"],
                "case_hybrid": bool(case["hybrid_case"]),
                "case_time_relation": (
                    "at_or_near_verified_onset"
                    if abs((scan_time - case["event_start_dt"]).total_seconds()) <= 30 * 60
                    else "within_case_context"
                ),
            })

        lat = obj.get("centroid_lat")
        lon = obj.get("centroid_lon")
        if pd.isna(lat) or pd.isna(lon):
            row["environment_status"] = "unavailable"
            rows.append(row)
            continue

        hour_key = scan_time.replace(minute=0, second=0, microsecond=0).isoformat()
        if hour_key not in cache:
            acquired = acquire_for_radar_time(
                scan_time,
                rap_dir=rap_dir,
                ruc_dir=ruc_dir,
                max_age_minutes=180,
            )
            cache[hour_key] = acquired

        acquired = cache[hour_key]
        if acquired is None:
            row["environment_status"] = "unavailable"
            rows.append(row)
            continue

        provider, match, environment_path = acquired
        environment = extract_features(
            provider,
            environment_path,
            float(lat),
            float(lon),
            scan_time,
            expected_valid_time=match.valid_time,
        )

        row["environment_status"] = environment.get("status", "partial")
        row["environment_source"] = provider
        row["environment_valid_time_utc"] = environment.get("source_valid_time_utc")
        row["environment_age_minutes"] = environment.get("age_minutes")
        for key, value in (environment.get("fields") or {}).items():
            row[key] = value

        # No future target is assigned here. The event metadata is descriptive,
        # while outcome labels require a separate observation-based labeling pass.
        row["label_status"] = "historical_case_context_only"
        row["snow_squall_outcome"] = None
        rows.append(row)

    result = pd.DataFrame(rows)
    result = result.sort_values(["scan_dt", "radar_site", "object_id"])
    result.drop(columns=["scan_dt"], inplace=True, errors="ignore")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False)

    print(f"Wrote {len(result)} object-timestep records to {output_csv}")
    print(f"RAP files used: {len(cache)}")
    print(f"Complete RAP records: {(result['environment_status'] == 'complete').sum()}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", default="data/manifests/banacos_2014_cases.csv")
    parser.add_argument("--rap-dir", default="data/raw/RAP")
    parser.add_argument("--ruc-dir", default="data/raw/RUC")
    args = parser.parse_args()
    enrich(
        Path(args.input_csv),
        Path(args.output),
        Path(args.cases),
        Path(args.rap_dir),
        Path(args.ruc_dir),
    )


if __name__ == "__main__":
    main()
