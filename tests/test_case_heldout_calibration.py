import json

import numpy as np
import pandas as pd
import pytest

from scripts.calibrate_model_bundle import fit_calibrators
from scripts.train_case_heldout_models import choose_predictors, evaluate


def test_predictor_guard_blocks_outcome_like_numeric_columns():
    frame = pd.DataFrame({
        "max_reflectivity_dbz": [20.0, 30.0],
        "cape_jkg": [10.0, 100.0],
        "future_visibility_min": [0.5, 0.2],
        "verified_event_count": [1, 0],
        "warning_distance_km": [5.0, 10.0],
        "squall_onset_within_15m": [1, 0],
    })
    predictors = choose_predictors(frame, "squall_onset_within_15m")
    assert predictors == ["max_reflectivity_dbz", "cape_jkg"]


def test_evaluate_emits_one_oof_prediction_per_evaluable_row_and_keeps_groups():
    rows = []
    for group_i in range(10):
        label = int(group_i < 5)
        for scan in range(2):
            rows.append({
                "split_group": f"case-{group_i}",
                "case_id": f"case-{group_i}",
                "reflectivity_max_dbz": float(25 + 10 * label + scan),
                "cape_jkg": float(20 + 100 * label),
                "squall_onset_within_15m": label,
            })
    frame = pd.DataFrame(rows)
    result = evaluate(frame, "squall_onset_within_15m", ["reflectivity_max_dbz", "cape_jkg"])
    assert result["status"] == "ok"
    oof = result["oof_predictions"]
    assert len(oof) == len(frame)
    assert all(0 <= row["oof_probability"] <= 1 for row in oof)
    # A given group is evaluated in exactly one fold; scans from one case do not split.
    by_group = {}
    for row in oof:
        by_group.setdefault(row["split_group"], set()).add(row["fold"])
    assert all(len(folds) == 1 for folds in by_group.values())


def test_calibrator_fits_per_horizon_and_marks_artifacts_research_only(tmp_path):
    metrics = {str(h): {"target": f"squall_onset_within_{h}m", "status": "ok"} for h in (15, 30, 45, 60)}
    (tmp_path / "metrics.json").write_text(json.dumps(metrics))
    rows = []
    for h in (15, 30, 45, 60):
        for i in range(80):
            y = int(i % 4 == 0)
            rows.append({
                "horizon_min": h,
                "target": f"squall_onset_within_{h}m",
                "target_value": y,
                "oof_probability": min(.95, max(.05, .15 + .65 * y + (i % 7) * .01)),
                "split_group": f"case-{i}",
                "fold": i % 5 + 1,
            })
    pd.DataFrame(rows).to_csv(tmp_path / "oof_predictions.csv", index=False)
    report = fit_calibrators(tmp_path)
    assert report["status"] == "research_only_not_independently_validated"
    assert all(report["horizons"][str(h)]["status"] == "fit_research_artifact" for h in (15, 30, 45, 60))
    assert (tmp_path / "probability_calibrators_research.joblib").exists()
    assert (tmp_path / "calibration_report.json").exists()


def test_calibrator_refuses_insufficient_class_support(tmp_path):
    (tmp_path / "metrics.json").write_text("{}")
    rows = [{
        "horizon_min": 15, "target": "squall_onset_within_15m",
        "target_value": 0, "oof_probability": .1,
        "split_group": f"case-{i}", "fold": i % 3,
    } for i in range(10)]
    pd.DataFrame(rows).to_csv(tmp_path / "oof_predictions.csv", index=False)
    report = fit_calibrators(tmp_path)
    assert report["horizons"]["15"]["status"] == "insufficient_data"
    assert not (tmp_path / "probability_calibrators_research.joblib").exists()
