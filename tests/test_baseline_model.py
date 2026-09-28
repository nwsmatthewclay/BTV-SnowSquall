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
            ],
            "case_id": ["BTV20040315", "BTV20040315", None],
            "null_id": [None, None, "NULL0001"],
            "track_event_associated": [True, True, False],
            "squall_onset_within_15m": [1, 0, 0],
            "max_reflectivity_dbz": [20.0, 25.0, 10.0],
        }
    )
    schema = {
        "future_information_policy": "current_and_past_only",
        "predictor_columns": ["max_reflectivity_dbz"],
    }

    result, predictors = prepare_dataset(frame, schema, "squall_onset_within_15m")

    assert predictors == ["max_reflectivity_dbz"]
    assert set(result["split_group"]) == {"case:BTV20040315", "null:NULL0001"}
