"""Evaluate snow-squall candidates with forward-in-time, group-held-out folds.

The evaluator is deliberately separate from the operational-release gate. It
answers whether a model trained on earlier cases generalizes to later cases
without allowing future-era rows into training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from src.snow_squall.training import case_scan_balanced_weights


HORIZONS = (15, 30, 45, 60)


def choose_predictors(df: pd.DataFrame, schema: dict) -> list[str]:
    blocked = {
        "scan_time_utc", "source_file", "radar_site", "object_id",
        "case_id", "null_id", "episode_id", "population", "split_group",
        "population_track_key", "future_information_policy",
        "label_status", "label_reason", "truth_status", "supervision_class",
        "environment_status", "environment_source", "activity_class",
    }
    prefixes = ("case_", "label_", "squall_", "track_event_", "association_", "truth_", "surface_")
    allowed = schema.get("operational_predictor_columns") or schema.get("predictor_columns") or []
    out = []
    for col in allowed:
        if col not in df.columns or col in blocked or any(col.startswith(p) for p in prefixes):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            out.append(col)
    return out


def group_key(df: pd.DataFrame) -> pd.Series:
    if "split_group" in df.columns:
        return df["split_group"].astype(str)
    if "population_track_key" in df.columns:
        return df["population_track_key"].astype(str)
    case = df["case_id"].fillna("").astype(str) if "case_id" in df.columns else pd.Series("", index=df.index)
    null = df["null_id"].fillna("").astype(str) if "null_id" in df.columns else pd.Series("", index=df.index)
    return np.where(case.ne(""), "case:" + case, "null:" + null)


def chronological_folds(groups: pd.Series, times: pd.Series, n_splits: int = 4) -> list[tuple[list[str], list[str]]]:
    meta = pd.DataFrame({"group": groups.astype(str).values, "time": times.values})
    meta = meta.dropna(subset=["time"]).groupby("group", as_index=False)["time"].min()
    meta = meta.sort_values(["time", "group"]).reset_index(drop=True)
    if len(meta) < 6:
        return []

    n_splits = min(n_splits, len(meta) - 2)
    block = max(1, len(meta) // (n_splits + 1))
    folds = []
    for i in range(n_splits):
        train_end = block * (i + 1)
        test_end = min(train_end + block, len(meta))
        if train_end < 3 or test_end <= train_end:
            continue
        train_groups = meta.iloc[:train_end]["group"].tolist()
        test_groups = meta.iloc[train_end:test_end]["group"].tolist()
        if test_groups:
            folds.append((train_groups, test_groups))
    return folds


def evaluate_target(df: pd.DataFrame, target: str, predictors: list[str]) -> dict:
    y = pd.to_numeric(df[target], errors="coerce")
    valid = y.notna()
    work = df.loc[valid].copy()
    if work.empty:
        return {"status": "target_missing_or_empty"}

    y = y.loc[valid].astype(int)
    if y.nunique() < 2:
        return {"status": "insufficient_class_diversity"}

    times = pd.to_datetime(work["scan_time_utc"], utc=True, errors="coerce")
    groups = pd.Series(group_key(work), index=work.index).astype(str)
    folds = chronological_folds(groups, times)
    if not folds:
        return {
            "status": "insufficient_temporal_groups",
            "groups": int(groups.nunique()),
        }

    rows = []
    for fold_id, (train_groups, test_groups) in enumerate(folds, start=1):
        train_mask = groups.isin(set(train_groups))
        test_mask = groups.isin(set(test_groups))
        y_train = y.loc[train_mask]
        y_test = y.loc[test_mask]

        if y_train.nunique() < 2 or y_test.nunique() < 2:
            rows.append({
                "fold": fold_id,
                "status": "skipped_class_diversity",
                "train_groups": len(train_groups),
                "test_groups": len(test_groups),
                "test_positive_rows": int(y_test.sum()),
            })
            continue

        fold_predictors = []
        for col in predictors:
            values = pd.to_numeric(work.loc[train_mask, col], errors="coerce").replace([np.inf, -np.inf], np.nan)
            if values.notna().any() and values.nunique(dropna=True) >= 2:
                fold_predictors.append(col)
        if not fold_predictors:
            rows.append({"fold": fold_id, "status": "skipped_no_variable_predictors"})
            continue

        model = HistGradientBoostingClassifier(
            learning_rate=0.08,
            max_iter=200,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=42,
        )
        evidence = pd.to_numeric(
            work.loc[train_mask].get("evidence_weight", pd.Series(1.0, index=work.loc[train_mask].index)),
            errors="coerce",
        ).fillna(1.0).to_numpy()
        weights = case_scan_balanced_weights(work.loc[train_mask]) * evidence
        model.fit(
            work.loc[train_mask, fold_predictors],
            y_train,
            sample_weight=weights,
        )
        probability = model.predict_proba(work.loc[test_mask, fold_predictors])[:, 1]

        train_end = times.loc[train_mask].max()
        test_start = times.loc[test_mask].min()
        rows.append({
            "fold": fold_id,
            "status": "ok",
            "train_groups": len(train_groups),
            "test_groups": len(test_groups),
            "train_rows": int(train_mask.sum()),
            "test_rows": int(test_mask.sum()),
            "test_positive_rows": int(y_test.sum()),
            "predictor_count": len(fold_predictors),
            "train_through_utc": train_end.isoformat() if pd.notna(train_end) else None,
            "test_from_utc": test_start.isoformat() if pd.notna(test_start) else None,
            "roc_auc": float(roc_auc_score(y_test, probability)),
            "pr_auc": float(average_precision_score(y_test, probability)),
            "brier": float(brier_score_loss(y_test, probability)),
        })

    ok = [r for r in rows if r["status"] == "ok"]
    result = {
        "status": "ok" if ok else "no_valid_temporal_folds",
        "records": int(len(work)),
        "positive_rows": int(y.sum()),
        "negative_rows": int((1 - y).sum()),
        "groups": int(groups.nunique()),
        "folds": rows,
    }
    if ok:
        for metric in ("roc_auc", "pr_auc", "brier"):
            values = [r[metric] for r in ok]
            result[metric + "_mean"] = float(np.mean(values))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.features)
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    predictors = choose_predictors(df, schema)

    report = {
        "version": "temporal-holdout-v1",
        "future_information_policy": schema.get("future_information_policy"),
        "predictor_count": len(predictors),
        "predictor_policy": "operational_predictor_columns",
        "horizons": {},
    }
    for h in HORIZONS:
        target = f"squall_onset_within_{h}m"
        report["horizons"][str(h)] = (
            evaluate_target(df, target, predictors)
            if target in df.columns
            else {"status": "target_missing"}
        )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
