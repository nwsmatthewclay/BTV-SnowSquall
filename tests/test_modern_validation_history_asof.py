from scripts.score_modern_validation import history_rows_as_of


def test_modern_validation_history_is_as_of():
    rows = [
        {"timestamp": "2020-01-01T00:00:00Z", "max_reflectivity_dbz": 20},
        {"timestamp": "2020-01-01T00:05:00Z", "max_reflectivity_dbz": 35},
        {"timestamp": "2020-01-01T00:10:00Z", "max_reflectivity_dbz": 50},
        {"timestamp": "not-a-time", "max_reflectivity_dbz": 99},
    ]

    out = history_rows_as_of(rows, "2020-01-01T00:05:00Z")

    assert [row["timestamp"] for row in out] == [
        "2020-01-01T00:00:00Z",
        "2020-01-01T00:05:00Z",
    ]


def test_modern_validation_history_handles_bad_cutoff():
    rows = [{"timestamp": "2020-01-01T00:00:00Z"}]
    assert history_rows_as_of(rows, "bad-cutoff") == []
