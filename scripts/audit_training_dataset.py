"""Audit historical training labels and flag ambiguous records.

This is a QC gate, not a trainer. It prevents accidental use of unknown or
future-contaminated examples and reports class/coverage statistics.
"""
from __future__ import annotations

import argparse
import json
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
        "event_onset_no_verified_end",
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

    # Future targets must be binary, and the table must contain actual
    # supervised onset labels. A successful file write is not evidence of
    # model-ingestible data.
    target_stats = {}
    for c in onset_cols + [f"squall_ongoing_within_{h}m" for h in HORIZONS]:
        if c not in df:
            if c in onset_cols:
                issues.append(f"missing_required_onset_target:{c}")
            continue
        numeric = pd.to_numeric(df[c], errors="coerce")
        values = set(numeric.dropna().unique())
        if not values.issubset({0, 1}):
            issues.append(f"nonbinary_target:{c}")
        target_stats[c] = {
            "known": int(numeric.notna().sum()),
            "positive": int((numeric == 1).sum()),
            "negative": int((numeric == 0).sum()),
        }

    if not any(target_stats.get(c, {}).get("known", 0) > 0 for c in onset_cols):
        issues.append("no_known_onset_targets_any_horizon")

    # A positive onset at a shorter horizon must also be positive at longer horizons.
    for short_h, long_h in zip(HORIZONS[:-1], HORIZONS[1:]):
        short_col = f"squall_onset_within_{short_h}m"
        long_col = f"squall_onset_within_{long_h}m"
        if short_col in df and long_col in df:
            short = pd.to_numeric(df[short_col], errors="coerce")
            long = pd.to_numeric(df[long_col], errors="coerce")
            contradiction = short.eq(1) & long.eq(0)
            if contradiction.any():
                issues.append(
                    f"nonmonotone_onset_horizons:{short_h}m_to_{long_h}m:{int(contradiction.sum())}"
                )

    # Duplicate object-scan identities inflate samples and risk train/test leakage.
    if {"scan_time_utc", "object_id"}.issubset(df.columns):
        duplicate_identity = df.duplicated(["scan_time_utc", "object_id"], keep=False)
        if duplicate_identity.any():
            issues.append(f"duplicate_object_scan_identity:{int(duplicate_identity.sum())}")

    # Unknown or unrelated objects must not be silently used as negatives.
    unknown_status = df["label_status"].isin(["unassociated_object", "unknown", "candidate_null"])
    for c in onset_cols:
        if c in df:
            known_unknown = unknown_status & pd.to_numeric(df[c], errors="coerce").notna()
            if known_unknown.any():
                issues.append(f"unknown_population_has_supervised_target:{c}:{int(known_unknown.sum())}")

    summary = {
        "records": len(df),
        "unique_objects": int(df["object_id"].nunique()),
        "unique_cases": int(df["case_id"].nunique()) if "case_id" in df else None,
        "unique_split_groups": int(df["split_group"].nunique()) if "split_group" in df else None,
        "duplicate_object_scan_rows": int(df.duplicated(["scan_time_utc", "object_id"], keep=False).sum()),
        "label_status_counts": df["label_status"].value_counts(dropna=False).to_dict(),
        "target_stats": target_stats,
        "issues": issues,
    }

    for h in HORIZONS:
        c = f"squall_onset_within_{h}m"
        if c in df:
            numeric = pd.to_numeric(df[c], errors="coerce")
            summary[f"onset_{h}m_positive"] = int((numeric == 1).sum())
            summary[f"onset_{h}m_negative"] = int((numeric == 0).sum())
            summary[f"onset_{h}m_known"] = int(numeric.notna().sum())

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

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"Report written: {report_path}")

    if summary["issues"]:
        raise SystemExit("QC FAILED")


if __name__ == "__main__":
    main()
