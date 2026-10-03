from scripts.live_model_features import build_live_feature_row
from snow_squall.environment_contract import assess_environment, flatten_environment


def complete_env():
    return {
        "source": "RAP",
        "status": "complete",
        "source_valid_time_utc": "2026-10-03T14:00:00Z",
        "age_minutes": 20.0,
        "fields": {
            "cape_jkg": 150.0,
            "pwat_mm": 15.0,
            "temperature_2m_k": 268.0,
            "dewpoint_2m_k": 266.0,
            "rh_2m_pct": 86.0,
            "u10_ms": 4.0,
            "v10_ms": -2.0,
        },
    }


def test_flatten_environment_promotes_nested_fields():
    row = flatten_environment({
        "timestamp": "2026-10-03T14:20:00Z",
        "environment": complete_env(),
    })
    assert row["cape_jkg"] == 150.0
    assert row["u10_ms"] == 4.0
    assert row["environment_source"] == "RAP"
    assert row["environment_status"] == "complete"
    assert row["environment_age_minutes"] == 20.0


def test_complete_environment_is_model_ready():
    row = {
        "timestamp": "2026-10-03T14:20:00Z",
        "environment": complete_env(),
    }
    result = assess_environment(row, max_age_minutes=90)
    assert result["ready"] is True
    assert result["missing_fields"] == []
    assert result["reasons"] == []


def test_stale_environment_is_not_model_ready():
    row = {
        "timestamp": "2026-10-03T15:45:00Z",
        "environment": complete_env(),
    }
    result = assess_environment(row, max_age_minutes=90)
    assert result["ready"] is False
    assert "environment_stale" in result["reasons"]


def test_live_feature_row_uses_nested_environment_without_special_caller_logic():
    current = {
        "timestamp": "2026-10-03T14:20:00Z",
        "track_id": "7",
        "max_reflectivity_dbz": 36.0,
        "mean_reflectivity_dbz": 28.0,
        "area_km2": 24.0,
        "environment": complete_env(),
    }
    row = build_live_feature_row(current)
    assert row["cape_jkg"] == 150.0
    assert row["pwat_mm"] == 15.0
    assert row["temperature_2m_k"] == 268.0
    assert row["dewpoint_2m_k"] == 266.0
    assert row["rh_2m_pct"] == 86.0
    assert row["surface_wind_speed_kt"] > 0
