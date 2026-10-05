import numpy as np

from scripts.train_candidate_ensemble import class_balanced_weights, estimator


def test_class_balanced_weights_equalizes_class_totals():
    weights = class_balanced_weights(np.array([0, 0, 0, 1], dtype=int))
    assert np.isclose(weights[0], 2.0 / 3.0)
    assert np.isclose(weights[3], 2.0)
    assert np.isclose(weights[:3].sum(), weights[3])


def test_candidate_ensemble_estimator_has_three_fixed_members():
    model = estimator()
    assert model.named_steps['model'].voting == 'soft'
    assert [name for name, _ in model.named_steps['model'].estimators] == ['hgb', 'rf', 'extra']


def test_limited_data_bootstrap_explicitly_bypasses_strict_contract(tmp_path):
    import json
    import pandas as pd
    import pytest
    from scripts.train_baseline_model import prepare_dataset

    frame = pd.DataFrame([
        {
            "population": "verified_case_context",
            "supervision_class": "supervised_positive",
            "label_status": "prospective_positive",
            "track_event_associated": False,
            "case_id": "case-1",
            "null_id": "",
            "episode_id": "episode-1",
            "target": 1,
            "area_km2": 10.0,
        },
        {
            "population": "winter_null_candidate",
            "supervision_class": "",
            "label_status": "",
            "track_event_associated": False,
            "case_id": "",
            "null_id": "null-1",
            "episode_id": "",
            "target": 0,
            "area_km2": 5.0,
        },
        {
            "population": "winter_null_candidate",
            "supervision_class": "",
            "label_status": "",
            "track_event_associated": False,
            "case_id": "",
            "null_id": "null-2",
            "episode_id": "",
            "target": 0,
            "area_km2": 6.0,
        },
    ])
    schema = {
        "predictor_columns": ["area_km2"],
        "operational_predictor_columns": ["area_km2"],
        "future_information_policy": "current_and_past_only",
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    data, predictors = prepare_dataset(
        frame,
        schema,
        "target",
        enforce_training_contract=False,
    )
    assert len(data) == 3
    assert predictors == ["area_km2"]

    with pytest.raises(ValueError, match="Training radar/environment contract missing columns"):
        prepare_dataset(frame, schema, "target", enforce_training_contract=True)
