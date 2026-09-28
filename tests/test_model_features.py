import pandas as pd

from scripts.build_model_features import build_features, write_schema


def test_model_features_are_causal():
    source = pd.DataFrame(
        {
            "population": ["verified_case_context"] * 3,
            "radar_site": ["KCXX"] * 3,
            "object_id": [7] * 3,
            "scan_time_utc": [
                "2006-02-07T12:00:00Z",
                "2006-02-07T12:05:00Z",
                "2006-02-07T12:10:00Z",
            ],
            "centroid_lat": [44.0, 44.05, 44.10],
            "centroid_lon": [-73.0, -73.0, -73.0],
            "max_reflectivity_dbz": [20.0, 30.0, 40.0],
            "mean_reflectivity_dbz": [15.0, 20.0, 25.0],
            "area_km2": [10.0, 20.0, 40.0],
            "length_km": [5.0, 7.0, 9.0],
            "width_km": [2.0, 3.0, 4.0],
            "pixel_count": [10, 20, 40],
            "core_pixel_count": [2, 5, 10],
            "squall_onset_within_15m": [0, 0, 1],
            "label_status": ["unknown", "prospective_positive", "verified_event_interval"],
            "future_information_policy": ["past_and_current_only"] * 3,
        }
    )
    result = build_features(source)

    assert "squall_onset_within_15m" in result.columns
    assert "label_status" in result.columns
    assert "max_reflectivity_dbz_delta" in result.columns
    assert "area_km2_rate_per_min" in result.columns
    assert "motion_speed_kmh" in result.columns

    # First observation has no prior observation; later rows use only prior data.
    assert pd.isna(result.loc[0, "max_reflectivity_dbz_delta"])
    assert result.loc[1, "max_reflectivity_dbz_delta"] == 10.0
    assert result.loc[2, "max_reflectivity_dbz_delta"] == 10.0

    # Running maximum at t=5 min cannot know the t=10 min value.
    assert result.loc[1, "max_reflectivity_dbz_running_max"] == 30.0


def test_schema_blocks_targets_and_identifiers(tmp_path):
    frame = pd.DataFrame(
        {
            "population": ["verified_case_context"],
            "case_id": ["BTV20040315"],
            "radar_site": ["KCXX"],
            "object_id": [1],
            "scan_time_utc": ["2006-02-07T12:00:00Z"],
            "max_reflectivity_dbz": [20.0],
            "squall_onset_within_15m": [0],
        }
    )
    schema_path = tmp_path / "schema.json"
    features = build_features(frame)
    schema = write_schema(features, schema_path)

    assert "max_reflectivity_dbz" in schema["predictor_columns"]
    assert "case_id" not in schema["predictor_columns"]
    assert "squall_onset_within_15m" in schema["target_columns"]
    assert "squall_onset_within_15m" not in schema["predictor_columns"]


def test_schema_blocks_case_context_numeric_fields(tmp_path):
    frame = pd.DataFrame(
        {
            "population": ["verified_case_context"],
            "case_id": ["BTV20040315"],
            "radar_site": ["KCXX"],
            "object_id": [1],
            "scan_time_utc": ["2006-02-07T12:00:00Z"],
            "max_reflectivity_dbz": [20.0],
            "case_peak_wind_kt": [31.0],
            "case_min_visibility_km": [0.4],
            "surface_visibility_m": [500.0],
            "squall_onset_within_15m": [0],
        }
    )
    features = build_features(frame)
    schema_path = tmp_path / "schema.json"
    schema = write_schema(features, schema_path)

    assert "max_reflectivity_dbz" in schema["predictor_columns"]
    assert "case_peak_wind_kt" not in schema["predictor_columns"]
    assert "case_min_visibility_km" not in schema["predictor_columns"]
    assert "surface_visibility_m" not in schema["predictor_columns"]
