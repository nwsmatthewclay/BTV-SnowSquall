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
        else positive_population
    )

    # Enforce the forecast-time boundary independently of label_status. A
    # post-event row must never enter training just because it was otherwise
    # categorized as case-associated nonimpact.
    if {"scan_time_utc", "case_event_start_utc"}.issubset(d.columns):
        scan_dt = pd.to_datetime(d["scan_time_utc"], utc=True, errors="coerce")
        onset_dt = pd.to_datetime(d["case_event_start_utc"], utc=True, errors="coerce")
        pre_onset_case = pre_onset_case & (
            ~positive_population | onset_dt.isna() | (scan_dt < onset_dt)
        )
    positive_rows = positive_population & pre_onset_case & d[target].eq(1)
    associated_negative_rows = (
        positive_population
        & d["track_event_associated"].fillna(False)
        & pre_onset_case
        & d[target].eq(0)
    )
    # Null-window rows are provisional negative context by design. They do not
    # have a future outcome label, so their target columns are NaN in the
    # unified table. Treat the null population as class 0 only after selecting
    # it here, rather than filtering on target==0.
    null_negative_rows = null_population
    usable = positive_rows | associated_negative_rows | null_negative_rows
    d = d.loc[usable].copy()

    if d.empty:
        raise ValueError("No usable labeled rows remain for baseline training.")

    # Materialize the provisional-null target after row selection so sklearn
    # receives a complete binary y vector.
    d.loc[d["population"].eq("winter_null_candidate"), target] = 0

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


def grouped_bootstrap_intervals(y, probability, groups, n_boot=500, seed=42):
    rng = np.random.default_rng(seed)
    unique_groups = np.asarray(sorted(set(groups)))
    if unique_groups.size < 3:
        return {}
    group_arrays = {g: np.flatnonzero(np.asarray(groups) == g) for g in unique_groups}
    aucs, aps, briers = [], [], []
    for _ in range(n_boot):
        sample_groups = rng.choice(unique_groups, size=unique_groups.size, replace=True)
        idx = np.concatenate([group_arrays[g] for g in sample_groups])
        yb = np.asarray(y)[idx]
        pb = np.asarray(probability)[idx]
        if len(np.unique(yb)) < 2:
            continue
        aucs.append(roc_auc_score(yb, pb))
        aps.append(average_precision_score(yb, pb))
        briers.append(brier_score_loss(yb, pb))
    def interval(values):
        if not values:
            return {'lower': None, 'median': None, 'upper': None, 'samples': 0}
        q = np.percentile(values, [2.5, 50, 97.5])
        return {'lower': float(q[0]), 'median': float(q[1]), 'upper': float(q[2]), 'samples': len(values)}
    return {
        'method': 'grouped_case_or_null_bootstrap',
        'group_count': int(unique_groups.size),
        'auc_roc': interval(aucs),
        'average_precision': interval(aps),
        'brier_score': interval(briers),
    }
def evaluate(frame: pd.DataFrame, predictor_cols: list[str], target: str):
    logo = LeaveOneGroupOut()
    X = frame[predictor_cols]
    y = frame[target].astype(int).to_numpy()
    groups = frame["split_group"].to_numpy()

    oof = np.full(len(frame), np.nan)
    climatology_oof = np.full(len(frame), np.nan)
    fold_rows = []

    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups), start=1):
        train_y = y[train_idx]
        climatology_oof[test_idx] = float(train_y.mean())
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
    climatology_valid = np.isfinite(climatology_oof)
    bootstrap = grouped_bootstrap_intervals(y[valid], oof[valid], groups[valid])
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
        "grouped_bootstrap_95pct": bootstrap,
        "climatology": {
            "brier_score": (
                float(brier_score_loss(y[climatology_valid], climatology_oof[climatology_valid]))
                if climatology_valid.any() else None
            ),
            "average_probability": (
                float(climatology_oof[climatology_valid].mean())
                if climatology_valid.any() else None
            ),
        },
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

    positive_case_groups = sorted(
        data.loc[data[args.target].eq(1), "split_group"].dropna().astype(str).unique()
    )
    positive_case_group_count = len(positive_case_groups)

    fold_status_counts = {}
    for fold in folds:
        status = fold.get("status", "unknown")
        fold_status_counts[status] = fold_status_counts.get(status, 0) + 1

    report = {
        "model_version": "baseline_hist_gradient_boosting_v1",
        "dataset_revision": str(args.features_csv),
        "schema_revision": str(args.schema),
        "target": args.target,
        "future_information_policy": schema["future_information_policy"],
        "predictor_columns": predictors,
        "training_rows": int(len(data)),
        "training_groups": int(data["split_group"].nunique()),
        "location_predictor_policy": schema.get("location_predictor_policy", "unspecified"),
        "evaluation_unit": "case_or_null_group",
        "training_class_counts": {
            "positive": int(data[args.target].sum()),
            "negative": int((1 - data[args.target]).sum()),
        },
        "positive_case_groups": positive_case_groups,
        "positive_case_group_count": positive_case_group_count,
        "evaluation_status": (
            "case_held_out_not_interpretable"
            if positive_case_group_count < 3
            else "case_held_out_exploratory"
        ),
        "evaluation_note": (
            "Fewer than three independent historical case groups contain positive "
            "forecast labels; holdout metrics must not be interpreted as model skill."
            if positive_case_group_count < 3
            else "Exploratory case-held-out evaluation; not operational verification."
        ),
        "fold_status_counts": fold_status_counts,
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
    print("Positive case groups:", positive_case_groups)
    print("Evaluation status:", "case_held_out_not_interpretable" if positive_case_group_count < 3 else "case_held_out_exploratory")
    print("Metrics:", json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
