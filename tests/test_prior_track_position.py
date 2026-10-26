import numpy as np

from scripts.process_live_volume import prior_position_from_track_history


def test_prior_position_uses_penultimate_tracker_history_point():
    lat = np.array([[44.0, 44.0], [45.0, 45.0]])
    lon = np.array([[-74.0, -73.0], [-74.0, -73.0]])
    history = [
        {"timestamp": "2026-10-25T12:00:00Z", "row": 0.25, "column": 0.75, "age_scans": 1},
        {"timestamp": "2026-10-25T12:10:00Z", "row": 0.50, "column": 0.50, "age_scans": 2},
    ]

    previous = prior_position_from_track_history(history, lat, lon)

    assert previous is not None
    assert previous["timestamp"] == "2026-10-25T12:00:00Z"
    assert abs(previous["lat"] - 44.25) < 1e-8
    assert abs(previous["lon"] - (-73.25)) < 1e-8


def test_prior_position_requires_two_observed_track_points():
    lat = np.array([[44.0, 44.0], [45.0, 45.0]])
    lon = np.array([[-74.0, -73.0], [-74.0, -73.0]])
    assert prior_position_from_track_history([], lat, lon) is None
    assert prior_position_from_track_history(
        [{"timestamp": "2026-10-25T12:00:00Z", "row": 0.0, "column": 0.0}],
        lat,
        lon,
    ) is None
