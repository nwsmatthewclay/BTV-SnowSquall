import pandas as pd

from scripts.live_model_features import build_live_feature_frame
from snow_squall.evolution import add_environment_evolution_features


def test_environment_evolution_is_causal_and_resets_after_gap():
    frame = pd.DataFrame({
        "track_id": ["a", "a", "a", "a"],
        "timestamp": [
            "2026-01-01T12:00:00Z",
            "2026-01-01T12:05:00Z",
            "2026-01-01T12:10:00Z",
            "2026-01-01T12:30:00Z",
        ],
        "snsq": [0.5, 1.0, 1.5, 4.0],
        "cape_jkg": [50.0, 75.0, 100.0, 400.0],
        "mean_rh_0_2km_pct": [80.0, 82.0, 84.0, 99.0],
    })
    out = add_environment_evolution_features(
        frame,
        group_cols=["track_id"],
        time_col="timestamp",
        columns=("snsq", "cape_jkg", "mean_rh_0_2km_pct"),
    )

    assert out.loc[1, "snsq_delta"] == 0.5
    assert out.loc[2, "cape_jkg_change_2scan"] == 50.0
    assert pd.isna(out.loc[3, "snsq_delta"])
    assert pd.isna(out.loc[3, "cape_jkg_change_2scan"])


def test_live_adapter_exposes_environment_evolution():
    history = [
        {
            "timestamp": "2026-01-01T12:00:00Z",
            "track_id": "sq1",
            "snsq": 0.5,
            "cape_jkg": 50.0,
            "mean_rh_0_2km_pct": 80.0,
        },
        {
            "timestamp": "2026-01-01T12:05:00Z",
            "track_id": "sq1",
            "snsq": 1.0,
            "cape_jkg": 75.0,
            "mean_rh_0_2km_pct": 82.0,
        },
    ]
    out = build_live_feature_frame(history, "sq1")
    assert out.loc[1, "snsq_delta"] == 0.5
    assert out.loc[1, "cape_jkg_delta"] == 25.0
    assert out.loc[1, "mean_rh_0_2km_pct_delta"] == 2.0
