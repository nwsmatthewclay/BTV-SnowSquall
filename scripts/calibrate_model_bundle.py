"""Fit research-only Platt calibrators from case-held-out OOF predictions.

This creates calibration artifacts for analysis only. It does not certify
calibration and must not be wired into operational scoring without independent
temporal/case-held-out reliability evaluation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


def fit_calibrators(model_dir: Path, min_rows: int = 30, min_per_class: int = 5):
    metrics_path = model_dir / "metrics.json"
    pred_path = model_dir / "oof_predictions.csv"
    if not metrics_path.exists() or not pred_path.exists():
        raise FileNotFoundError(f"Missing model metrics or OOF predictions in {model_dir}")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    predictions = pd.read_csv(pred_path)
    required = {"horizon_min", "target", "target_value", "oof_probability", "split_group", "fold"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(f"OOF predictions missing required fields: {missing}")

    calibrators = {}
    report = {
        "status": "research_only_not_independently_validated",
        "source": "case_grouped_out_of_fold_predictions",
        "independent_test_used_for_fit": False,
        "horizons": {},
    }
    for horizon in (15, 30, 45, 60):
        frame = predictions[pd.to_numeric(predictions["horizon_min"], errors="coerce").eq(horizon)].copy()
        y = pd.to_numeric(frame["target_value"], errors="coerce")
        p = pd.to_numeric(frame["oof_probability"], errors="coerce")
        mask = y.isin([0, 1]) & p.between(0, 1) & frame["split_group"].notna() & frame["fold"].notna()
        y = y.loc[mask].astype(int)
        p = p.loc[mask].clip(1e-6, 1 - 1e-6)
        positives = int(y.sum())
        negatives = int((1-y).sum())
        item = {
            "rows": int(len(y)),
            "positive_rows": positives,
            "negative_rows": negatives,
            "groups": int(frame.loc[mask, "split_group"].nunique()),
            "folds": int(frame.loc[mask, "fold"].nunique()),
            "method": "platt_logistic_on_oof_logit",
        }
        if len(y) < min_rows or positives < min_per_class or negatives < min_per_class:
            item["status"] = "insufficient_data"
            report["horizons"][str(horizon)] = item
            continue
        logits = np.log(p / (1.0-p)).to_numpy().reshape(-1, 1)
        calibrator = LogisticRegression(C=10.0, max_iter=2000, solver="lbfgs")
        calibrator.fit(logits, y.to_numpy())
        calibrators[str(horizon)] = calibrator
        item["status"] = "fit_research_artifact"
        item["target"] = f"squall_onset_within_{horizon}m"
        report["horizons"][str(horizon)] = item

    if calibrators:
        joblib.dump(calibrators, model_dir / "probability_calibrators_research.joblib")
    (model_dir / "calibration_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--min-rows", type=int, default=30)
    parser.add_argument("--min-per-class", type=int, default=5)
    args = parser.parse_args()
    fit_calibrators(Path(args.model_dir), args.min_rows, args.min_per_class)


if __name__ == "__main__":
    main()
