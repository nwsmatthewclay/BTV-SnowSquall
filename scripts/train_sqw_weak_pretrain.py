"""Train a research-only national SQW weak-supervision radar model.

BTV warning episodes are excluded by default so the resulting pretrainer can
serve as a geographically external feature source for the BTV-specific model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline

from scripts.train_candidate_ensemble import class_balanced_weights

RADAR_PREFIXES = (
    "area_",
    "length_",
    "width_",
    "aspect_",
    "motion_",
    "max_reflectivity_",
    "mean_reflectivity_",
    "core_",
    "pixel_",
    "track_",
    "centroid_displacement_",
    "echo_",
    "top_minus_base_",
    "vertical_",
    "zdr_",
    "rhohv_",
    "kdp_",
    "velocity_",
    "reflectivity_",
)

BASE_RADAR_COLUMNS = {
    "area_km2", "length_km", "width_km", "aspect_ratio",
    "motion_dir_deg", "motion_speed_kt",
    "max_reflectivity_dbz", "mean_reflectivity_dbz",
    "core_pixel_count", "pixel_count", "core_fraction",
    "echo_top_km", "top_minus_base_km", "vertical_reflectivity_gradient",
    "vertical_valid_points", "zdr_mean_db", "zdr_p90_db",
    "zdr_gradient_dbkm", "rhohv_mean", "rhohv_max", "rhohv_p90", "rhohv_min",
    "kdp_mean_degkm", "kdp_p90_degkm", "velocity_mean_kt", "velocity_std_kt",
    "velocity_p90_abs_kt", "velocity_gradient_ktkm",
}

def estimator():
    hgb = HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=250, max_leaf_nodes=15,
        l2_regularization=2.0, random_state=42
    )
    rf = RandomForestClassifier(
        n_estimators=350, min_samples_leaf=4, max_features="sqrt",
        random_state=43, n_jobs=-1
    )
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("model", VotingClassifier(
            estimators=[("hgb", hgb), ("rf", rf)],
            voting="soft",
            weights=[1, 1],
        )),
    ])

def train(features: pd.DataFrame, target: str, output: Path, exclude_wfo: str = "BTV"):
    data = features.copy()
    if "warning_wfo" in data.columns:
        data = data[data["warning_wfo"].astype("string").str.upper().ne(exclude_wfo.upper())].copy()

    if target not in data.columns:
        raise ValueError(f"Missing target: {target}")

    group_col = "episode_id" if "episode_id" in data.columns and data["episode_id"].notna().any() else "case_id"
    if group_col not in data.columns:
        raise ValueError("No physical episode/case grouping column is available.")

    candidates = [c for c in BASE_RADAR_COLUMNS if c in data.columns]
    candidates += [c for c in data.columns if c.startswith(RADAR_PREFIXES) and c not in candidates]
    predictors = sorted({
        c for c in candidates
        if pd.api.types.is_numeric_dtype(data[c])
        and c not in {target, "weak_sample_weight"}
    })
    if not predictors:
        raise ValueError("No radar predictors available for weak pretraining.")

    data = data.dropna(subset=[target, group_col]).copy()
    y = data[target].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        raise ValueError("Weak-pretraining target has only one class.")

    groups = data[group_col].astype(str).to_numpy()
    base_weight = pd.to_numeric(
        data.get("weak_sample_weight", pd.Series(1.0, index=data.index)),
        errors="coerce",
    ).fillna(1.0).to_numpy(dtype=float)

    logo = LeaveOneGroupOut()
    oof = np.full(len(data), np.nan)
    fold_rows = []
    X = data[predictors]

    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups), start=1):
        model = estimator()
        train_y = y[train_idx]
        if len(np.unique(train_y)) < 2:
            fold_rows.append({"fold": fold, "status": "skipped_single_class_training"})
            continue
        sample_weight = class_balanced_weights(train_y) * base_weight[train_idx]
        model.fit(X.iloc[train_idx], train_y, model__sample_weight=sample_weight)
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
        fold_rows.append({
            "fold": fold,
            "held_out_group": groups[test_idx][0],
            "test_rows": int(len(test_idx)),
            "test_positives": int(y[test_idx].sum()),
            "status": "ok",
        })

    valid = np.isfinite(oof)
    yv, pv = y[valid], oof[valid]
    metrics = {
        "evaluated_rows": int(valid.sum()),
        "positive_rows": int(yv.sum()),
        "negative_rows": int((1-yv).sum()),
        "auc_roc": float(roc_auc_score(yv, pv)) if len(np.unique(yv)) == 2 else None,
        "average_precision": float(average_precision_score(yv, pv)) if yv.sum() else None,
        "brier_score": float(brier_score_loss(yv, pv)) if valid.any() else None,
    }

    final = estimator()
    final.fit(
        X, y,
        model__sample_weight=class_balanced_weights(y) * base_weight,
    )

    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, output / "weak_pretraining_model.joblib")
    prediction = data[[group_col, "case_id", "radar_site", "object_id", "scan_time_utc", target]].copy()
    prediction["oof_probability"] = oof
    prediction.to_csv(output / "oof_predictions.csv", index=False)

    report = {
        "model_version": "national_sqw_weak_radar_pretrainer_v1",
        "target": target,
        "predictor_columns": predictors,
        "group_column": group_col,
        "excluded_wfo": exclude_wfo,
        "training_rows": int(len(data)),
        "training_groups": int(data[group_col].nunique()),
        "positive_groups": int(data.loc[data[target].eq(1), group_col].nunique()),
        "metrics": metrics,
        "folds": fold_rows,
        "operational_release_status": "candidate_only",
        "intended_use": "national_radar_pretraining_for_BTV_specific_model",
        "warning_supervision_policy": "IEM-verified warning episodes are weak supervision; radar/surface physical truth remains separate.",
    }
    (output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--exclude-wfo", default="BTV")
    args = parser.parse_args()
    train(pd.read_csv(args.features), args.target, Path(args.output_dir), args.exclude_wfo)

if __name__ == "__main__":
    main()
