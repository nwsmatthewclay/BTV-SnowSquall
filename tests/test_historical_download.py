from datetime import datetime, timezone

from acquisition.historical_download import parse_volume_time


def test_level2_volume_filename_timestamp_parsing():
    value = parse_volume_time(
        "2020/01/02/KCXX/KCXX20200102_120530_V06",
        "KCXX",
    )
    assert value == datetime(2020, 1, 2, 12, 5, 30, tzinfo=timezone.utc)


def test_level2_volume_parser_rejects_wrong_radar():
    assert parse_volume_time(
        "2020/01/02/KTYX/KTYX20200102_120530_V06",
        "KCXX",
    ) is None
