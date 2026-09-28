"""Aggregate out-of-fold probabilities to event/window level.

This is a diagnostic companion to row-wise verification. It prevents long-lived
tracks from dominating threshold counts simply because they contribute many
rows. Max probability is intentionally reported as a diagnostic; it is not an
operational threshold selection procedure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build(frame: pd.DataFrame, target: str, probability: str,
          thresholds=(0.1, 0.2, 0.3, 0.5)) -> dict:
    required = {"population", "case_id", "null_id", target, probability}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing event-level verification columns: {missing}")

    d = frame.copy()
    d[target] = pd.to_numeric(d[target], errors="coerce")
    d[probability] = pd.to_numeric(d[probability], errors="coerce")
    d = d[d[target].notna() & d[probability].notna()].copy()
    d = d[d[probability].between(0.0, 1.0)].copy()

    positive = d[d["population"] == "verified_case_context"].copy()
    null = d[d["population"] == "winter_null_candidate"].copy()

    positive["group_id"] = positive["case_id"].astype(str)
    null["group_id"] = null["null_id"].astype(str)

    def summarize(grouped):
        if grouped.empty:
            return []
        top = (
            grouped.groupby("group_id", dropna=False)[probability]
            .agg(max_probability="max", mean_probability="mean", rows="size")
            .reset_index()
        )
        top = top.sort_values("max_probability", ascending=False)
        return top.to_dict(orient="records")

    positive_groups = summarize(positive)
    null_groups = summarize(null)

    threshold_rows = []
    positive_max = pd.Series([x["max_probability"] for x in positive_groups], dtype="float64")
    null_max = pd.Series([x["max_probability"] for x in null_groups], dtype="float64")

    for threshold in thresholds:
        hit_positive = int((positive_max >= threshold).sum())
        hit_null = int((null_max >= threshold).sum())
        threshold_rows.append({
            "threshold": float(threshold),
            "positive_cases_detected": hit_positive,
            "positive_case_count": int(len(positive_max)),
            "case_detection_fraction": float(hit_positive / len(positive_max))
            if len(positive_max) else None,
            "null_windows_triggered": hit_null,
            "null_window_count": int(len(null_max)),
            "null_window_alert_fraction": float(hit_null / len(null_max))
            if len(null_max) else None,
        })

    return {
        "verification_version": "event_level_verification_v1",
        "interpretation": "diagnostic_only; max_probability_aggregation_can_depend_on_object_multiplicity",
        "target": target,
        "probability_column": probability,
        "positive_case_count": len(positive_groups),
        "null_window_count": len(null_groups),
        "positive_cases": positive_groups,
        "null_windows": null_groups,
        "threshold_diagnostics": threshold_rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions_csv")
    parser.add_argument("--target", required=True)
    parser.add_argument("--probability", default="oof_probability")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    frame = pd.read_csv(args.predictions_csv)
    report = build(frame, args.target, args.probability)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Cases={report['positive_case_count']} "
        f"NullWindows={report['null_window_count']}"
    )


if __name__ == "__main__":
    main()
