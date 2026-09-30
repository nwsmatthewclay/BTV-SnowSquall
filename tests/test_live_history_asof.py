from scripts.process_live_volume import history_rows_as_of


def test_history_rows_as_of_excludes_future_and_invalid_rows():
    rows = [
        {"timestamp": "2026-01-01T12:00:00Z", "value": "past"},
        {"timestamp": "2026-01-01T12:05:00Z", "value": "future"},
        {"timestamp": "not-a-time", "value": "invalid"},
    ]
    result = history_rows_as_of(rows, "2026-01-01T12:00:00Z")
    assert [row["value"] for row in result] == ["past"]


def test_history_rows_as_of_keeps_same_scan_time():
    rows = [
        {"timestamp": "2026-01-01T12:05:00Z", "value": "current"},
        {"timestamp": "2026-01-01T12:00:00Z", "value": "past"},
    ]
    result = history_rows_as_of(rows, "2026-01-01T12:05:00Z")
    assert [row["value"] for row in result] == ["past", "current"]
