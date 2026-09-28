from datetime import datetime, timezone
from acquisition.ruc_environment import ruc_analysis_url


def test_ruc_analysis_url_uses_hourly_historical_archive():
    valid = datetime(2006, 2, 8, 0, 0, tzinfo=timezone.utc)
    url = ruc_analysis_url(valid)
    assert url.endswith(
        "/model-ruc130anl-old/200602/20060208/"
        "ruc2anl_130_20060208_0000_000.grb2"
    )
