"""Preflight archived Level-II coverage for the outcome-blind modern cohort.

This step checks only archive availability. It does not inspect reflectivity,
surface impacts, model output, or event severity.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from datetime import timedelta

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.client import Config

BUCKET = "unidata-nexrad-level2"


def client():
    return boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED),
    )


def key_time(name: str):
    import re
    match = re.match(r"^K[A-Z0-9]{3}(\d{8}_\d{6})(?:_.*|\.gz)$", name)
    if not match or name.endswith("_MDM"):
        return None
    return pd.to_datetime(match.group(1), format="%Y%m%d_%H%M%S", utc=True)


def count_volumes(s3, radar: str, start: pd.Timestamp, end: pd.Timestamp) -> tuple[int, str | None, str | None]:
    day = start.normalize()
    count = 0
    first = last = None
    while day <= end.normalize():
        prefix = f"{day:%Y/%m/%d}/{radar}/"
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                name = Path(obj["Key"]).name
                t = key_time(name)
                if t is None or t < start or t > end:
                    continue
                count += 1
                iso = t.isoformat()
                first = iso if first is None else min(first, iso)
                last = iso if last is None else max(last, iso)
        day += pd.Timedelta(days=1)
    return count, first, last


def build(cohort_path: Path, output_path: Path, buffer_before: int = 30, buffer_after: int = 30) -> pd.DataFrame:
    cohort = pd.read_csv(cohort_path)
    candidates = cohort[
        cohort["selection_basis"] == "one_hash_selected_episode_per_year"
    ].copy()
    if candidates.empty:
        raise ValueError("No outcome-blind reconstruction candidates found")

    s3 = client()
    rows = []
    for row in candidates.itertuples(index=False):
        start = pd.to_datetime(row.episode_start, utc=True) - pd.Timedelta(minutes=buffer_before)
        end = pd.to_datetime(row.episode_end, utc=True) + pd.Timedelta(minutes=buffer_after)
        for radar in ("KCXX", "KTYX"):
            count, first, last = count_volumes(s3, radar, start, end)
            rows.append({
                "case_id": row.case_id,
                "episode_id": row.episode_id,
                "year": int(row.year),
                "episode_start_utc": pd.to_datetime(row.episode_start, utc=True).isoformat(),
                "episode_end_utc": pd.to_datetime(row.episode_end, utc=True).isoformat(),
                "window_start_utc": start.isoformat(),
                "window_end_utc": end.isoformat(),
                "radar_site": radar,
                "buffer_before_minutes": buffer_before,
                "buffer_after_minutes": buffer_after,
                "level2_volume_count": count,
                "first_volume_utc": first,
                "last_volume_utc": last,
                "archive_status": "available" if count else "unavailable",
                "selection_policy": "outcome_blind_deterministic_year_coverage;archive_availability_only",
                "training_eligible": False,
            })

    result = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(result.to_string(index=False))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--buffer-before", type=int, default=30)
    parser.add_argument("--buffer-after", type=int, default=30)
    args = parser.parse_args()
    build(
        Path(args.cohort),
        Path(args.output),
        args.buffer_before,
        args.buffer_after,
    )


if __name__ == "__main__":
    main()
