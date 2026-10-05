"""Materialize row-level provenance for human-reviewed hard-negative windows.

The promotion decision is made at the null-window level, but training happens at
the object-timestep level. This script expands each reviewed null_id into the
exact feature rows that become eligible for negative training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(
    features: pd.DataFrame,
    promoted: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    required_features = {"null_id", "population", "scan_time_utc"}
    missing = sorted(required_features - set(features.columns))
    if missing:
        raise ValueError("Feature table missing required columns: " + ", ".join(missing))

    required_promoted = {"null_id", "negative_truth_status"}
    missing = sorted(required_promoted - set(promoted.columns))
    if missing:
        raise ValueError("Promoted manifest missing required columns: " + ", ".join(missing))

    p = promoted.copy()
    p["null_id"] = p["null_id"].fillna("").astype(str).str.strip()
    if not p["negative_truth_status"].fillna("").astype(str).str.strip().eq("reviewed_negative").all():
        raise ValueError("Promoted manifest contains a non-reviewed-negative row")

    p = p[p["null_id"].ne("")].drop_duplicates("null_id")
    f = features.copy()
    f["null_id"] = f["null_id"].fillna("").astype(str).str.strip()

    rows = f[
        f["population"].eq("winter_null_candidate")
        & f["null_id"].isin(set(p["null_id"]))
    ].copy()

    if rows.empty and not p.empty:
        raise ValueError("Promoted review windows have no matching winter-null feature rows")

    if "row_identity_key" not in rows.columns:
        object_id = rows.get("object_id", pd.Series("", index=rows.index)).fillna("").astype(str)
        radar = rows.get("radar_site", pd.Series("", index=rows.index)).fillna("").astype(str)
        scan = rows["scan_time_utc"].fillna("").astype(str)
        rows["row_identity_key"] = (
            "reviewed_negative:" + rows["null_id"] + ":" + radar + ":" + object_id + ":" + scan
        )

    review_cols = [
        "null_id", "hard_negative_score", "peak_object_id",
        "peak_scan_time_utc", "peak_radar_site", "reviewer",
        "reviewed_at_utc", "review_notes", "promotion_reason",
    ]
    review_cols = [c for c in review_cols if c in p.columns]
    rows = rows.merge(
        p[review_cols].drop_duplicates("null_id"),
        on="null_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_review"),
    )

    rows["negative_truth_status"] = "reviewed_negative"
    rows["promotion_source"] = "human_reviewed_hard_negative_null"
    rows["future_information_policy"] = rows.get(
        "future_information_policy",
        pd.Series("current_and_past_only", index=rows.index),
    )

    if "case_id" in rows.columns:
        contaminated_case_ids = rows["case_id"].fillna("").astype(str).str.strip().ne("")
        if contaminated_case_ids.any():
            raise ValueError("Reviewed negative rows unexpectedly contain case_id values")

    duplicate_identity = int(rows["row_identity_key"].duplicated().sum())
    if duplicate_identity:
        raise ValueError(
            f"Reviewed-negative object manifest contains {duplicate_identity} duplicate row identities"
        )

    summary = {
        "manifest_version": "reviewed_negative_object_manifest_v1",
        "reviewed_negative_windows": int(p["null_id"].nunique()),
        "reviewed_negative_object_rows": int(len(rows)),
        "reviewed_negative_object_rows_by_radar": (
            rows["radar_site"].value_counts().to_dict()
            if "radar_site" in rows.columns else {}
        ),
        "reviewed_negative_windows_without_rows": sorted(
            set(p["null_id"]) - set(rows["null_id"])
        ),
        "policy": (
            "Every admitted training-negative window is expanded to its exact "
            "object-timestep feature records; no automatic truth inference."
        ),
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--promoted", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    rows, summary = build(
        pd.read_csv(args.features),
        pd.read_csv(args.promoted),
    )
    output = Path(args.output)
    summary_path = Path(args.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(output, index=False)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote reviewed-negative object manifest: {output}")


if __name__ == "__main__":
    main()
