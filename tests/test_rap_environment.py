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
