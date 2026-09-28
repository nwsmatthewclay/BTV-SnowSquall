import pandas as pd


def test_surface_impact_summary_extracts_visibility_and_gust():
    from scripts.build_modern_sqw_surface_impact_inventory import summarize_station

    frame = pd.DataFrame([
        {"valid": "2024-01-01T00:00:00Z", "visibility_mi": 2.5, "wind_gust_kt": 20, "wxcodes": "SN"},
        {"valid": "2024-01-01T00:10:00Z", "visibility_mi": 0.5, "wind_gust_kt": 35, "wxcodes": "SN,BLSN"},
        {"valid": "2024-01-01T00:20:00Z", "visibility_mi": 0.125, "wind_gust_kt": 30, "wxcodes": "SN"},
    ])
    result = summarize_station(frame)
    assert result["surface_rows"] == 3
    assert result["min_visibility_mi"] == 0.125
    assert result["max_wind_gust_kt"] == 35.0
    assert result["first_visibility_le_0p5_sm_utc"] == "2024-01-01T00:10:00Z"
    assert result["first_visibility_le_0p25_sm_utc"] == "2024-01-01T00:20:00Z"
    assert "SN" in result["present_weather_codes"]
