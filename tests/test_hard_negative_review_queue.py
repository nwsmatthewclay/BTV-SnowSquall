import pandas as pd

from scripts.build_hard_negative_review_queue import build


def test_hard_negative_queue_flags_vigorous_null_window_without_labeling_it():
    frame = pd.DataFrame({
        "population": [
            "winter_null_candidate", "winter_null_candidate",
            "winter_null_candidate",
        ],
        "null_id": ["N1", "N1", "N2"],
        "radar_site": ["KCXX", "KTYX", "KCXX"],
        "max_reflectivity_dbz": [42.0, 38.0, 20.0],
        "base_reflectivity_max_dbz": [43.0, 39.0, 21.0],
        "core_pixel_count": [10, 0, 0],
        "velocity_p90_abs_kt": [25, 22, 5],
        "base_velocity_p90_abs_kt": [24, 21, 5],
        "area_km2": [150, 120, 20],
        "track_scan_count_to_date": [3, 4, 1],
        "environment_contract_ok": [True, True, True],
        "activity_class": ["high_activity_hard_negative_candidate", "high_activity_hard_negative_candidate", "quiet"],
    })

    table, summary = build(frame)
    n1 = table.loc[table["null_id"].eq("N1")].iloc[0]

    assert bool(n1["review_recommended"])
    assert n1["hard_negative_score"] >= 4
    assert summary.iloc[0]["review_candidates"] == 1
    assert "diagnostic_review_only" in summary.iloc[0]["policy"]


def test_surface_snow_and_low_visibility_increase_review_priority(tmp_path):
    surface = pd.DataFrame({
        "null_id": ["N1", "N1"],
        "valid": pd.to_datetime([
            "2026-01-01T00:30:00Z",
            "2026-01-01T00:45:00Z",
        ], utc=True),
        "visibility_m": [700.0, 650.0],
        "wind_gust_kt": [28.0, 30.0],
        "wxcodes": ["SN", "SN"],
    })

    table = pd.DataFrame({
        "population": ["winter_null_candidate", "winter_null_candidate"],
        "null_id": ["N1", "N1"],
        "radar_site": ["KCXX", "KTYX"],
        "max_reflectivity_dbz": [32.0, 31.0],
        "base_reflectivity_max_dbz": [33.0, 32.0],
        "core_pixel_count": [0, 0],
        "velocity_p90_abs_kt": [10, 11],
        "base_velocity_p90_abs_kt": [9, 10],
        "area_km2": [40, 45],
        "track_scan_count_to_date": [2, 2],
        "environment_contract_ok": [True, True],
        "activity_class": ["moderate_activity", "moderate_activity"],
    })

    from scripts.build_hard_negative_review_queue import build
    result, summary = build(table, surface=surface)
    row = result.loc[result["null_id"].eq("N1")].iloc[0]

    assert row["surface_report_count"] == 2
    assert row["surface_snow_reports"] == 2
    assert row["surface_min_visibility_m"] == 650.0
    assert row["surface_max_gust_kt"] == 30.0
    assert bool(row["review_recommended"])
    assert "nearby_surface_snow_report" in row["review_reasons"]
    assert "nearby_surface_visibility_le_0p8km" in row["review_reasons"]


def test_mixed_rasn_is_not_counted_as_pure_snow_and_station_counts_are_conditional():
    surface = pd.DataFrame({
        "null_id": ["N1", "N1", "N1"],
        "station": ["KBTV", "KPBG", "KMPV"],
        "visibility_m": [900.0, 700.0, 600.0],
        "wind_gust_kt": [20.0, 30.0, 28.0],
        "wxcodes": ["RASN", "SN", "BLSN"],
    })
    frame = pd.DataFrame({
        "population": ["winter_null_candidate"] * 3,
        "null_id": ["N1"] * 3,
        "radar_site": ["KCXX", "KCXX", "KTYX"],
        "max_reflectivity_dbz": [30.0, 31.0, 29.0],
        "base_reflectivity_max_dbz": [31.0, 32.0, 30.0],
        "core_pixel_count": [0, 0, 0],
        "velocity_p90_abs_kt": [8, 9, 7],
        "base_velocity_p90_abs_kt": [8, 9, 7],
        "area_km2": [40, 41, 39],
        "track_scan_count_to_date": [2, 2, 2],
        "environment_contract_ok": [True, True, True],
        "activity_class": ["moderate_activity"] * 3,
    })
    result, _ = build(frame, surface=surface)
    row = result.iloc[0]

    assert row["surface_snow_reports"] == 2
    assert row["surface_mixed_reports"] == 1
    assert row["surface_snow_station_count"] == 2
    assert row["surface_mixed_station_count"] == 1
