"""Fit a Platt-style probability calibrator to grouped out-of-fold predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


def fit_calibrator(model_dir: Path):
    metrics_path = model_dir / "metrics.json"
    pred_path = model_dir / "oof_predictions.csv"
    if not metrics_path.exists() or not pred_path.exists():
        raise FileNotFoundError(f"Missing model metrics or OOF predictions in {model_dir}")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    predictions = pd.read_csv(pred_path)
    probability_col = "oof_probability"
    target = metrics.get("target")
    if probability_col not in predictions or not target or target not in predictions:
        raise ValueError("OOF predictions must contain oof_probability and the target column")
    y = pd.to_numeric(predictions[target], errors="coerce")
    p = pd.to_numeric(predictions[probability_col], errors="coerce")
    mask = y.notna() & p.notna()
    y = y.loc[mask].astype(int)
    p = p.loc[mask].clip(1e-6, 1 - 1e-6)
    if len(y) < 30 or y.nunique() < 2 or y.sum() < 5 or (1 - y).sum() < 5:
        raise ValueError(f"Insufficient OOF data for calibration: rows={len(y)}, positives={int(y.sum())}")
    logits = np.log(p / (1.0 - p)).to_numpy().reshape(-1, 1)
    calibrator = LogisticRegression(C=10.0, max_iter=2000, solver="lbfgs")
    calibrator.fit(logits, y.to_numpy())
    joblib.dump(calibrator, model_dir / "probability_calibrator.joblib")
    metadata = {
        "calibration_method": "platt_logistic_on_grouped_oof_logit",
        "calibration_rows": int(len(y)),
        "calibration_positive_rows": int(y.sum()),
        "calibration_negative_rows": int((1 - y).sum()),
        "calibration_target": target,
        "calibration_status": "fit_on_oof_research_data",
    }
    metrics.update(metadata)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()
    fit_calibrator(Path(args.model_dir))


if __name__ == "__main__":
    main()
