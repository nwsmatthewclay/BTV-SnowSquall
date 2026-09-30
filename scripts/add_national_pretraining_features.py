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
            summary[f"{horizon}m"] = {"status": "not_available"}
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
        probabilities = np.asarray(model.predict_proba(working[predictors]), dtype=float)[:, 1]
        out[feature_name] = probabilities
        summary[f"{horizon}m"] = {
            "status": "applied",
            "predictor_count": len(predictors),
            "missing_source_predictors": missing,
            "model_version": metadata.get("model_version"),
            "excluded_wfo": metadata.get("excluded_wfo"),
        }
    return out, summary


def update_schema(schema_path: Path, summary: dict):
    if not schema_path.exists():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for horizon, info in summary.items():
        if info.get("status") != "applied":
            continue
        column = f"national_pretrain_probability_{horizon}m"
        predictors = list(schema.get("predictor_columns") or [])
        operational = list(schema.get("operational_predictor_columns") or [])
        if column not in predictors:
            predictors.append(column)
        if column not in operational:
            operational.append(column)
        schema["predictor_columns"] = predictors
        schema["operational_predictor_columns"] = operational
    schema["national_pretraining_policy"] = "BTV-excluded weak radar prior; research-only feature"
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()

    frame = pd.read_csv(args.features)
    augmented, summary = augment(frame, Path(args.model_root))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    augmented.to_csv(args.output, index=False)
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.schema:
        update_schema(Path(args.schema), summary)
    applied = [h for h, info in summary.items() if info["status"] == "applied"]
    print(json.dumps({"applied_horizons": applied, "summary": summary}, indent=2))

if __name__ == "__main__":
    main()
