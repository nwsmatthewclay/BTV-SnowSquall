import pandas as pd


def test_validation_review_matrix_remains_non_scoring(tmp_path):
    from scripts.build_modern_validation_review_matrix import build

    frame = tmp_path / "frame.csv"
    surface = tmp_path / "surface.csv"
    output = tmp_path / "out.csv"

    pd.DataFrame([{
        "episode_id": "SQE1",
        "duration_minutes": 60,
        "warning_count": 2,
        "year": 2024,
        "years": "2024",
        "duration_stratum": "60_to_180m",
        "warning_count_stratum": "2_to_4_warnings",
    }]).to_csv(frame, index=False)

    pd.DataFrame([
        {"episode_id": "SQE1", "station": "KBTV", "query_status": "success",
         "min_visibility_mi": 0.25, "max_wind_gust_kt": 30, "present_weather_codes": "SN"},
        {"episode_id": "SQE1", "station": "KMPV", "query_status": "success",
         "min_visibility_mi": 0.5, "max_wind_gust_kt": 35, "present_weather_codes": ""},
    ]).to_csv(surface, index=False)

    result = build(frame, surface, output)
    assert len(result) == 1
    assert result.iloc[0]["stations_queried"] == 2
    assert result.iloc[0]["minimum_visibility_mi"] == 0.25
    assert result.iloc[0]["maximum_gust_kt"] == 35
    assert result.iloc[0]["surface_evidence_review_status"] == "surface_visibility_at_or_below_0p25_sm"
    assert result.iloc[0]["training_eligible"] == False
