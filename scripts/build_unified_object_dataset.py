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


def build(positive_csv: Path, null_csv: Path, output_csv: Path):
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

    columns = list(dict.fromkeys(list(positive.columns) + list(nulls.columns)))
    positive = positive.reindex(columns=columns)
    nulls = nulls.reindex(columns=columns)

    combined = pd.concat([positive, nulls], ignore_index=True)
    combined["dataset_version"] = "object_population_pilot_v1"
    combined["future_information_policy"] = "past_and_current_only"
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
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.positive_csv), Path(args.null_csv), Path(args.output))


if __name__ == "__main__":
    main()
