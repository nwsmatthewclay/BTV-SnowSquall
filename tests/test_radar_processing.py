import numpy as np

from processing.object_detector import detect_reflectivity_objects
from processing.object_tracker import CentroidTracker
from processing.radar_features import object_field_summary, velocity_object_summary


def test_object_field_summary_and_velocity_texture():
    values = np.array([1.0, 2.0, 3.0, np.nan])
    summary = object_field_summary(values, "zdr")
    assert summary["zdr_mean"] == 2.0
    assert summary["zdr_max"] == 3.0
    assert summary["zdr_p90"] > 2.5

    velocity = velocity_object_summary(values, gradient=np.ones(4))
    assert velocity["velocity_mean"] == 2.0
    assert velocity["velocity_std_kt"] > 0
    assert velocity["velocity_p90_abs_kt"] > 2.0
    assert velocity["velocity_gradient"] == 1.0


def test_detector_finds_candidate():
    field = np.zeros((20, 20))
    field[5:10, 5:10] = 45
    objects = detect_reflectivity_objects(field)
    assert len(objects) == 1
    assert objects[0]["max_reflectivity_dbz"] == 45


def test_tracker_reuses_nearby_track():
    tracker = CentroidTracker()
    first = tracker.update(
        "2026-01-01T00:00:00Z",
        [{
            "row_centroid": 5, "column_centroid": 5,
            "pixel_count": 30, "max_reflectivity_dbz": 40,
            "mean_reflectivity_dbz": 30, "core_pixel_count": 10,
        }],
    )
    second = tracker.update(
        "2026-01-01T00:05:00Z",
        [{
            "row_centroid": 7, "column_centroid": 6,
            "pixel_count": 35, "max_reflectivity_dbz": 42,
            "mean_reflectivity_dbz": 31, "core_pixel_count": 12,
        }],
    )
    assert first[0]["object_id"] == second[0]["object_id"]


def test_tracker_state_round_trip():
    tracker = CentroidTracker()
    tracker.update(
        "2026-01-01T00:00:00Z",
        [{"row_centroid": 10, "column_centroid": 20}],
    )

    restored = CentroidTracker.from_state(tracker.to_state())
    second = restored.update(
        "2026-01-01T00:05:00Z",
        [{"row_centroid": 11, "column_centroid": 21}],
    )

    assert second[0]["object_id"] == 1
    assert restored.next_id == 2
