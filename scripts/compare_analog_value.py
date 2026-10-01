"""Measure incremental value of causal historical analogs with fold-safe case-held-out CV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.snow_squall.analogs import AnalogLibrary

HORIZONS = (15, 30, 45, 60)
ANALOG_PREFIX = "analog_"
BLOCKED_PREFIXES = (
    "case_", "label_", "squall_", "track_event_", "association_", "truth_", "surface_"
)
BLOCKED_EXACT = {
    "scan_time_utc", "source_file", "radar_site", "object_id", "population",
    "population_id", "future_information_policy", "lead_time_min", "sqw_intersection",
}

def binary(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    return series.astype(str).str.strip().str.lower().map(
        {"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0}
    )

def model_specs():
    return {
        "logistic": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(
                max_iter=2500, class_weight="balanced", solver="liblinear", random_state=42
            )),
        ]),
        "hgb": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", HistGradientBoostingClassifier(
                learning_rate=0.08, max_iter=220, max_leaf_nodes=15,
                l2_regularization=1.0, random_state=42
            )),
        ]),
    }

def predictors(df: pd.DataFrame, target: str, with_analogs: bool):
    out = []
    for col in df.columns:
        if col == target or col in BLOCKED_EXACT:
            continue
        if any(col.startswith(p) for p in BLOCKED_PREFIXES):
            continue
        if not with_analogs and col.startswith(ANALOG_PREFIX):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            out.append(col)
    return out

def make_folds(groups):
    unique = np.asarray(sorted(set(groups)))
    rng = np.random.default_rng(42)
    rng.shuffle(unique)
    n = min(5, len(unique))
    return [unique[i::n] for i in range(n)]

def apply_fold_analogs(train: pd.DataFrame, test: pd.DataFrame):
    library = AnalogLibrary.fit(train)
    train_analog = library.query(train, top_k=15, max_age_days=3650)
    test_analog = library.query(test, top_k=15, max_age_days=3650)

    train_out = train.copy()
    test_out = test.copy()
    for col in train_analog.columns:
        train_out[col] = train_analog[col].to_numpy()
        test_out[col] = test_analog[col].to_numpy()
    return train_out, test_out

def evaluate(df: pd.DataFrame, target: str):
    ys = binary(df[target])
    valid = ys.notna()
    data = df.loc[valid].copy().reset_index(drop=True)
    y = ys.loc[valid].astype(int).to_numpy()
    groups = data["case_id"].astype(str).to_numpy()

    folds = make_folds(groups)
    predictions = {
        ("baseline", name): np.full(len(data), np.nan) for name in model_specs()
    }
    predictions.update({
        ("analogs", name): np.full(len(data), np.nan) for name in model_specs()
    })
    fold_reports = []

    for fold_number, held_out in enumerate(folds, 1):
        test_mask = np.isin(groups, held_out)
        train_mask = ~test_mask
        if len(np.unique(y[train_mask])) < 2 or len(np.unique(y[test_mask])) < 2:
            continue

        train_raw = data.loc[train_mask].copy()
        test_raw = data.loc[test_mask].copy()
        train_analog, test_analog = apply_fold_analogs(train_raw, test_raw)

        fold_reports.append({
            "fold": fold_number,
            "held_out_cases": sorted(set(groups[test_mask])),
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
        })

        for variant, train_frame, test_frame in (
            ("baseline", train_raw, test_raw),
            ("analogs", train_analog, test_analog),
        ):
            cols = predictors(train_frame, target, variant == "analogs")
            cols = [
                c for c in cols
                if train_frame[c].notna().any()
                and train_frame[c].nunique(dropna=True) >= 2
            ]
            for name, spec in model_specs().items():
                spec.fit(train_frame[cols], y[train_mask])
                predictions[(variant, name)][test_mask] = (
                    spec.predict_proba(test_frame[cols])[:, 1]
                )

    models = {}
    for (variant, name), pred in predictions.items():
        ok = np.isfinite(pred)
        if not ok.any():
            models[f"{variant}_{name}"] = {"status": "no_valid_predictions"}
            continue
        yy = y[ok]
        pp = pred[ok]
        models[f"{variant}_{name}"] = {
            "status": "ok",
            "evaluated_rows": int(ok.sum()),
            "roc_auc": float(roc_auc_score(yy, pp)) if len(np.unique(yy)) == 2 else None,
            "pr_auc": float(average_precision_score(yy, pp)) if yy.sum() else None,
            "brier": float(brier_score_loss(yy, pp)),
        }

    return {
        "status": "ok" if fold_reports else "no_valid_folds",
        "records": int(len(data)),
        "cases": int(data["case_id"].nunique()),
        "positive": int(y.sum()),
        "negative": int((1 - y).sum()),
        "folds": fold_reports,
        "models": models,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features_csv")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.features_csv)
    report = {
        "version": "causal-analog-value-v2",
        "dataset": str(args.features_csv),
        "future_information_policy": (
            str(df["future_information_policy"].dropna().iloc[0])
            if "future_information_policy" in df.columns and df["future_information_policy"].notna().any()
            else "unknown"
        ),
        "horizons": {},
    }

    for horizon in HORIZONS:
        target = f"squall_onset_within_{horizon}m"
        report["horizons"][str(horizon)] = (
            evaluate(df, target) if target in df.columns else {"status": "target_missing"}
        )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
