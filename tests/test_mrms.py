from datetime import datetime, timezone

from acquisition.mrms import (
    IEM_START,
    available_for_time,
    floor_product_time,
    raster_netcdf_url,
)


def test_mrms_availability_boundary():
    assert not available_for_time(datetime(2011, 3, 2, tzinfo=timezone.utc))
    assert available_for_time(datetime(2014, 10, 1, tzinfo=timezone.utc))


def test_mrms_time_is_never_future():
    radar = datetime(2018, 2, 10, 16, 29, 37, tzinfo=timezone.utc)
    valid = floor_product_time(radar, 2)
    assert valid <= radar
    assert valid.minute == 28


def test_mrms_url_is_deterministic():
    valid = datetime(2018, 2, 10, 16, 28, tzinfo=timezone.utc)
    url = raster_netcdf_url(valid, "mrms_lcref")
    assert "dstr=201802101628" in url
    assert "prod=mrms_lcref" in url
