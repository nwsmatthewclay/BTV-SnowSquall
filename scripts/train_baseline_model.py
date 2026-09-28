"""Train and evaluate a case-held-out baseline snow-squall onset model.

The evaluator uses Leave-One-Group-Out cross-validation where the group is the
historical case or null window, never an individual row. This prevents
consecutive observations from the same event from being split across train/test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_dataset(frame: pd.DataFrame, schema: dict, target: str):
    if target not in frame.columns:
        raise ValueError(f"Target column not found: {target}")

    d = frame.copy()
    positive_population = d["population"].eq("verified_case_context")
    null_population = d["population"].eq("winter_null_candidate")

    # Conservative labels for the first baseline:
    #   - positives are verified prospective-onset rows
    #   - negatives are candidate-null rows or associated case-context rows
    #     where the onset target is explicitly zero
    # Forecast-training rows must represent a state that existed before the
    # verified onset. Post-onset observations are not valid negative examples.
    pre_onset_case = (
        d["label_status"].isin(["prospective_positive", "case_associated_nonimpact"])
        if "label_status" in d.columns
        else pd.Series(False, index=d.index)
    )
    positive_rows = positive_population & pre_onset_case & d[target].eq(1)
    associated_negative_rows = (
        positive_population
        & d["track_event_associated"].fillna(False)
        & pre_onset_case
        & d[target].eq(0)
    )
    null_negative_rows = null_population & d[target].eq(0)
    usable = positive_rows | associated_negative_rows | null_negative_rows
    d = d.loc[usable].copy()

    if d.empty:
        raise ValueError("No usable labeled rows remain for baseline training.")

    predictor_cols = [
        c for c in schema["predictor_columns"]
        if c in d.columns and pd.api.types.is_numeric_dtype(d[c])
    ]
    if not predictor_cols:
        raise ValueError("No numeric predictor columns remain after schema filtering.")

    d[predictor_cols] = d[predictor_cols].replace([np.inf, -np.inf], np.nan)

    # A model cannot consume all-NaN columns.
    predictor_cols = [
        c for c in predictor_cols if not d[c].isna().all()
    ]
    if not predictor_cols:
        raise ValueError("Every predictor is missing in the training population.")

    group_case = d["case_id"].fillna("")
    group_null = d["null_id"].fillna("")
    d["split_group"] = np.where(
        positive_population.loc[d.index],
        "case:" + group_case.astype(str),
        "null:" + group_null.astype(str),
    )
    if d["split_group"].nunique() < 3:
        raise ValueError("Need at least 3 independent case/null groups for evaluation.")

    return d, predictor_cols


def evaluate(frame: pd.DataFrame, predictor_cols: list[str], target: str):
    logo = LeaveOneGroupOut()
    X = frame[predictor_cols]
    y = frame[target].astype(int).to_numpy()
    groups = frame["split_group"].to_numpy()

    oof = np.full(len(frame), np.nan)
    fold_rows = []

    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups), start=1):
        train_y = y[train_idx]
        if len(np.unique(train_y)) < 2:
            fold_rows.append({
                "fold": fold,
                "held_out_group": groups[test_idx][0],
                "status": "skipped_single_class_training",
            })
            continue

        model = HistGradientBoostingClassifier(
            learning_rate=0.08,
            max_iter=200,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=42,
        )
        model.fit(X.iloc[train_idx], train_y)
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
        fold_rows.append({
            "fold": fold,
            "held_out_group": groups[test_idx][0],
            "test_rows": int(len(test_idx)),
            "test_positives": int(y[test_idx].sum()),
            "status": "ok",
        })

    valid = np.isfinite(oof)
    metrics = {
        "evaluated_rows": int(valid.sum()),
        "positive_rows": int(y[valid].sum()),
        "negative_rows": int((1 - y[valid]).sum()),
        "folds": len(fold_rows),
        "auc_roc": (
            float(roc_auc_score(y[valid], oof[valid]))
            if len(np.unique(y[valid])) == 2 else None
        ),
        "average_precision": (
            float(average_precision_score(y[valid], oof[valid]))
            if y[valid].sum() > 0 else None
        ),
        "brier_score": (
            float(brier_score_loss(y[valid], oof[valid]))
            if valid.any() else None
        ),
    }

    return oof, metrics, fold_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features_csv")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--target", default="squall_onset_within_15m")
    parser.add_argument("--output-dir", default="data/derived/baseline_model")
    args = parser.parse_args()

    source = pd.read_csv(args.features_csv)
    schema = load_schema(Path(args.schema))
    data, predictors = prepare_dataset(source, schema, args.target)

    oof, metrics, folds = evaluate(data, predictors, args.target)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions = data[
        ["split_group", "population", "case_id", "null_id", "radar_site", "object_id", "scan_time_utc", args.target]
    ].copy()
    predictions["oof_probability"] = oof
    predictions.to_csv(output_dir / "oof_predictions.csv", index=False)

    final_model = HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=200,
        max_leaf_nodes=15,
        l2_regularization=1.0,
        random_state=42,
    )
    final_model.fit(data[predictors], data[args.target].astype(int))
    joblib.dump(final_model, output_dir / "baseline_model.joblib")

    report = {
        "model_version": "baseline_hist_gradient_boosting_v1",
        "target": args.target,
        "future_information_policy": schema["future_information_policy"],
        "predictor_columns": predictors,
        "training_rows": int(len(data)),
        "training_groups": int(data["split_group"].nunique()),
        "metrics": metrics,
        "folds": folds,
        "negative_label_policy": (
            "winter_null_candidate OR pre-onset associated case-context row with explicit target zero"
        ),
        "post_onset_exclusion_policy": (
            "verified_event_interval rows are excluded from baseline forecast training"
        ),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Baseline rows: {len(data)}")
    print(f"Independent groups: {data['split_group'].nunique()}")
    print(f"Predictors: {len(predictors)}")
    print("Metrics:", json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
