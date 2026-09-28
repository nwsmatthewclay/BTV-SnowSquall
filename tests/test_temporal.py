import pandas as pd
import pytest
from snow_squall.temporal import add_track_history_features
from snow_squall.inference import ObjectProbabilityState

def test_track_history_is_past_only():
    frame = pd.DataFrame({
        "object_id": [1, 1, 1],
        "scan_time": ["2026-01-01T00:00Z", "2026-01-01T00:05Z", "2026-01-01T00:10Z"],
        "max_reflectivity_dbz": [25, 35, 45],
    })
    out = add_track_history_features(frame)
    assert pd.isna(out.iloc[0]["reflectivity_delta_5min"])
    assert out.iloc[1]["reflectivity_delta_5min"] == 10
    assert out.iloc[2]["reflectivity_delta_10min"] == 20

def test_probability_state_tracks_trend():
    state = ObjectProbabilityState.create(7)
    state.update("2026-01-01T00:00Z", 0.10)
    state.update("2026-01-01T00:05Z", 0.30)
    assert state.trend() == pytest.approx(0.20)
