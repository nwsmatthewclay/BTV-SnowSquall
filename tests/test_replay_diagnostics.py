import pytest

from scripts.replay_diagnostics import summarize


def test_replay_diagnostics_finds_peak_and_threshold_crossings():
    timeline = {
        "future_information_policy": "one_scan_at_a_time",
        "alignment_gap_count": 0,
        "records": [
            {"timestamp": "2020-01-01T12:00:00Z", "track_id": "1",
             "cumulative_probabilities": {"15": 0.08, "30": 0.05, "45": 0.02, "60": 0.01}},
            {"timestamp": "2020-01-01T12:05:00Z", "track_id": "1",
             "cumulative_probabilities": {"15": 0.30, "30": 0.22, "45": 0.15, "60": 0.10}},
            {"timestamp": "2020-01-01T12:10:00Z", "track_id": "1",
             "cumulative_probabilities": {"15": 0.80, "30": 0.70, "45": 0.50, "60": 0.35}},
        ],
    }

    report = summarize(timeline, onset_utc="2020-01-01T12:25:00Z")
    assert report["record_count"] == 3
    assert report["track_count"] == 1
    assert report["horizons"]["15"]["peak_probability"] == pytest.approx(0.80)
    assert report["horizons"]["15"]["first_threshold_crossings_utc"]["0.25"] == "2020-01-01T12:05:00Z"
    assert report["threshold_lead_time_minutes"]["15"]["0.25"] == pytest.approx(20.0)


def test_replay_diagnostics_does_not_invent_missing_scores():
    timeline = {
        "records": [
            {"timestamp": "2020-01-01T12:00:00Z", "track_id": "1", "cumulative_probabilities": {}},
        ]
    }
    report = summarize(timeline)
    assert report["horizons"]["15"]["record_count"] == 0
    assert report["horizons"]["15"]["peak_probability"] is None
