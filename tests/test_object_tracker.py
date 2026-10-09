"""Tests for physically gated, persistence-aware object tracking."""
from processing.object_tracker import CentroidTracker

def obj(row, col, area=25, z=35):
    return {"row_centroid":row,"column_centroid":col,"pixel_count":int(area),
            "area_km2":float(area),"max_reflectivity_dbz":float(z)}

def test_time_scaled_gate_rejects_unrealistic_fast_scan_jump():
    t=CentroidTracker()
    first=t.update("2026-01-01T12:00:00Z",[obj(10,10)])[0]["object_id"]
    second=t.update("2026-01-01T12:05:00Z",[obj(10,22)])[0]["object_id"]
    assert second!=first

def test_longer_gap_allows_physically_plausible_motion():
    t=CentroidTracker()
    first=t.update("2026-01-01T12:00:00Z",[obj(10,10)])[0]["object_id"]
    second=t.update("2026-01-01T12:10:00Z",[obj(10,22)])[0]["object_id"]
    assert second==first

def test_large_area_jump_does_not_swap_track_identity():
    t=CentroidTracker()
    first=t.update("2026-01-01T12:00:00Z",[obj(10,10,25)])[0]["object_id"]
    second=t.update("2026-01-01T12:05:00Z",[obj(10,11,1000)])[0]["object_id"]
    assert second!=first

def test_single_missed_scan_can_recover():
    t=CentroidTracker()
    first=t.update("2026-01-01T12:00:00Z",[obj(10,10)])[0]["object_id"]
    assert t.update("2026-01-01T12:05:00Z",[])==[]
    second=t.update("2026-01-01T12:10:00Z",[obj(10,12)])[0]["object_id"]
    assert second==first


def test_matched_track_emits_association_diagnostics():
    t=CentroidTracker()
    t.update("2026-01-01T12:00:00Z",[obj(10,10)])
    row=t.update("2026-01-01T12:05:00Z",[obj(10,11)])[0]
    assert row["track_association_status"]=="matched"
    assert row["track_association_distance_px"] > 0
    assert row["track_association_gate_px"] > row["track_association_distance_px"]
    assert row["track_association_cost"] >= 0
    assert row["track_age_scans"] == 2


def test_radar_motion_persists_in_track_velocity():
    t=CentroidTracker()
    radar={"radar_motion_row_per_min":0.0,"radar_motion_column_per_min":1.0,
           "radar_motion_confidence":1.0}
    first=t.update("2026-01-01T12:00:00Z",[obj(10,10)],radar_motion=radar)[0]
    assert first["track_motion_source"]=="radar_prior"
    second=t.update("2026-01-01T12:05:00Z",[obj(10,14)],radar_motion=radar)[0]
    assert second["track_motion_source"]=="object_radar_blend"
    assert second["track_motion_radar_weight"] > 0
    assert second["track_velocity_column_per_min"] > 0

def test_low_confidence_radar_motion_does_not_overwrite_object_motion():
    t=CentroidTracker()
    t.update("2026-01-01T12:00:00Z",[obj(10,10)])
    radar={"radar_motion_row_per_min":0.0,"radar_motion_column_per_min":-10.0,
           "radar_motion_confidence":0.0}
    row=t.update("2026-01-01T12:05:00Z",[obj(10,12)],radar_motion=radar)[0]
    assert row["track_motion_source"]=="object_only"
    assert row["track_motion_radar_weight"]==0.0
    assert row["track_velocity_column_per_min"] > 0


def test_tracker_identity_overrides_scan_local_detector_id():
    t = CentroidTracker()
    first = t.update(
        "2026-01-01T12:00:00Z",
        [{"object_id": 1, **obj(10, 10)}],
    )[0]
    second = t.update(
        "2026-01-01T12:05:00Z",
        [{"object_id": 7, **obj(10, 11)}],
    )[0]
    assert second["object_id"] == first["object_id"]
    assert second["track_id"] == first["track_id"]
    assert first["detector_object_id"] == 1
    assert second["detector_object_id"] == 7


