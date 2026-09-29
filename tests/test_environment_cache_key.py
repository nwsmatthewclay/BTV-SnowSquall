from datetime import datetime, timezone

from processing.environment import environment_cache_key, provider_for_time


def test_environment_cache_key_uses_narr_three_hour_cadence():
    early = datetime(2005, 2, 13, 1, 10, tzinfo=timezone.utc)
    later = datetime(2005, 2, 13, 2, 55, tzinfo=timezone.utc)

    assert provider_for_time(early) == "NARR"
    assert environment_cache_key(early) == environment_cache_key(later)


def test_environment_cache_key_uses_hourly_ruc_and_rap_cadence():
    ruc = datetime(2010, 2, 13, 1, 10, tzinfo=timezone.utc)
    rap = datetime(2018, 2, 13, 1, 10, tzinfo=timezone.utc)

    assert provider_for_time(ruc) == "RUC"
    assert provider_for_time(rap) == "RAP"

    assert environment_cache_key(ruc) == environment_cache_key(
        ruc.replace(minute=59)
    )
    assert environment_cache_key(ruc) != environment_cache_key(
        ruc.replace(hour=2)
    )
    assert environment_cache_key(rap) == environment_cache_key(
        rap.replace(minute=59)
    )
    assert environment_cache_key(rap) != environment_cache_key(
        rap.replace(hour=2)
    )
