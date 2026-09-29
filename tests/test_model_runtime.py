import json

import joblib
import numpy as np
import pandas as pd

from scripts.model_runtime import ModelRuntime


class FakeModel:
    def predict_proba(self, frame):
        n = len(frame)
        return np.column_stack([np.full(n, 0.6), np.full(n, 0.4)])


def test_candidate_model_is_not_live_enabled(tmp_path):
    (tmp_path / "metrics.json").write_text(
        json.dumps({
            "operational_release_status": "candidate_only",
            "predictor_columns": ["x"],
        }),
        encoding="utf-8",
    )
    joblib.dump(FakeModel(), tmp_path / "baseline_model.joblib")
    runtime = ModelRuntime.load(tmp_path)
    assert runtime.enabled is False
    assert runtime.score(pd.DataFrame({"x": [1.0]})) is None


def test_released_model_scores(tmp_path):
    (tmp_path / "metrics.json").write_text(
        json.dumps({
            "operational_release_status": "released",
            "predictor_columns": ["x"],
        }),
        encoding="utf-8",
    )
    joblib.dump(FakeModel(), tmp_path / "baseline_model.joblib")
    runtime = ModelRuntime.load(tmp_path)
    result = runtime.score(pd.DataFrame({"x": [1.0, 2.0]}))
    assert runtime.enabled is True
    assert result == [0.4, 0.4]


def test_missing_model_bundle_stays_disabled(tmp_path):
    runtime = ModelRuntime.load(tmp_path)
    assert runtime.enabled is False
    assert runtime.score(pd.DataFrame({"x": [1.0]})) is None


def test_model_horizon_is_read_from_target():
    runtime = ModelRuntime(metadata={"target": "squall_onset_within_45m"})
    assert runtime.horizon_minutes == 45


def test_unknown_model_horizon_is_none():
    runtime = ModelRuntime(metadata={"target": "snow_squall_probability"})
    assert runtime.horizon_minutes is None
