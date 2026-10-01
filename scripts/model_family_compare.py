"""Compare model families on the same case-held-out forecast population."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HORIZONS = (15, 30, 45, 60)
BLOCKED_PREFIXES = ("case_", "label_", "squall_", "track_event_", "association_", "truth_", "surface_")
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


def choose_predictors(df: pd.DataFrame, target: str) -> list[str]:
    return [
        c for c in df.columns
        if c != target
        and c not in BLOCKED_EXACT
        and not any(c.startswith(p) for p in BLOCKED_PREFIXES)
        and pd.api.types.is_numeric_dtype(df[c])
    ]


def class_weights(y):
    y = np.asarray(y, dtype=int)
    counts = np.bincount(y, minlength=2).astype(float)
    total = float(len(y))
    w = np.ones(len(y), dtype=float)
    for cls in (0, 1):
        if counts[cls] > 0:
            w[y == cls] = total / (2.0 * counts[cls])
    return w


def model_specs():
    return {
        "logistic": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(
                max_iter=3000, class_weight="balanced", solver="liblinear", random_state=42
            )),
        ]),
        "hgb": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", HistGradientBoostingClassifier(
                learning_rate=0.08, max_iter=220, max_leaf_nodes=15,
                l2_regularization=1.0, random_state=42
            )),
        ]),
        "random_forest": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", RandomForestClassifier(
                n_estimators=300, min_samples_leaf=3, max_features="sqrt",
                class_weight="balanced", random_state=42, n_jobs=-1
            )),
        ]),
        "extra_trees": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", ExtraTreesClassifier(
                n_estimators=300, min_samples_leaf=3, max_features="sqrt",
                class_weight="balanced", random_state=43, n_jobs=-1
            )),
        ]),
    }


def evaluate(df: pd.DataFrame, target: str):
    y_series = as_binary(df[target])
    valid = y_series.notna()
    data = df.loc[valid].copy()
    y = y_series.loc[valid].astype(int).to_numpy()
    groups = (
        data["case_id"].astype(str).to_numpy()
        if "case_id" in data
        else np.arange(len(data)).astype(str)
    )
    unique = np.asarray(sorted(set(groups)))
    if unique.size < 3:
        raise ValueError(f"Need at least 3 independent groups; found {unique.size}")

    rng = np.random.default_rng(42)
    shuffled = unique.copy()
    rng.shuffle(shuffled)
    nfolds = min(5, unique.size)
    fold_groups = [shuffled[i::nfolds] for i in range(nfolds)]

    predictor_cols = choose_predictors(data, target)
    specs = model_specs()
    oof = {name: np.full(len(data), np.nan) for name in specs}
    oof["soft_vote"] = np.full(len(data), np.nan)
    folds = []

    for fold, held in enumerate(fold_groups, 1):
        test = np.isin(groups, held)
        train = ~test
        if len(np.unique(y[train])) < 2 or len(np.unique(y[test])) < 2:
            continue

        fold_predictors = [
            c for c in predictor_cols
            if data.iloc[train][c].notna().any()
            and data.iloc[train][c].nunique(dropna=True) >= 2
        ]
        if not fold_predictors:
            continue

        X_train = data.iloc[train][fold_predictors]
        X_test = data.iloc[test][fold_predictors]
        weights = class_weights(y[train])
        probs = {}

        for name, spec in specs.items():
            spec.fit(X_train, y[train], model__sample_weight=weights)
            probs[name] = spec.predict_proba(X_test)[:, 1]
            oof[name][test] = probs[name]

        oof["soft_vote"][test] = np.mean(
            np.column_stack([
                probs["hgb"],
                probs["random_forest"],
                probs["extra_trees"],
            ]),
            axis=1,
        )
        folds.append({
            "fold": fold,
            "held_out_groups": [str(x) for x in held],
            "n_train": int(train.sum()),
            "n_test": int(test.sum()),
            "test_positives": int(y[test].sum()),
            "predictor_count": len(fold_predictors),
        })

    report = {
        "status": "ok" if folds else "no_valid_folds",
        "target": target,
        "records": int(len(data)),
        "positive": int(y.sum()),
        "negative": int((1 - y).sum()),
        "groups": int(len(unique)),
        "candidate_predictor_count": len(predictor_cols),
        "folds": folds,
        "models": {},
    }
    for name, pred in oof.items():
        ok = np.isfinite(pred)
        if not ok.any():
            report["models"][name] = {"status": "no_valid_predictions"}
            continue
        yy = y[ok]
        pp = pred[ok]
        report["models"][name] = {
            "status": "ok",
            "evaluated_rows": int(ok.sum()),
            "roc_auc": float(roc_auc_score(yy, pp)) if len(np.unique(yy)) == 2 else None,
            "pr_auc": float(average_precision_score(yy, pp)) if yy.sum() else None,
            "brier": float(brier_score_loss(yy, pp)),
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features_csv")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    source = pd.read_csv(args.features_csv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    overall = {
        "version": "model-family-comparison-v2",
        "dataset": str(args.features_csv),
        "future_information_policy": (
            str(source["future_information_policy"].dropna().iloc[0])
            if "future_information_policy" in source.columns
            else "unknown"
        ),
        "horizons": {},
    }
    for h in HORIZONS:
        target = f"squall_onset_within_{h}m"
        overall["horizons"][str(h)] = (
            evaluate(source, target)
            if target in source.columns
            else {"status": "target_missing"}
        )
    (out / "metrics.json").write_text(
        json.dumps(overall, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
