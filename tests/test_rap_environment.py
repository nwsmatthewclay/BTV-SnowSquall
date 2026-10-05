from datetime import datetime, timezone

from acquisition.rap_environment import rap_analysis_url


def test_rap_analysis_url_uses_utc_cycle():
    valid = datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)
    url = rap_analysis_url(valid)
    assert url.endswith("/rap.20260928/rap.t01z.awp130pgrbf00.grib2")


def test_future_analysis_is_not_constructed_by_selector_contract():
    radar_time = datetime(2026, 9, 28, 1, 34, tzinfo=timezone.utc)
    candidate = radar_time.replace(minute=0)
    assert candidate <= radar_time


def test_rap_field_specs_use_canonical_cfgrib_levels():
    from processing.rap_features import FIELD_SPECS

    assert FIELD_SPECS["surface_temperature_k"] == ("heightAboveGround", "2t", 2)
    assert FIELD_SPECS["temperature_2m_k"] == ("heightAboveGround", "2t", 2)
    assert FIELD_SPECS["dewpoint_2m_k"] == ("heightAboveGround", "2d", 2)
    assert FIELD_SPECS["rh_2m_pct"] == ("heightAboveGround", "2r", 2)
    assert FIELD_SPECS["u10_ms"] == ("heightAboveGround", "10u", 10)
    assert FIELD_SPECS["v10_ms"] == ("heightAboveGround", "10v", 10)
    assert FIELD_SPECS["pwat_mm"] == ("atmosphereSingleLayer", "pwat", None)
    assert FIELD_SPECS["mlcape_jkg"] == ("pressureFromGroundLayer", "cape", 9000)
    assert FIELD_SPECS["mlcin_jkg"] == ("pressureFromGroundLayer", "cin", 9000)
    assert FIELD_SPECS["mucape_jkg"] == ("pressureFromGroundLayer", "cape", 18000)
    assert FIELD_SPECS["mucin_jkg"] == ("pressureFromGroundLayer", "cin", 18000)
