"""Score candidate snow-squall models on an independent validation population."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from scripts.model_runtime import ModelRuntime

HORIZONS = (15, 30, 45, 60)


def score_one(features: pd.DataFrame, model_dir: Path, target: str):
    runtime = ModelRuntime.load(model_dir)
    if runtime.model is None:
        return None, {"status": "model_missing"}
    frame = features.copy()
    for column in runtime.feature_columns:
        if column not in frame.columns:
            frame[column] = float("nan")
    probabilities = runtime.score_candidate(frame)
    y = pd.to_numeric(features[target], errors='coerce')
    p = pd.Series(probabilities, index=features.index, dtype='float64')
    mask = y.notna() & p.notna()
    y = y.loc[mask].astype(int)
    p = p.loc[mask]
    metrics = {
        "evaluated_rows": int(mask.sum()),
        "positive_rows": int(y.sum()),
        "negative_rows": int((1 - y).sum()),
        "roc_auc": float(roc_auc_score(y, p)) if len(y.unique()) == 2 else None,
        "average_precision": float(average_precision_score(y, p)) if y.sum() > 0 else None,
        "brier_score": float(brier_score_loss(y, p)) if len(y) else None,
        "prediction_mean": float(p.mean()) if len(p) else None,
    }
    return probabilities, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('features_csv')
    parser.add_argument('--model-root', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    features = pd.read_csv(args.features_csv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}

    for horizon in HORIZONS:
        target = f'squall_onset_within_{horizon}m'
        model_dir = Path(args.model_root) / f'candidate_expansion_{horizon}m'
        probabilities, metrics = score_one(features, model_dir, target)
        summary[str(horizon)] = metrics
        if probabilities is not None:
            cols = [c for c in ['case_id', 'radar_site', 'object_id', 'scan_time_utc', target] if c in features.columns]
            prediction = features[cols].copy()
            prediction['validation_probability'] = probabilities
            prediction.to_csv(out / f'validation_predictions_{horizon}m.csv', index=False)

    summary["policy"] = "Independent validation only; these rows are never added to model training."
    (out / "validation_metrics.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
