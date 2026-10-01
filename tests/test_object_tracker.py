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
