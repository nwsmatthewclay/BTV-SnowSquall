from datetime import datetime, timezone

from acquisition.narr_environment import narr_analysis_url
from processing.environment import provider_for_time


def test_pre_ruc_uses_narr():
    assert provider_for_time(datetime(2006, 2, 8, tzinfo=timezone.utc)) == "NARR"
    assert provider_for_time(datetime(2007, 4, 1, tzinfo=timezone.utc)) == "RUC"


def test_narr_analysis_url_uses_three_hour_archive():
    valid = datetime(2006, 2, 8, 4, 20, tzinfo=timezone.utc)
    url = narr_analysis_url(valid)
    assert url.endswith(
        "/model-narr-a-files/200602/20060208/"
        "narr-a_221_20060208_0300_000.grb"
    )
