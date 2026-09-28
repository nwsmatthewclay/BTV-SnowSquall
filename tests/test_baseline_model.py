import json

import pandas as pd

from scripts.train_baseline_model import prepare_dataset


def test_baseline_split_group_is_case_or_null():
    frame = pd.DataFrame(
        {
            "population": [
                "verified_case_context",
                "verified_case_context",
                "winter_null_candidate",
                "winter_null_candidate",
            ],
            "case_id": ["BTV20040315", "BTV20040315", None, None],
            "null_id": [None, None, "NULL0001", "NULL0002"],
            "track_event_associated": [True, True, False, False],
            "squall_onset_within_15m": [1, 0, 0, 0],
            "max_reflectivity_dbz": [20.0, 25.0, 10.0, 12.0],
        }
    )
    schema = {
        "future_information_policy": "current_and_past_only",
        "predictor_columns": ["max_reflectivity_dbz"],
    }

    result, predictors = prepare_dataset(frame, schema, "squall_onset_within_15m")

    assert predictors == ["max_reflectivity_dbz"]
    assert set(result["split_group"]) == {
        "case:BTV20040315", "null:NULL0001", "null:NULL0002"
    }
    assert len(result.loc[result["population"] == "winter_null_candidate"]) == 2
    assert result.loc[result["population"] == "winter_null_candidate", "squall_onset_within_15m"].eq(0).all()


def test_baseline_excludes_post_onset_case_rows():
    frame = pd.DataFrame(
        {
            "population": [
                "verified_case_context",
                "verified_case_context",
                "winter_null_candidate",
                "winter_null_candidate",
            ],
            "case_id": ["CASE1", "CASE1", None, None],
            "null_id": [None, None, "NULL0001", "NULL0002"],
            "track_event_associated": [True, True, False, False],
            "label_status": [
                "prospective_positive",
                "verified_event_interval",
                "unknown",
                "unknown",
            ],
            "squall_onset_within_15m": [1, 0, 0, 0],
            "max_reflectivity_dbz": [30.0, 45.0, 10.0, 12.0],
        }
    )
    schema = {
        "future_information_policy": "current_and_past_only",
        "predictor_columns": ["max_reflectivity_dbz"],
    }

    result, _ = prepare_dataset(frame, schema, "squall_onset_within_15m")

    assert len(result) == 3
    assert not (result["label_status"] == "verified_event_interval").any()
