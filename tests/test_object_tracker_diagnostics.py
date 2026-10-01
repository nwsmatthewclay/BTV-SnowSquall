from processing.object_tracker import CentroidTracker, TrackerConfig

def obj(row,col,area=25,z=35):
    return {"row_centroid":row,"column_centroid":col,"area_km2":area,"max_reflectivity_dbz":z}

def test_tracker_emits_split_merge_competition_diagnostics():
    t=CentroidTracker(TrackerConfig(max_pixel_distance=12))
    first=t.update("2026-01-01T00:00:00Z",[obj(10,10)])[0]
    out=t.update("2026-01-01T00:05:00Z",[obj(10,9),obj(10,11)])
    assert len(out)==2
    assert any(x["track_split_candidate"] for x in out) or any(x["track_merge_candidate"] for x in out)
    assert all("track_competing_track_count" in x for x in out)
