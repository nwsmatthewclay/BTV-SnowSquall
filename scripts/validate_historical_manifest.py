#!/usr/bin/env python3
"""Validate historical case labels before feature extraction/training."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

REQUIRED = {
    "case_id", "event_date", "event_time_utc", "site", "classification",
    "verification", "source", "visibility_km", "peak_wind_kt",
    "peak_gust_kt", "start_temp_c", "end_temp_c", "hybrid",
}


def as_float(value: str, field: str, case_id: str) -> None:
    if value.strip() == "":
        return
    x = float(value)
    if not math.isfinite(x):
        raise ValueError(f"{case_id}: non-finite {field}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("manifest", nargs="?", default="data/historical/case_manifest.csv")
    p.add_argument("--expected-benchmark-count", type=int, default=36)
    args = p.parse_args()

    with Path(args.manifest).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED - fields
        if missing:
            raise SystemExit(f"Missing required fields: {sorted(missing)}")

        rows = list(reader)

    ids = [r["case_id"] for r in rows]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise SystemExit(f"Duplicate case_id values: {duplicates}")

    allowed_class = {"positive", "candidate", "negative", "unknown"}
    allowed_verification = {"research_confirmed", "verified", "candidate", "unverified", "unknown"}

    for r in rows:
        if r["classification"] not in allowed_class:
            raise SystemExit(f"{r['case_id']}: invalid classification")
        if r["verification"] not in allowed_verification:
            raise SystemExit(f"{r['case_id']}: invalid verification")
        if r["visibility_km"].strip():
            as_float(r["visibility_km"], "visibility_km", r["case_id"])
        as_float(r["peak_wind_kt"], "peak_wind_kt", r["case_id"])
        as_float(r["peak_gust_kt"], "peak_gust_kt", r["case_id"])
        as_float(r["start_temp_c"], "start_temp_c", r["case_id"])
        as_float(r["end_temp_c"], "end_temp_c", r["case_id"])

    benchmark = [r for r in rows if r["source"] == "Banacos_2014"]
    if len(benchmark) != args.expected_benchmark_count:
        raise SystemExit(
            f"Expected {args.expected_benchmark_count} Banacos_2014 rows; found {len(benchmark)}"
        )

    kb = sum(r["site"] == "KBTV" for r in benchmark)
    if kb != 21:
        raise SystemExit(f"Expected 21 KBTV benchmark cases; found {kb}")

    print(f"PASS: {len(rows)} rows; {len(benchmark)} published benchmark rows; {kb} KBTV cases")


if __name__ == "__main__":
    main()
