"""Classify historical null windows by meteorological object activity.

This taxonomy is diagnostic only. It does not label a null window as truth or
change model-training membership automatically.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def classify(objects: pd.DataFrame) -> pd.DataFrame:
    required = {"null_id", "radar_site", "scan_time_utc"}
    missing = sorted(required - set(objects.columns))
    if missing:
        raise ValueError(f"Missing null-window columns: {missing}")

    d = objects.copy()
    d["scan_time_utc"] = pd.to_datetime(d["scan_time_utc"], utc=True, errors="coerce")
    d["max_reflectivity_dbz"] = pd.to_numeric(
        d.get("max_reflectivity_dbz"), errors="coerce"
    )
    d["core_pixel_count"] = pd.to_numeric(
        d.get("core_pixel_count"), errors="coerce"
    )
    grouped = (
        d.dropna(subset=["null_id"])
        .groupby("null_id", dropna=False)
        .agg(
            radar_count=("radar_site", "nunique"),
            object_records=("object_id", "count"),
            unique_objects=("object_id", "nunique"),
            scan_count=("scan_time_utc", "nunique"),
            max_reflectivity_dbz=("max_reflectivity_dbz", "max"),
            max_core_pixels=("core_pixel_count", "max"),
        )
        .reset_index()
    )

    def level(row):
        if row["object_records"] == 0 or pd.isna(row["max_reflectivity_dbz"]):
            return "quiet"
        if row["max_reflectivity_dbz"] >= 40.0 or (
            pd.notna(row["max_core_pixels"]) and row["max_core_pixels"] > 0
        ):
            return "high_activity_hard_negative_candidate"
        if row["max_reflectivity_dbz"] >= 30.0:
            return "moderate_activity"
        return "light_activity"

    grouped["activity_class"] = grouped.apply(level, axis=1)
    grouped["selection_policy"] = "diagnostic_only"
    return grouped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = classify(pd.read_csv(args.input_csv))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print("Null window activity classes:")
    print(result["activity_class"].value_counts().to_string())


if __name__ == "__main__":
    main()
