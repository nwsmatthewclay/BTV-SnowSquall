"""Build a transparent probabilistic verification report from out-of-sample predictions.

The report is intentionally model-agnostic. It includes discrimination,
probabilistic error, reliability, threshold confusion counts, and lead-time
summary when an event-time column is available. It never selects an operational
threshold or declares a model successful.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)


def reliability_table(y_true, probability, bins: int = 10):
    edges = np.linspace(0.0, 1.0, bins + 1)
    frame = pd.DataFrame({"y": y_true, "p": probability})
    frame["bin"] = pd.cut(
        frame["p"].clip(0.0, 1.0),
        bins=edges,
        include_lowest=True,
        labels=False,
    )
    grouped = (
        frame.groupby("bin", dropna=False)
        .agg(
            count=("y", "size"),
            observed_frequency=("y", "mean"),
            mean_probability=("p", "mean"),
        )
        .reset_index()
    )
    grouped["abs_calibration_error"] = (
        grouped["observed_frequency"] - grouped["mean_probability"]
    ).abs()
    return grouped


def verify(
    frame: pd.DataFrame,
    target: str,
    probability: str,
    probability_bins: int = 10,
    thresholds: tuple[float, ...] = (0.1, 0.2, 0.3, 0.5),
):
    y = pd.to_numeric(frame[target], errors="coerce")
    p = pd.to_numeric(frame[probability], errors="coerce")
    valid = y.notna() & p.notna() & p.between(0.0, 1.0)
    d = frame.loc[valid].copy()
    y = y.loc[valid].astype(int).to_numpy()
    p = p.loc[valid].astype(float).to_numpy()

    if len(y) == 0:
        raise ValueError("No valid prediction rows remain.")
    if len(np.unique(y)) < 2:
        raise ValueError("Verification requires both observed classes.")

    reliability = reliability_table(y, p, bins=probability_bins)
    overall = {
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "negatives": int((1 - y).sum()),
        "positive_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier_score": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "reliability_bins": int(probability_bins),
        "mean_absolute_calibration_error": float(
            reliability["abs_calibration_error"].mean()
        ),
    }

    threshold_rows = []
    for threshold in thresholds:
        predicted = (p >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
        threshold_rows.append({
            "threshold": float(threshold),
            "true_positive": int(tp),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_negative": int(tn),
            "pod": float(tp / (tp + fn)) if tp + fn else None,
            "far": float(fp / (tp + fp)) if tp + fp else None,
            "base_rate": float(y.mean()),
            "forecast_rate": float(predicted.mean()),
        })

    report = {
        "verification_version": "probabilistic_verification_v1",
        "future_information_policy": "out_of_sample_predictions_only",
        "target": target,
        "probability_column": probability,
        "status": "exploratory_unless_independent_verification_population_is_confirmed",
        "overall": overall,
        "threshold_diagnostics": threshold_rows,
        "reliability": reliability.to_dict(orient="records"),
    }

    if {"scan_time_utc", "truth_onset_time"}.issubset(d.columns):
        scan = pd.to_datetime(d["scan_time_utc"], utc=True, errors="coerce")
        onset = pd.to_datetime(d["truth_onset_time"], utc=True, errors="coerce")
        lead = (onset - scan).dt.total_seconds().div(60.0)
        report["lead_time"] = {
            "rows_with_verified_onset": int(lead.notna().sum()),
            "median_min": float(lead.median()) if lead.notna().any() else None,
            "mean_min": float(lead.mean()) if lead.notna().any() else None,
            "p10_min": float(lead.quantile(0.10)) if lead.notna().any() else None,
            "p90_min": float(lead.quantile(0.90)) if lead.notna().any() else None,
        }

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions_csv")
    parser.add_argument("--target", required=True)
    parser.add_argument("--probability", default="oof_probability")
    parser.add_argument("--output", required=True)
    parser.add_argument("--bins", type=int, default=10)
    args = parser.parse_args()

    frame = pd.read_csv(args.predictions_csv)
    report = verify(
        frame,
        target=args.target,
        probability=args.probability,
        probability_bins=args.bins,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["overall"], indent=2))


if __name__ == "__main__":
    main()