def test_tracker_new_object_gets_unique_track_identity():
    t = CentroidTracker()
    first = t.update(
        "2026-01-01T12:00:00Z",
        [{"object_id": 1, **obj(10, 10)}],
    )[0]
    second = t.update(
        "2026-01-01T12:05:00Z",
        [{"object_id": 1, **obj(10, 30)}],
    )[0]
    assert second["object_id"] != first["object_id"]
    assert second["track_id"] != first["track_id"]


def test_two_missed_scans_can_recover_same_track():
    t = CentroidTracker()
    first = t.update("2026-01-01T12:00:00Z", [obj(10, 10)])[0]["object_id"]
    assert t.update("2026-01-01T12:05:00Z", []) == []
    assert t.update("2026-01-01T12:10:00Z", []) == []
    third = t.update("2026-01-01T12:15:00Z", [obj(10, 13)])[0]["object_id"]
    assert third == first


def test_three_missed_scans_end_track_identity():
    t = CentroidTracker()
    first = t.update("2026-01-01T12:00:00Z", [obj(10, 10)])[0]["object_id"]
    assert t.update("2026-01-01T12:05:00Z", []) == []
    assert t.update("2026-01-01T12:10:00Z", []) == []
    assert t.update("2026-01-01T12:15:00Z", []) == []
    replacement = t.update("2026-01-01T12:20:00Z", [obj(10, 13)])[0]["object_id"]
    assert replacement != first


def test_track_age_is_persistent_and_emitted_on_each_observation():
    t = CentroidTracker()
    first = t.update("2026-01-01T12:00:00Z", [obj(10, 10)])[0]
    second = t.update("2026-01-01T12:05:00Z", [obj(10, 11)])[0]
    assert first["track_age_min"] == 0.0
    assert second["track_age_min"] == 5.0
    assert second["track_first_scan_utc"].startswith("2026-01-01T12:00:00")


def test_moving_object_keeps_identity_through_short_action_gap():
    t = CentroidTracker()
    first = t.update("2026-01-01T12:00:00Z", [obj(10, 10)])[0]["object_id"]
    # Simulates an Actions delay long enough to miss several radar scans but
    # still within the live track-retention window.
    second = t.update("2026-01-01T12:25:00Z", [obj(10, 30)])[0]
    assert second["object_id"] == first
    assert second["track_association_status"] == "matched"
    assert second["track_association_distance_px"] > 0


def test_track_history_persists_positions_across_state_restore():
    t = CentroidTracker()
    first = t.update("2026-01-01T12:00:00Z", [obj(10, 10)])[0]
    second = t.update("2026-01-01T12:05:00Z", [obj(10, 12)])[0]
    restored = CentroidTracker.from_state(t.to_state())
    third = restored.update("2026-01-01T12:10:00Z", [obj(10, 14)])[0]

    assert third["track_id"] == first["track_id"] == second["track_id"]
    history = third["track_position_history"]
    assert [row["timestamp"] for row in history] == [
        "2026-01-01T12:00:00Z",
        "2026-01-01T12:05:00Z",
        "2026-01-01T12:10:00Z",
    ]
    assert [row["column"] for row in history] == [10.0, 12.0, 14.0]


def test_out_of_order_scan_is_rejected_without_rewinding_track():
    t = CentroidTracker()
    first = t.update("2026-01-01T12:10:00Z", [obj(10, 10)])[0]
    before = t.to_state()

    import pytest
    with pytest.raises(ValueError, match="Out-of-order or duplicate radar scan rejected"):
        t.update("2026-01-01T12:05:00Z", [obj(10, 9)])

    assert t.to_state() == before
    next_row = t.update("2026-01-01T12:15:00Z", [obj(10, 12)])[0]
    assert next_row["track_id"] == first["track_id"]
    assert next_row["track_position_history"][-1]["timestamp"] == "2026-01-01T12:15:00Z"


def test_duplicate_scan_timestamp_is_rejected():
    t = CentroidTracker()
    t.update("2026-01-01T12:10:00Z", [obj(10, 10)])
    import pytest
    with pytest.raises(ValueError, match="Out-of-order or duplicate radar scan rejected"):
        t.update("2026-01-01T12:10:00Z", [obj(10, 11)])
