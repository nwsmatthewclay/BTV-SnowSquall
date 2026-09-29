"""Create one common object-level dataset from positive-context and null populations.

Null objects remain candidate negatives until radar/event QC is complete.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

POPULATION_FIELDS = [
    "population",
    "truth_status",
    "label_status",
    "case_id",
    "null_id",
    "source_study",
]


def prepare(frame, population, truth_status, source_column):
    out = frame.copy()
    out["population"] = population
    out["truth_status"] = truth_status
    if source_column not in out:
        out[source_column] = None
    for col in POPULATION_FIELDS:
        if col not in out:
            out[col] = None
    return out


def build(
    positive_csv: Path,
    null_csv: Path,
    output_csv: Path,
    null_activity_csv: Path | None = None,
):
    positive = prepare(
        pd.read_csv(positive_csv),
        "verified_case_context",
        "case_context_not_final_object_truth",
        "source_study",
    )
    nulls = prepare(
        pd.read_csv(null_csv),
        "winter_null_candidate",
        "unverified_null_candidate",
        "null_id",
    )
    if null_activity_csv is not None:
        activity = pd.read_csv(null_activity_csv)
        required_activity = {"null_id", "activity_class"}
        missing_activity = required_activity - set(activity.columns)
        if missing_activity:
            raise ValueError(
                f"Null activity file missing columns: {sorted(missing_activity)}"
            )
        activity = activity[["null_id", "activity_class"]].drop_duplicates("null_id")
        nulls = nulls.drop(columns=["activity_class"], errors="ignore").merge(
            activity,
            on="null_id",
            how="left",
            validate="many_to_one",
        )

    columns = list(dict.fromkeys(list(positive.columns) + list(nulls.columns)))
    positive = positive.reindex(columns=columns)
    nulls = nulls.reindex(columns=columns)

    combined = pd.concat([positive, nulls], ignore_index=True)
    combined["dataset_version"] = "object_population_pilot_v1"
    combined["future_information_policy"] = "current_and_past_only"
    radar_series = (
        combined["radar_site"].astype(str)
        if "radar_site" in combined.columns
        else pd.Series("", index=combined.index, dtype="object")
    )
    object_series = (
        combined["object_id"].astype(str)
        if "object_id" in combined.columns
        else pd.Series("", index=combined.index, dtype="object")
    )
    case_identity = combined["case_id"].fillna("").astype(str)
    null_identity = combined["null_id"].fillna("").astype(str)
    source_identity = case_identity.where(case_identity.ne(""), null_identity)
    combined["population_track_key"] = (
        combined["population"].astype(str) + ":" + source_identity + ":" + radar_series + ":" + object_series
    )
    combined["row_identity_key"] = (
        combined["population_track_key"]
        + ":"
        + combined["scan_time_utc"].astype(str)
    )
    if combined["row_identity_key"].duplicated().any():
        count = int(combined["row_identity_key"].duplicated().sum())
        raise ValueError(f"Unified dataset contains {count} duplicate object-timestep identities")
    if (combined["population"].eq("verified_case_context") & combined["null_id"].notna()).any():
        raise ValueError("Verified case-context rows must not contain null_id")
    if (combined["population"].eq("winter_null_candidate") & combined["case_id"].notna()).any():
        raise ValueError("Null-candidate rows must not contain case_id")
    combined = combined.sort_values(
        [c for c in ["scan_time_utc", "radar_site", "object_id"] if c in combined.columns]
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_csv, index=False)

    print(f"Wrote {len(combined)} unified object records to {output_csv}")
    print("Population:")
    print(combined["population"].value_counts(dropna=False).to_string())
    print("Truth status:")
    print(combined["truth_status"].value_counts(dropna=False).to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("positive_csv")
    parser.add_argument("null_csv")
    parser.add_argument(
        "--null-activity",
        default=None,
        help="Optional null-window activity classification CSV.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(
        Path(args.positive_csv),
        Path(args.null_csv),
        Path(args.output),
        Path(args.null_activity) if args.null_activity else None,
    )


if __name__ == "__main__":
    main()
