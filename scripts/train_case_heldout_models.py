"""Train leakage-safe case-held-out snow-squall models.

This gate deliberately splits by case_id rather than individual radar scans.
It evaluates four forecast horizons and writes metrics plus a final model
bundle. It can operate directly on an object_model_features CSV artifact,
so historical Level-II acquisition is not part of the training gate.

The script refuses to train if the feature table contains obvious future/truth
columns in the predictor set.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HORIZONS = (15, 30, 45, 60)
TARGET_TEMPLATE = "squall_onset_within_{h}m"

BLOCKED_PREFIXES = (
    "case_", "label_", "squall_", "track_event_", "association_",
    "truth_", "surface_",
)
BLOCKED_EXACT = {
    "lead_time_min", "lead_time_to_warning_min", "warning_issue_utc",
    "warning_distance_km", "warning_verifying_lsr_count",
    "warning_supervision_class", "sqw_intersection",
    "scan_time_utc", "source_file", "radar_site", "object_id",
}

def as_binary(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    mapped = series.astype(str).str.strip().str.lower().map({
        "true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0,
    })
    return mapped.astype(float)

def choose_predictors(df: pd.DataFrame, target: str) -> list[str]:
    blocked = set(BLOCKED_EXACT) | {target}
    cols = []
    for c in df.columns:
        if c in blocked or any(c.startswith(p) for p in BLOCKED_PREFIXES):
            continue
        if c in {"population", "future_information_policy", "environment_status",
                 "environment_source", "label_status", "label_reason"}:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    if not cols:
        raise ValueError("No numeric forecast-time predictors remain after leakage controls.")
    return cols

def event_folds(groups: pd.Series, n_splits: int = 5):
    unique = pd.Series(groups.dropna().unique())
    if len(unique) < 2:
        return []
    n = min(n_splits, len(unique))
    rng = np.random.default_rng(42)
    shuffled = unique.to_numpy().copy()
    rng.shuffle(shuffled)
    return [shuffled[i::n] for i in range(n)]

def fit_pipeline() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(
            max_iter=3000, class_weight="balanced", solver="liblinear", random_state=42
        )),
    ])

def evaluate(df: pd.DataFrame, target: str, predictors: list[str]) -> dict:
    y = as_binary(df[target])
    valid = y.notna()
    work = df.loc[valid].copy()
    y = y.loc[valid].astype(int)
    groups = work["case_id"].astype(str) if "case_id" in work else pd.Series(
        np.arange(len(work)), index=work.index
    )

    if y.nunique() < 2:
        return {"status": "insufficient_class_diversity", "n": int(len(y)), "classes": y.value_counts().to_dict()}

    folds = event_folds(groups)
    fold_rows = []
    for i, held_groups in enumerate(folds, 1):
        test_mask = groups.isin(set(held_groups))
        train_mask = ~test_mask
        if y.loc[train_mask].nunique() < 2 or y.loc[test_mask].nunique() < 2:
            continue
        model = fit_pipeline()
        model.fit(work.loc[train_mask, predictors], y.loc[train_mask])
        p = model.predict_proba(work.loc[test_mask, predictors])[:, 1]
        yt = y.loc[test_mask]
        fold_rows.append({
            "fold": i,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "test_cases": int(len(set(groups.loc[test_mask]))),
            "roc_auc": float(roc_auc_score(yt, p)),
            "pr_auc": float(average_precision_score(yt, p)),
            "brier": float(brier_score_loss(yt, p)),
        })

    result = {
        "status": "ok" if fold_rows else "no_valid_event_folds",
        "n": int(len(y)),
        "positive": int(y.sum()),
        "negative": int((1-y).sum()),
        "cases": int(groups.nunique()),
        "predictor_count": len(predictors),
        "folds": fold_rows,
    }
    if fold_rows:
        for metric in ("roc_auc", "pr_auc", "brier"):
            vals = [r[metric] for r in fold_rows]
            result[metric + "_mean"] = float(np.mean(vals))
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--output-dir", default="data/derived/model_gate")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(src)

    if "future_information_policy" not in df.columns:
        raise SystemExit("FAIL: feature table lacks future_information_policy provenance.")
    policy = df["future_information_policy"].astype(str)
    if not policy.str.contains("past|current|forecast", case=False, regex=True).any():
        raise SystemExit("FAIL: no forecast-time feature policy records found.")

    summaries = {}
    final_models = {}
    for h in HORIZONS:
        target = TARGET_TEMPLATE.format(h=h)
        if target not in df.columns:
            summaries[str(h)] = {"status": "target_missing", "target": target}
            continue
        predictors = choose_predictors(df, target)
        result = evaluate(df, target, predictors)
        result["target"] = target
        summaries[str(h)] = result

        y = as_binary(df[target])
        valid = y.notna()
        if y.loc[valid].nunique() >= 2:
            model = fit_pipeline()
            model.fit(df.loc[valid, predictors], y.loc[valid].astype(int))
            final_models[str(h)] = {"model": model, "predictors": predictors}

    with (out / "metrics.json").open("w") as f:
        json.dump(summaries, f, indent=2)

    joblib.dump(final_models, out / "models.joblib")
    pd.DataFrame([
        {"horizon_min": int(h), **{k: v for k, v in s.items() if not isinstance(v, list)}}
        for h, s in summaries.items()
    ]).to_csv(out / "metrics.csv", index=False)

    ok = [s for s in summaries.values() if s.get("status") == "ok"]
    print("MODEL GATE")
    print("records:", len(df))
    print("cases:", df["case_id"].nunique() if "case_id" in df else "missing")
    print("horizons evaluated:", len(ok))
    for h, s in summaries.items():
        print(h + "m:", s.get("status"), "ROC-AUC=", s.get("roc_auc_mean"),
              "PR-AUC=", s.get("pr_auc_mean"), "Brier=", s.get("brier_mean"))
    if not ok:
        raise SystemExit("FAIL: no horizon passed the minimum event-held-out evaluation gate.")

if __name__ == "__main__":
    main()
