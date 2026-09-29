"""Attach leakage-safe historical RUC/RAP environment fields to object scans."""
from __future__ import annotations

import argparse
from datetime import timezone
from pathlib import Path
import pandas as pd

from processing.environment import acquire_for_radar_time, extract_features, environment_cache_key


def enrich(input_csv: Path, output_csv: Path, rap_dir: Path, ruc_dir: Path):
    objects = pd.read_csv(input_csv)
    objects["scan_dt"] = pd.to_datetime(objects["scan_time_utc"], utc=True, errors="coerce")
    objects = objects.dropna(subset=["scan_dt"]).copy()

    cache = {}
    rows = []
    for _, obj in objects.iterrows():
        row = obj.to_dict()
        row["label_status"] = "candidate_null"
        scan_time = obj["scan_dt"].to_pydatetime().astimezone(timezone.utc)
        lat, lon = obj.get("centroid_lat"), obj.get("centroid_lon")
        if pd.isna(lat) or pd.isna(lon):
            row.update({
                "environment_source": None,
                "environment_status": "unavailable",
                "environment_valid_time_utc": None,
                "environment_age_minutes": None,
            })
            rows.append(row)
            continue

        hour_key = environment_cache_key(scan_time)
        if hour_key not in cache:
            cache[hour_key] = acquire_for_radar_time(
                scan_time, rap_dir=rap_dir, ruc_dir=ruc_dir, max_age_minutes=180
            )

        acquired = cache[hour_key]
        if acquired is None:
            row.update({
                "environment_source": None,
                "environment_status": "unavailable",
                "environment_valid_time_utc": None,
                "environment_age_minutes": None,
            })
            rows.append(row)
            continue

        provider, match, path = acquired
        env = extract_features(
            provider, path, float(lat), float(lon), scan_time,
            expected_valid_time=match.valid_time,
        )
        row["environment_source"] = provider
        row["environment_status"] = env.get("status", "partial")
        row["environment_valid_time_utc"] = env.get("source_valid_time_utc")
        row["environment_match_method"] = "latest_valid_analysis_at_or_before_scan"
        row["environment_time_delta_policy"] = "scan_time_minus_source_valid_time"
        row["environment_age_minutes"] = env.get("age_minutes")
        for key, value in (env.get("fields") or {}).items():
            row[key] = value
        rows.append(row)

    result = pd.DataFrame(rows).drop(columns=["scan_dt"], errors="ignore")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False)
    print(f"Wrote {len(result)} environment-enriched object scans to {output_csv}")
    print("Environment source:")
    print(result["environment_source"].value_counts(dropna=False).to_string())
    print("Environment status:")
    print(result["environment_status"].value_counts(dropna=False).to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rap-dir", default="data/raw/RAP")
    parser.add_argument("--ruc-dir", default="data/raw/RUC")
    args = parser.parse_args()
    enrich(Path(args.input_csv), Path(args.output), Path(args.rap_dir), Path(args.ruc_dir))


if __name__ == "__main__":
    main()
