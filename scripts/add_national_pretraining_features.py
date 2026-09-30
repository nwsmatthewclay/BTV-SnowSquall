"""Add BTV-safe features from a BTV-excluded national weak radar pretrainer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HORIZONS = (15, 30, 45, 60)


def augment(frame: pd.DataFrame, model_root: Path) -> tuple[pd.DataFrame, dict]:
    out = frame.copy()
    summary = {}
    for horizon in HORIZONS:
        root = model_root / f"national_sqw_weak_model_{horizon}m"
        model_path = root / "weak_pretraining_model.joblib"
        metrics_path = root / "metrics.json"
        feature_name = f"national_pretrain_probability_{horizon}m"
        if not model_path.exists() or not metrics_path.exists():
            summary[str(horizon)] = {"status": "not_available"}
            continue
        metadata = json.loads(metrics_path.read_text(encoding="utf-8"))
        predictors = list(metadata.get("predictor_columns") or [])
        working = pd.DataFrame(index=out.index)
        missing = []
        for column in predictors:
            if column in out.columns:
                working[column] = pd.to_numeric(out[column], errors="coerce")
            else:
                working[column] = np.nan
                missing.append(column)
        model = joblib.load(model_path)
        probabilities = model.predict_proba(working[predictors])[:, 1]
        out[feature_name] = probabilities
        summary[str(horizon)] = {
            "status": "applied",
            "predictor_count": len(predictors),
            "missing_source_predictors": missing,
            "model_version": metadata.get("model_version"),
            "excluded_wfo": metadata.get("excluded_wfo"),
        }
    return out, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    frame = pd.read_csv(args.features)
    augmented, summary = augment(frame, Path(args.model_root))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    augmented.to_csv(args.output, index=False)
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    applied = [h for h, info in summary.items() if info["status"] == "applied"]
    print(json.dumps({"applied_horizons": applied, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
