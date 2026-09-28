"""Audit historical training labels and flag ambiguous records.

This is a QC gate, not a trainer. It prevents accidental use of unknown or
future-contaminated examples and reports class/coverage statistics.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

HORIZONS = (15, 30, 45, 60)


def audit(path: Path):
    df = pd.read_csv(path)
    required = ["scan_time_utc", "object_id", "label_status"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    issues = []

    if df["scan_time_utc"].isna().any():
        issues.append("records_missing_scan_time")

    if df["object_id"].isna().any():
        issues.append("records_missing_object_id")

    known = {
        "prospective_positive",
        "verified_event_interval",
        "case_associated_nonimpact",
        "unassociated_object",
        "unknown",
        "candidate_null",
    }
    unexpected = sorted(set(df["label_status"].dropna()) - known)
    if unexpected:
        issues.append(f"unexpected_label_status:{unexpected}")

    # A prospective positive must have at least one positive future horizon.
    pos = df["label_status"].eq("prospective_positive")
    onset_cols = [f"squall_onset_within_{h}m" for h in HORIZONS]
    if all(c in df for c in onset_cols):
        bad = pos & (df[onset_cols].sum(axis=1) == 0)
        if bad.any():
            issues.append(f"prospective_positive_without_future_onset:{int(bad.sum())}")

    # Future targets must be binary.
    for c in onset_cols + [f"squall_ongoing_within_{h}m" for h in HORIZONS]:
        if c in df:
            values = set(pd.to_numeric(df[c], errors="coerce").dropna().unique())
            if not values.issubset({0, 1}):
                issues.append(f"nonbinary_target:{c}")

    summary = {
        "records": len(df),
        "unique_objects": int(df["object_id"].nunique()),
        "label_status_counts": df["label_status"].value_counts(dropna=False).to_dict(),
        "issues": issues,
    }

    for h in HORIZONS:
        c = f"squall_onset_within_{h}m"
        if c in df:
            summary[f"onset_{h}m_positive"] = int(pd.to_numeric(df[c], errors="coerce").fillna(0).sum())

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    summary = audit(Path(args.input_csv))
    print("Historical dataset QC")
    print("=====================")
    for key, value in summary.items():
        print(f"{key}: {value}")

    if summary["issues"]:
        raise SystemExit("QC FAILED")


if __name__ == "__main__":
    main()
