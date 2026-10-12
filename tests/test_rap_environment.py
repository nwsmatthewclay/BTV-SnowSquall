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



def test_ncei_rap_analysis_urls_use_historical_filename():
    from acquisition.rap_environment import ncei_rap_analysis_urls

    valid = datetime(2018, 11, 21, 17, 0, tzinfo=timezone.utc)
    urls = list(ncei_rap_analysis_urls(valid))
    assert any(
        url.endswith("/model-rap130anl/201811/20181121/rap_130_20181121_1700_000.grb2")
        for url in urls
    )


def test_ncei_old_rap_archive_is_in_candidate_urls():
    from acquisition.rap_environment import ncei_rap_analysis_urls

    valid = datetime(2013, 7, 23, 23, 0, tzinfo=timezone.utc)
    urls = list(ncei_rap_analysis_urls(valid))
    assert any("/model-rap130anl-old/" in url for url in urls)

def test_find_forecast_stops_at_newest_available_cycle(monkeypatch):
    from acquisition import rap_environment as rap

    radar_time = datetime(2026, 10, 11, 20, 23, tzinfo=timezone.utc)
    checked = []
    monkeypatch.setattr(rap, "_url_exists", lambda url: checked.append(url) or True)

    match = rap.find_forecast(radar_time, target_minutes=30)

    assert match is not None
    assert match.cycle_time == datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
    assert match.valid_time == datetime(2026, 10, 11, 21, 0, tzinfo=timezone.utc)
    assert match.lead_hours == 1
    assert checked == [rap.rap_forecast_url(match.cycle_time, match.lead_hours)]


def test_find_forecast_falls_back_only_when_newest_cycle_missing(monkeypatch):
    from acquisition import rap_environment as rap

    radar_time = datetime(2026, 10, 11, 20, 23, tzinfo=timezone.utc)
    checked = []
    newest_url = rap.rap_forecast_url(
        datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc), 1
    )

    def available(url):
        checked.append(url)
        return url != newest_url

    monkeypatch.setattr(rap, "_url_exists", available)
    match = rap.find_forecast(radar_time, target_minutes=30)

    assert match is not None
    assert match.cycle_time == datetime(2026, 10, 11, 19, 0, tzinfo=timezone.utc)
    assert match.valid_time == datetime(2026, 10, 11, 21, 0, tzinfo=timezone.utc)
    assert checked == [
        newest_url,
        rap.rap_forecast_url(match.cycle_time, match.lead_hours),
    ]

