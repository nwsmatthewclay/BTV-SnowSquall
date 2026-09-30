"""Score candidate snow-squall models on an independent validation population."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from scripts.model_runtime import ModelRuntime

HORIZONS = (15, 30, 45, 60)

def expected_calibration_error(y, p, bins=10):
    y = pd.Series(y).astype(float)
    p = pd.Series(p).astype(float).clip(0.0, 1.0)
    edges = [i / bins for i in range(bins + 1)]
    ece = 0.0
    total = float(len(y))
    rows = []
    if total == 0:
        return 0.0, rows
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (p >= left) & ((p < right) if right < 1 else (p <= right))
        n = int(mask.sum())
        if not n:
            continue
        mean_p = float(p[mask].mean())
        mean_y = float(y[mask].mean())
        ece += (n / total) * abs(mean_p - mean_y)
        rows.append({"lower": left, "upper": right, "n": n, "mean_probability": mean_p, "observed_frequency": mean_y})
    return float(ece), rows


def score_one(features: pd.DataFrame, model_dir: Path, target: str):
    runtime = ModelRuntime.load(model_dir)
    if runtime.model is None:
        return None, {"status": "model_missing"}
    frame = features.copy()
    for column in runtime.feature_columns:
        if column not in frame.columns:
            frame[column] = float("nan")
    probabilities = runtime.score_candidate(frame)
    p = pd.Series(probabilities, index=features.index, dtype='float64')
    if target not in features.columns:
        return probabilities, {
            "status": "unscored_no_observed_target",
            "evaluated_rows": 0,
            "positive_rows": 0,
            "negative_rows": 0,
            "prediction_mean": float(p.mean()) if len(p) else None,
            "note": f"Independent validation inventory intentionally contains no future outcome column: {target}",
        }
    y = pd.to_numeric(features[target], errors='coerce')
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
        "climatology_brier_score": None,
        "brier_skill_vs_climatology": None,
        "expected_calibration_error": None,
    }
    if len(y):
        climatology = float(y.mean())
        metrics["climatology_brier_score"] = float(brier_score_loss(y, pd.Series(climatology, index=y.index)))
        if metrics["climatology_brier_score"] > 0:
            metrics["brier_skill_vs_climatology"] = 1.0 - metrics["brier_score"] / metrics["climatology_brier_score"]
        edges = [i / 10.0 for i in range(11)]
        ece = 0.0
        for left, right in zip(edges[:-1], edges[1:]):
            in_bin = (p >= left) & ((p < right) if right < 1 else (p <= right))
            if in_bin.any():
                ece += float(in_bin.mean()) * abs(float(p[in_bin].mean()) - float(y[in_bin].mean()))
        metrics["expected_calibration_error"] = float(ece)
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
        ensemble_dir = Path(args.model_root) / f'candidate_ensemble_expansion_{horizon}m'
        baseline_dir = Path(args.model_root) / f'baseline_expansion_{horizon}m'
        model_dir = ensemble_dir if (ensemble_dir / 'baseline_model.joblib').exists() else baseline_dir
        probabilities, metrics = score_one(features, model_dir, target)
        metrics['selected_model_dir'] = model_dir.name
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
