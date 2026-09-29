import pandas as pd

from scripts.live_model_features import build_live_feature_frame, build_live_feature_row, feature_coverage


def test_live_row_maps_environment_and_units():
    row = build_live_feature_row({
        "timestamp": "2026-01-01T12:05:00Z",
        "track_id": "7",
        "max_reflectivity_dbz": 36.0,
        "mean_reflectivity_dbz": 28.0,
        "area_km2": 24.0,
        "gust_ms": 10.0,
        "visibility_m": 1200.0,
        "cape_jkg": 180.0,
        "cin_jkg": -35.0,
        "shear_0_6km_ms": 12.0,
    })
    assert row["reflectivity_max_dbz"] == 36.0
    assert row["reflectivity_mean_dbz"] == 28.0
    assert row["wind_gust_kt"] > 19.0
    assert 0.74 < row["visibility_sm"] < 0.75
    assert row["sbcape_jkg"] == 180.0
    assert row["sbcin_jkg"] == -35.0
    assert row["shear_0_6km_kt"] > 23.0
    assert row["reflectivity_core_excess"] == 8.0


def test_live_feature_frame_adds_current_past_evolution_only():
    history = [
        {
            "timestamp": "2026-01-01T12:00:00Z",
            "track_id": "7",
            "centroid_lat": 44.0,
            "centroid_lon": -73.0,
            "max_reflectivity_dbz": 20.0,
            "mean_reflectivity_dbz": 15.0,
            "area_km2": 10.0,
        },
        {
            "timestamp": "2026-01-01T12:05:00Z",
            "track_id": "7",
            "centroid_lat": 44.03,
            "centroid_lon": -73.0,
            "max_reflectivity_dbz": 26.0,
            "mean_reflectivity_dbz": 19.0,
            "area_km2": 12.0,
        },
        {
            "timestamp": "2026-01-01T12:12:00Z",
            "track_id": "7",
            "centroid_lat": 44.04,
            "centroid_lon": -73.0,
            "max_reflectivity_dbz": 32.0,
            "mean_reflectivity_dbz": 21.0,
            "area_km2": 15.0,
        },
    ]
    frame = build_live_feature_frame(history, "7")
    assert len(frame) == 3
    assert pd.isna(frame.iloc[0]["max_reflectivity_dbz_delta"])
    assert frame.iloc[1]["max_reflectivity_dbz_delta"] == 6.0
    assert frame.iloc[1]["track_scan_index"] == 1
    assert frame.iloc[1]["motion_speed_kmh"] > 0
    assert frame.iloc[2]["max_reflectivity_dbz_delta"] == 6.0
    assert frame.iloc[2]["area_km2_rate_per_min"] > 0


def test_feature_coverage_reports_missing_predictors():
    frame = pd.DataFrame({"a": [1.0], "b": [None]})
    coverage = feature_coverage(frame, ["a", "b", "c"])
    assert coverage["predictors"] == 3
    assert coverage["available"] == 1
    assert coverage["fraction"] == 0.333
    assert coverage["missing"] == ["b", "c"]
