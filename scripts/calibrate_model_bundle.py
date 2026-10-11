"""Fit research-only Platt calibrators and grouped calibration diagnostics.

Calibrators are fitted to case-grouped out-of-fold (OOF) model probabilities.
Calibration quality is estimated by cross-fitting the calibrator itself across
held-out groups, so a group's labels are never used to fit the calibrator that
scores that group. This remains a research diagnostic: it is not an independent
forward-time release evaluation and must not alone enable operational use.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold


REQUIRED_COLUMNS = {
    "horizon_min", "target", "target_value", "oof_probability", "split_group", "fold"
}


def _safe_metrics(y: np.ndarray, p: np.ndarray, climatology: np.ndarray | None = None) -> dict:
    """Summarize discrimination and probability quality without thresholding."""
    y = np.asarray(y, dtype=int)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    out = {
        "rows": int(len(y)),
        "positive_rows": int(y.sum()),
        "negative_rows": int((1 - y).sum()),
        "prevalence": float(y.mean()) if len(y) else None,
        "brier_score": float(brier_score_loss(y, p)) if len(y) else None,
        "log_loss": float(log_loss(y, p, labels=[0, 1])) if len(y) else None,
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "average_precision": float(average_precision_score(y, p)) if y.sum() else None,
    }
    if climatology is not None and len(y):
        base = np.clip(np.asarray(climatology, dtype=float), 1e-6, 1 - 1e-6)
        base_brier = float(brier_score_loss(y, base))
        out["fold_climatology_brier_score"] = base_brier
        out["brier_skill_vs_fold_climatology"] = (
            float(1 - out["brier_score"] / base_brier) if base_brier > 0 else None
        )

    # Equal-frequency reliability bins. Store counts to expose small-sample bins.
    order = np.argsort(p, kind="stable")
    bins = np.array_split(order, min(10, len(order))) if len(order) else []
    reliability = []
    weighted_gap = 0.0
    for i, indices in enumerate(bins, start=1):
        if not len(indices):
            continue
        predicted = float(p[indices].mean())
        observed = float(y[indices].mean())
        gap = abs(predicted - observed)
        weighted_gap += len(indices) / len(y) * gap
        reliability.append({
            "bin": i,
            "count": int(len(indices)),
            "mean_predicted_probability": predicted,
            "observed_event_rate": observed,
            "absolute_gap": float(gap),
        })
    out["expected_calibration_error_equal_frequency"] = float(weighted_gap) if len(y) else None
    out["reliability_bins"] = reliability
    return out


def _fit_platt(p: np.ndarray, y: np.ndarray) -> LogisticRegression:
    logits = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    model = LogisticRegression(C=10.0, max_iter=2000, solver="lbfgs")
    model.fit(logits.reshape(-1, 1), np.asarray(y, dtype=int))
    return model


def _crossfit_calibration(
    y: np.ndarray,
    p: np.ndarray,
    groups: np.ndarray,
    *,
    min_rows: int,
    min_per_class: int,
) -> dict:
    """Evaluate Platt calibration on groups excluded from each calibrator fit."""
    unique_groups = np.unique(groups.astype(str))
    base = {
        "status": "insufficient_grouped_data",
        "method": "GroupKFold cross-fit of Platt calibration on model OOF probabilities",
        "group_count": int(len(unique_groups)),
        "folds": [],
    }
    if len(unique_groups) < 3:
        base["reason"] = "fewer than 3 independent split groups"
        return base

    splitter = GroupKFold(n_splits=min(5, len(unique_groups)))
    calibrated = np.full(len(y), np.nan, dtype=float)
    fold_climatology = np.full(len(y), np.nan, dtype=float)
    fold_reports = []
    for fold_id, (train_idx, test_idx) in enumerate(
        splitter.split(np.zeros(len(y)), y, groups.astype(str)), start=1
    ):
        y_train = y[train_idx]
        train_groups = np.unique(groups[train_idx].astype(str))
        test_groups = np.unique(groups[test_idx].astype(str))
        fold = {
            "fold": fold_id,
            "train_groups": int(len(train_groups)),
            "test_groups": int(len(test_groups)),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
        }
        if np.intersect1d(train_groups, test_groups).size:
            fold["status"] = "group_leakage_detected"
            fold_reports.append(fold)
            base["folds"] = fold_reports
            base["reason"] = "split_group overlap between calibration fit and evaluation"
            return base
        if (
            len(train_idx) < min_rows
            or int(y_train.sum()) < min_per_class
            or int((1 - y_train).sum()) < min_per_class
        ):
            fold["status"] = "insufficient_training_class_support"
            fold_reports.append(fold)
            base["folds"] = fold_reports
            base["reason"] = "at least one fold lacks minimum rows or per-class support"
            return base
        calibrator = _fit_platt(p[train_idx], y_train)
        clipped_test = np.clip(p[test_idx], 1e-6, 1 - 1e-6)
        test_logits = np.log(clipped_test / (1 - clipped_test)).reshape(-1, 1)
        calibrated[test_idx] = calibrator.predict_proba(test_logits)[:, 1]
        fold_climatology[test_idx] = float(y_train.mean())
        fold["status"] = "ok"
        fold["train_positive_rows"] = int(y_train.sum())
        fold["test_positive_rows"] = int(y[test_idx].sum())
        fold_reports.append(fold)

    if not np.isfinite(calibrated).all() or not np.isfinite(fold_climatology).all():
        base["folds"] = fold_reports
        base["reason"] = "cross-fitted probabilities incomplete"
        return base

    base.update({
        "status": "evaluated_research_diagnostic_only",
        "fit_evaluation_group_overlap": False,
        "raw_oof_probability_metrics": _safe_metrics(y, p, fold_climatology),
        "cross_fitted_calibrated_probability_metrics": _safe_metrics(y, calibrated, fold_climatology),
        "folds": fold_reports,
        "caveat": (
            "Calibration is cross-fitted across split groups, but these are still "
            "research diagnostics on the available OOF population, not an independent "
            "forward-time release gate."
        ),
    })
    return base


def fit_calibrators(model_dir: Path, min_rows: int = 30, min_per_class: int = 5):
    metrics_path = model_dir / "metrics.json"
    pred_path = model_dir / "oof_predictions.csv"
    if not metrics_path.exists() or not pred_path.exists():
        raise FileNotFoundError(f"Missing model metrics or OOF predictions in {model_dir}")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    predictions = pd.read_csv(pred_path)
    missing = sorted(REQUIRED_COLUMNS - set(predictions.columns))
    if missing:
        raise ValueError(f"OOF predictions missing required fields: {missing}")

    calibrators = {}
    report = {
        "status": "research_only_not_independently_validated",
        "source": "case_grouped_out_of_fold_predictions",
        "independent_test_used_for_fit": False,
        "calibration_evaluation_method": "group-held-out cross-fitting of the calibrator",
        "base_model_evaluation_status": metrics.get("evaluation_status"),
        "horizons": {},
    }
    for horizon in (15, 30, 45, 60):
        frame = predictions[
            pd.to_numeric(predictions["horizon_min"], errors="coerce").eq(horizon)
        ].copy()
        y_all = pd.to_numeric(frame["target_value"], errors="coerce")
        p_all = pd.to_numeric(frame["oof_probability"], errors="coerce")
        group_all = frame["split_group"].fillna("").astype(str).str.strip()
        fold_all = frame["fold"]
        mask = (
            y_all.isin([0, 1])
            & p_all.between(0, 1)
            & group_all.ne("")
            & fold_all.notna()
        )
        y = y_all.loc[mask].astype(int).to_numpy()
        p = p_all.loc[mask].astype(float).to_numpy()
        groups = group_all.loc[mask].astype(str).to_numpy()
        positives = int(y.sum())
        negatives = int((1 - y).sum())
        item = {
            "rows": int(len(y)),
            "positive_rows": positives,
            "negative_rows": negatives,
            "groups": int(len(np.unique(groups))) if len(groups) else 0,
            "base_oof_folds": int(frame.loc[mask, "fold"].nunique()),
            "method": "Platt logistic regression on OOF probability logits",
        }
        if (
            len(y) < min_rows
            or positives < min_per_class
            or negatives < min_per_class
            or len(np.unique(y)) < 2
        ):
            item["status"] = "insufficient_data"
            item["reason"] = "minimum rows or per-class support not met"
            report["horizons"][str(horizon)] = item
            continue

        item["cross_fitted_evaluation"] = _crossfit_calibration(
            y, p, groups, min_rows=min_rows, min_per_class=min_per_class
        )
        calibrator = _fit_platt(p, y)
        calibrators[str(horizon)] = calibrator
        item["status"] = "fit_research_artifact"
        item["target"] = f"squall_onset_within_{horizon}m"
        item["full_oof_fit_metrics_not_validation"] = _safe_metrics(y, calibrator.predict_proba(
            np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(-1, 1)
        )[:, 1])
        report["horizons"][str(horizon)] = item

    if calibrators:
        joblib.dump(calibrators, model_dir / "probability_calibrators_research.joblib")
    (model_dir / "calibration_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--min-rows", type=int, default=30)
    parser.add_argument("--min-per-class", type=int, default=5)
    args = parser.parse_args()
    fit_calibrators(Path(args.model_dir), args.min_rows, args.min_per_class)


if __name__ == "__main__":
    main()
