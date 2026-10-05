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
