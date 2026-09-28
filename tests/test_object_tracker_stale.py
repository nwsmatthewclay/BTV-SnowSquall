from processing.object_tracker import CentroidTracker,TrackerConfig

def obj(row=10.0,column=10.0):
    return {"row_centroid":row,"column_centroid":column}

def test_stale_track_is_pruned_before_matching():
    tracker=CentroidTracker(TrackerConfig(max_pixel_distance=35,max_time_gap_minutes=10))
    first=tracker.update("2026-09-28T12:00:00Z",[obj()])[0]["object_id"]
    assert first==1
    second=tracker.update("2026-09-28T12:05:00Z",[obj(11,11)])[0]["object_id"]
    assert second==first
    third=tracker.update("2026-09-28T12:20:00Z",[obj(12,12)])[0]["object_id"]
    assert third!=first
    assert first not in tracker.tracks
    assert third in tracker.tracks

def test_state_round_trip_preserves_active_tracks():
    tracker=CentroidTracker()
    tracker.update("2026-09-28T12:00:00Z",[obj()])
    restored=CentroidTracker.from_state(tracker.to_state())
    assert restored.tracks[1].age_scans==1
    assert restored.next_id==2
