import numpy as np
from processing.radar_storm_motion import estimate_radar_storm_motion


def test_radar_motion_recovers_eastward_shift():
    previous=np.zeros((80,80),dtype=float)
    previous[30:40,25:35]=45.0
    current=np.zeros_like(previous)
    current[30:40,29:39]=45.0
    result=estimate_radar_storm_motion(previous,current,5,spacing_km=1.0,max_shift_km=20)
    assert result is not None
    assert result["radar_motion_speed_kt"] > 4
    assert 70 <= result["radar_motion_direction_deg"] <= 110


def test_tracker_accepts_optional_radar_motion():
    from processing.object_tracker import CentroidTracker
    tracker=CentroidTracker()
    first=tracker.update("2026-01-01T12:00:00Z",[{
        "row_centroid":10,"column_centroid":10,"area_km2":25,"max_reflectivity_dbz":35
    }],radar_motion={
        "radar_motion_row_per_min":0.0,"radar_motion_column_per_min":1.0,
        "radar_motion_speed_kt":11.0,"radar_motion_direction_deg":90.0,
        "radar_motion_confidence":1.0
    })[0]["object_id"]
    second=tracker.update("2026-01-01T12:05:00Z",[{
        "row_centroid":10,"column_centroid":15,"area_km2":25,"max_reflectivity_dbz":35
    }],radar_motion={
        "radar_motion_row_per_min":0.0,"radar_motion_column_per_min":1.0,
        "radar_motion_speed_kt":11.0,"radar_motion_direction_deg":90.0,
        "radar_motion_confidence":1.0
    })[0]
    assert second["object_id"]==first
    assert second["radar_motion_direction_deg"]==90.0
