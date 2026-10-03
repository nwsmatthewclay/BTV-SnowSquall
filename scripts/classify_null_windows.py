"""Classify historical null windows by meteorological object activity.

This taxonomy is diagnostic only. It does not label a null window as truth or
change model-training membership automatically.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def classify(objects: pd.DataFrame, manifest: pd.DataFrame | None = None) -> pd.DataFrame:
    required = {"null_id", "radar_site", "scan_time_utc"}
    missing = sorted(required - set(objects.columns))
    if missing:
        raise ValueError(f"Missing null-window columns: {missing}")

    d = objects.copy()
    d["scan_time_utc"] = pd.to_datetime(d["scan_time_utc"], utc=True, errors="coerce")
    d["context_only"] = pd.to_numeric(d.get("context_only", 0), errors="coerce").fillna(0).astype(int)
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
            object_records=("object_id", lambda s: int((~d.loc[s.index, "context_only"].astype(bool)).sum())),
            unique_objects=("object_id", lambda s: int(d.loc[s.index].loc[~d.loc[s.index, "context_only"].astype(bool), "object_id"].nunique())),
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

    # Preserve genuinely quiet windows that produce zero object records.
    if manifest is not None:
        missing_manifest = {"null_id"} - set(manifest.columns)
        if missing_manifest:
            raise ValueError(f"Missing null-window manifest columns: {sorted(missing_manifest)}")
        manifest_ids = (
            manifest[["null_id"]]
            .dropna()
            .drop_duplicates()
            .assign(null_id=lambda x: x["null_id"].astype(str))
        )
        grouped["null_id"] = grouped["null_id"].astype(str)
        grouped = manifest_ids.merge(grouped, on="null_id", how="left")
        for column in [
            "radar_count", "object_records", "unique_objects", "scan_count",
            "max_reflectivity_dbz", "max_core_pixels",
        ]:
            if column in grouped.columns:
                grouped[column] = grouped[column].fillna(0)
        grouped["activity_class"] = grouped["activity_class"].fillna("quiet_no_objects")
        grouped["selection_policy"] = grouped["selection_policy"].fillna("diagnostic_only")
    return grouped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest) if args.manifest else None
    result = classify(pd.read_csv(args.input_csv), manifest=manifest)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print("Null window activity classes:")
    print(result["activity_class"].value_counts().to_string())


if __name__ == "__main__":
    main()
