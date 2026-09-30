import pandas as pd
import pytest

from scripts.audit_live_feature_parity import audit_track


def test_replay_parity_matches_historical_and_live_feature_paths():
    raw = pd.DataFrame([
        {
            "timestamp": "2026-01-01T12:00:00Z",
            "track_id": "sq1",
            "radar_site": "KCXX",
            "max_reflectivity_dbz": 22.0,
            "mean_reflectivity_dbz": 16.0,
            "area_km2": 8.0,
            "length_km": 4.0,
            "width_km": 2.0,
            "core_pixel_count": 4,
            "pixel_count": 10,
            "motion_speed_kt": 22.0,
            "echo_top_km": 1.8,
            "zdr_mean_db": 0.5,
            "rhohv_mean": 0.99,
            "kdp_mean_degkm": 0.1,
            "velocity_mean_kt": 18.0,
            "cape_jkg": 150.0,
            "cin_jkg": -20.0,
            "shear_u_0_6km_ms": 8.0,
            "shear_v_0_6km_ms": 6.0,
        },
        {
            "timestamp": "2026-01-01T12:05:00Z",
            "track_id": "sq1",
            "radar_site": "KCXX",
            "max_reflectivity_dbz": 30.0,
            "mean_reflectivity_dbz": 20.0,
            "area_km2": 12.0,
            "length_km": 5.0,
            "width_km": 2.5,
            "core_pixel_count": 6,
            "pixel_count": 13,
            "motion_speed_kt": 24.0,
            "echo_top_km": 2.6,
            "zdr_mean_db": 0.7,
            "rhohv_mean": 0.98,
            "kdp_mean_degkm": 0.2,
            "velocity_mean_kt": 24.0,
            "cape_jkg": 170.0,
            "cin_jkg": -15.0,
            "shear_u_0_6km_ms": 8.0,
            "shear_v_0_6km_ms": 6.0,
        },
        {
            "timestamp": "2026-01-01T12:10:00Z",
            "track_id": "sq1",
            "radar_site": "KCXX",
            "max_reflectivity_dbz": 37.0,
            "mean_reflectivity_dbz": 23.0,
            "area_km2": 17.0,
            "length_km": 6.0,
            "width_km": 2.7,
            "core_pixel_count": 9,
            "pixel_count": 18,
            "motion_speed_kt": 27.0,
            "echo_top_km": 3.3,
            "zdr_mean_db": 0.9,
            "rhohv_mean": 0.97,
            "kdp_mean_degkm": 0.4,
            "velocity_mean_kt": 30.0,
            "cape_jkg": 200.0,
            "cin_jkg": -10.0,
            "shear_u_0_6km_ms": 8.0,
            "shear_v_0_6km_ms": 6.0,
        },
    ])

    result = audit_track(
        raw,
        [
            "max_reflectivity_dbz",
            "max_reflectivity_dbz_delta",
            "max_reflectivity_dbz_rate_per_min",
            "area_km2_change_2scan",
            "area_km2_rate_2scan_per_min",
            "echo_top_km_rate_per_min",
            "motion_speed_kt_trailing_mean_3",
            "shear_0_6km_kt",
            "cape_shear_product",
        ],
        "sq1",
    )

    assert result["status"] == "pass"
    assert result["mismatch_count"] == 0
    assert result["comparable_predictors"] == 9


def test_replay_parity_detects_causal_feature_drift():
    raw = pd.DataFrame([
        {
            "timestamp": "2026-01-01T12:00:00Z",
            "track_id": "sq2",
            "radar_site": "KCXX",
            "max_reflectivity_dbz": 20.0,
            "area_km2": 8.0,
        },
        {
            "timestamp": "2026-01-01T12:05:00Z",
            "track_id": "sq2",
            "radar_site": "KCXX",
            "max_reflectivity_dbz": 30.0,
            "area_km2": 12.0,
        },
    ])

    result = audit_track(
        raw,
        ["max_reflectivity_dbz_rate_per_min"],
        "sq2",
    )
    assert result["status"] == "pass"

    mutated = raw.copy()
    mutated.loc[1, "max_reflectivity_dbz"] = 99.0
    drift = audit_track(
        mutated,
        ["max_reflectivity_dbz_rate_per_min"],
        "sq2",
    )
    assert drift["status"] == "pass"
