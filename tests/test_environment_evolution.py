import pandas as pd

from snow_squall.evolution import add_environment_evolution_features, add_motion_evolution_features
from scripts.live_model_features import build_live_feature_frame


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


def test_motion_evolution_is_causal_and_tracks_turning():
    frame = pd.DataFrame({
        "track_id": ["m", "m", "m", "m"],
        "timestamp": [
            "2026-01-01T12:00:00Z",
            "2026-01-01T12:05:00Z",
            "2026-01-01T12:10:00Z",
            "2026-01-01T12:15:00Z",
        ],
        "centroid_lat": [44.00, 44.05, 44.10, 44.10],
        "centroid_lon": [-73.00, -73.00, -72.95, -72.90],
        "motion_speed_kt": [20.0, 24.0, 28.0, 30.0],
        "motion_dir_deg": [0.0, 0.0, 45.0, 90.0],
        "max_reflectivity_dbz_rate_per_min": [None, 0.5, 1.0, 1.5],
        "area_km2_rate_per_min": [None, 0.5, 1.0, 1.5],
    })
    out = add_motion_evolution_features(
        frame,
        group_cols=["track_id"],
        time_col="timestamp",
    )
    assert out.loc[1, "motion_speed_kt_delta"] == 4.0
    assert out.loc[2, "motion_turn_deg"] == 45.0
    assert out.loc[3, "motion_turn_rate_deg_per_min"] == 9.0
    assert 0 < out.loc[2, "motion_straightness_3"] <= 1
    assert pd.isna(out.loc[0, "motion_speed_kt_delta"])


def test_live_adapter_exposes_environment_and_motion_evolution():
    history = [
        {
            "timestamp": "2026-01-01T12:00:00Z",
            "track_id": "sq1",
            "centroid_lat": 44.00,
            "centroid_lon": -73.00,
            "snsq": 0.5,
            "cape_jkg": 50.0,
            "mean_rh_0_2km_pct": 80.0,
            "motion_speed_kt": 20.0,
            "motion_direction_deg": 0.0,
            "max_reflectivity_dbz": 25.0,
            "area_km2": 10.0,
        },
        {
            "timestamp": "2026-01-01T12:05:00Z",
            "track_id": "sq1",
            "centroid_lat": 44.05,
            "centroid_lon": -73.00,
            "snsq": 1.0,
            "cape_jkg": 75.0,
            "mean_rh_0_2km_pct": 82.0,
            "motion_speed_kt": 24.0,
            "motion_direction_deg": 0.0,
            "max_reflectivity_dbz": 28.0,
            "area_km2": 12.0,
        },
        {
            "timestamp": "2026-01-01T12:10:00Z",
            "track_id": "sq1",
            "centroid_lat": 44.10,
            "centroid_lon": -72.95,
            "snsq": 1.5,
            "cape_jkg": 100.0,
            "mean_rh_0_2km_pct": 84.0,
            "motion_speed_kt": 28.0,
            "motion_direction_deg": 45.0,
            "max_reflectivity_dbz": 33.0,
            "area_km2": 15.0,
        },
    ]
    out = build_live_feature_frame(history, "sq1")
    assert out.loc[1, "snsq_delta"] == 0.5
    assert out.loc[1, "cape_jkg_delta"] == 25.0
    assert out.loc[1, "motion_speed_kt_delta"] == 4.0
    assert out.loc[2, "motion_turn_deg"] == 45.0
