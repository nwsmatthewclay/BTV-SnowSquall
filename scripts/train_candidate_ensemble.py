"""Train a research-only snow-squall soft-vote ensemble with case-held-out OOF evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline

from scripts.train_baseline_model import load_schema, prepare_dataset, grouped_bootstrap_intervals


def class_balanced_weights(y):
    y = np.asarray(y, dtype=int)
    counts = np.bincount(y, minlength=2).astype(float)
    total = float(len(y))
    weights = np.ones_like(y, dtype=float)
    for cls in (0, 1):
        if counts[cls] > 0:
            weights[y == cls] = total / (2.0 * counts[cls])
    return weights


def estimator():
    hgb = HistGradientBoostingClassifier(
        learning_rate=0.06, max_iter=300, max_leaf_nodes=15,
        l2_regularization=1.5, random_state=42
    )
    rf = RandomForestClassifier(
        n_estimators=400, max_depth=None, min_samples_leaf=3,
        max_features="sqrt", random_state=42, n_jobs=-1
    )
    extra = ExtraTreesClassifier(
        n_estimators=400, max_depth=None, min_samples_leaf=3,
        max_features="sqrt", random_state=43, n_jobs=-1
    )
    vote = VotingClassifier(
        estimators=[("hgb", hgb), ("rf", rf), ("extra", extra)],
        voting="soft", weights=[1, 1, 1], flatten_transform=True
    )
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("model", vote),
    ])


def evaluate(data, predictors, target):
    logo = LeaveOneGroupOut()
    X = data[predictors]
    y = data[target].astype(int).to_numpy()
    groups = data["split_group"].to_numpy()
    oof = np.full(len(data), np.nan)
    climatology = np.full(len(data), np.nan)
    folds = []
    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups), start=1):
        model = estimator()
        train_y = y[train_idx]
        climatology[test_idx] = float(train_y.mean())
        if len(np.unique(train_y)) < 2:
            folds.append({"fold":fold,"held_out_group":groups[test_idx][0],"status":"skipped_single_class_training"})
            continue
        weights = class_balanced_weights(train_y) * pd.to_numeric(data.iloc[train_idx].get("evidence_weight", pd.Series(1.0, index=data.iloc[train_idx].index)), errors="coerce").fillna(1.0).to_numpy()
        model.fit(X.iloc[train_idx], train_y, model__sample_weight=weights)
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
        folds.append({"fold":fold,"held_out_group":groups[test_idx][0],"test_rows":int(len(test_idx)),"test_positives":int(y[test_idx].sum()),"status":"ok"})
    valid = np.isfinite(oof)
    yv = y[valid]
    pv = oof[valid]
    metrics={
        "evaluated_rows": int(valid.sum()),
        "positive_rows": int(yv.sum()),
        "negative_rows": int((1-yv).sum()),
        "auc_roc": float(roc_auc_score(yv,pv)) if len(np.unique(yv))==2 else None,
        "average_precision": float(average_precision_score(yv,pv)) if yv.sum()>0 else None,
        "brier_score": float(brier_score_loss(yv,pv)) if valid.any() else None,
        "grouped_bootstrap_95pct": grouped_bootstrap_intervals(yv,pv,groups[valid]),
        "climatology": {
            "brier_score": float(brier_score_loss(yv,climatology[valid])) if np.isfinite(climatology[valid]).all() and valid.any() else None,
        },
    }
    return oof, metrics, folds


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("features_csv")
    parser.add_argument("--schema",required=True)
    parser.add_argument("--target",required=True)
    parser.add_argument("--output-dir",required=True)
    args=parser.parse_args()

    source=pd.read_csv(args.features_csv)
    schema=load_schema(Path(args.schema))
    data,predictors=prepare_dataset(source,schema,args.target)
    # Enforce the same live-compatible predictor contract as the baseline.
    operational=set(schema.get("operational_predictor_columns") or predictors)
    predictors=[c for c in predictors if c in operational]
    if not predictors:
        raise ValueError("No live-compatible predictors remain for ensemble training.")
    oof,metrics,folds=evaluate(data,predictors,args.target)
    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    pred=data[["split_group","population","case_id","null_id","radar_site","object_id","scan_time_utc",args.target]].copy()
    pred["oof_probability"]=oof
    pred.to_csv(out/"oof_predictions.csv",index=False)

    final=estimator()
    final.fit(data[predictors],data[args.target].astype(int),model__sample_weight=class_balanced_weights(data[args.target].astype(int)))
    joblib.dump(final,out/"baseline_model.joblib")
    positive_groups=sorted(data.loc[data[args.target].eq(1),"split_group"].astype(str).unique())
    report={
        "model_version":"candidate_soft_vote_ensemble_v1",
        "dataset_revision":str(args.features_csv),
        "schema_revision":str(args.schema),
        "target":args.target,
        "future_information_policy":schema["future_information_policy"],
        "predictor_columns":predictors,
        "operational_predictor_policy":"live_compatible_subset_from_feature_schema",
        "training_rows":int(len(data)),
        "training_groups":int(data["split_group"].nunique()),
        "positive_case_groups":positive_groups,
        "positive_case_group_count":len(positive_groups),
        "evaluation_unit":"episode_or_case_or_null_group",
        "evaluation_status":"case_held_out_exploratory" if len(positive_groups)>=3 else "case_held_out_not_interpretable",
        "operational_release_status":"candidate_only",
        "operational_release_note":"Research candidate only; independent modern verification and calibration are required before operational release.",
        "estimator_family":["HistGradientBoostingClassifier","RandomForestClassifier","ExtraTreesClassifier"],
        "training_weight_policy":"inverse_class_frequency_with_equal_class_total",
        "metrics":metrics,
        "folds":folds,
        "null_activity_policy":"clean_quiet_light",
    }
    (out/"metrics.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
