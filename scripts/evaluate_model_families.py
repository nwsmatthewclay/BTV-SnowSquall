"""Compare probability model families on the same leakage-safe case-held-out population.

This evaluator intentionally uses the exact forecast-time rows supplied to the
case-held-out gate rather than applying a second, incompatible label filter.
That makes Logistic, HGB, Random Forest, Extra Trees, and their soft-vote
average directly comparable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HORIZONS = (15, 30, 45, 60)
BLOCKED_PREFIXES = (
    "case_", "label_", "squall_", "track_event_", "association_", "truth_", "surface_",
)
BLOCKED_EXACT = {
    "lead_time_min", "lead_time_to_warning_min", "warning_issue_utc",
    "warning_distance_km", "warning_verifying_lsr_count", "warning_supervision_class",
    "sqw_intersection", "scan_time_utc", "source_file", "radar_site", "object_id",
    "population", "future_information_policy", "environment_status", "environment_source",
    "label_status", "label_reason",
}


def as_binary(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    return series.astype(str).str.strip().str.lower().map(
        {"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0}
    ).astype(float)


def predictors(df: pd.DataFrame, target: str) -> list[str]:
    cols = []
    for col in df.columns:
        if col in BLOCKED_EXACT or col == target or any(col.startswith(p) for p in BLOCKED_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def groups_for(df: pd.DataFrame) -> pd.Series:
    if "case_id" in df.columns:
        return df["case_id"].astype(str)
    return pd.Series(np.arange(len(df)), index=df.index).astype(str)


def folds(groups: pd.Series) -> list[np.ndarray]:
    unique = np.asarray(sorted(groups.dropna().unique()))
    if unique.size < 3:
        return []
    rng = np.random.default_rng(42)
    shuffled = unique.copy()
    rng.shuffle(shuffled)
    n = min(5, unique.size)
    return [shuffled[i::n] for i in range(n)]


def model_specs():
    return {
        "logistic": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(
                max_iter=3000, class_weight="balanced", solver="liblinear", random_state=42,
            )),
        ]),
        "hgb": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", HistGradientBoostingClassifier(
                learning_rate=0.08, max_iter=220, max_leaf_nodes=15,
                l2_regularization=1.0, random_state=42,
            )),
        ]),
        "random_forest": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", RandomForestClassifier(
                n_estimators=350, min_samples_leaf=3, max_features="sqrt",
                class_weight="balanced", random_state=42, n_jobs=-1,
            )),
        ]),
        "extra_trees": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", ExtraTreesClassifier(
                n_estimators=350, min_samples_leaf=3, max_features="sqrt",
                class_weight="balanced", random_state=43, n_jobs=-1,
            )),
        ]),
    }


def fit_with_weights(model, X, y, weights):
    model.fit(X, y, **{"model__sample_weight": weights})


def metrics(y, p):
    return {
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "pr_auc": float(average_precision_score(y, p)) if y.sum() > 0 else None,
        "brier": float(brier_score_loss(y, p)),
    }


def class_weights(y):
    y = np.asarray(y, dtype=int)
    counts = np.bincount(y, minlength=2).astype(float)
    total = float(len(y))
    w = np.ones_like(y, dtype=float)
    for cls in (0, 1):
        if counts[cls] > 0:
            w[y == cls] = total / (2.0 * counts[cls])
    return w


def evaluate_target(df: pd.DataFrame, target: str):
    y_all = as_binary(df[target])
    valid = y_all.notna()
    data = df.loc[valid].copy()
    y = y_all.loc[valid].astype(int).to_numpy()
    groups = groups_for(data).to_numpy()
    candidate_predictors = predictors(data, target)

    oof = {name: np.full(len(data), np.nan) for name in model_specs()}
    folds_out = []

    for fold_id, held in enumerate(folds(pd.Series(groups)), start=1):
        test = np.isin(groups, held)
        train = ~test
        if len(np.unique(y[train])) < 2 or len(np.unique(y[test])) < 2:
            continue

        fold_predictors = [
            col for col in candidate_predictors
            if data.iloc[train][col].notna().any()
            and data.iloc[train][col].nunique(dropna=True) >= 2
        ]
        if not fold_predictors:
            continue

        X_train = data.iloc[train][fold_predictors]
        X_test = data.iloc[test][fold_predictors]
        weights = class_weights(y[train])
        probabilities = {}

        for name, spec in model_specs().items():
            fit_with_weights(spec, X_train, y[train], weights)
            probabilities[name] = spec.predict_proba(X_test)[:, 1]
            oof[name][test] = probabilities[name]

        probabilities["soft_vote"] = np.mean(
            np.column_stack([
                probabilities["hgb"],
                probabilities["random_forest"],
                probabilities["extra_trees"],
            ]),
            axis=1,
        )
        oof.setdefault("soft_vote", np.full(len(data), np.nan))
        oof["soft_vote"][test] = probabilities["soft_vote"]

        folds_out.append({
            "fold": fold_id,
            "held_out_groups": [str(x) for x in held],
            "n_train": int(train.sum()),
            "n_test": int(test.sum()),
            "test_positives": int(y[test].sum()),
            "predictor_count": len(fold_predictors),
        })

    report = {
        "target": target,
        "records": int(len(data)),
        "positive": int(y.sum()),
        "negative": int((1 - y).sum()),
        "groups": int(pd.Series(groups).nunique()),
        "candidate_predictor_count": int(len(candidate_predictors)),
        "folds": folds_out,
        "models": {},
    }
    for name, p in oof.items():
        valid_p = np.isfinite(p)
        if not valid_p.any():
            report["models"][name] = {"status": "no_valid_predictions"}
            continue
        m = metrics(y[valid_p], p[valid_p])
        report["models"][name] = {
            "status": "ok",
            "evaluated_rows": int(valid_p.sum()),
            **m,
        }

    return data, y, candidate_predictors, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features_csv")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    source = pd.read_csv(args.features_csv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    overall = {
        "version": "model-family-comparison-v1",
        "dataset": str(args.features_csv),
        "future_information_policy": str(source.get("future_information_policy", pd.Series(["unknown"])).dropna().iloc[0]),
        "horizons": {},
    }

    for h in HORIZONS:
        target = f"squall_onset_within_{h}m"
        if target not in source.columns:
            overall["horizons"][str(h)] = {"status": "target_missing"}
            continue
        _, _, _, report = evaluate_target(source, target)
        overall["horizons"][str(h)] = report

    (out / "metrics.json").write_text(json.dumps(overall, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
