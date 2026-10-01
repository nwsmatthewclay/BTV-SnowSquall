import pandas as pd
from scripts.audit_object_tracking import audit

def test_tracking_audit_reports_quality_metrics():
    d=pd.DataFrame({
      "radar_site":["KCXX","KCXX","KCXX","KCXX"],
      "object_id":[1,1,2,2],
      "scan_time_utc":["2026-01-01T00:00:00Z","2026-01-01T00:05:00Z","2026-01-01T00:00:00Z","2026-01-01T00:05:00Z"],
      "motion_speed_kt":[None,35,None,100],
      "motion_direction_deg":[None,90,None,180],
      "radar_motion_speed_kt":[None,32,None,32],
      "radar_motion_direction_deg":[None,88,None,182],
      "radar_motion_confidence":[0,.8,0,.9],
      "touches_grid_edge":[False,False,False,True],
    })
    r=audit(d)
    assert r["tracks"]==2
    assert r["multi_scan_tracks"]==2
    assert r["impossible_speed_over_90kt"]==1
    assert r["radar_motion_high_confidence"]==2
    assert r["median_object_radar_motion_direction_error_deg"]==2.0


def test_tracking_audit_reports_fragmentation_metrics():
    d=pd.DataFrame({
      "radar_site":["KCXX","KCXX","KCXX"],
      "object_id":[1,2,2],
      "scan_time_utc":["2026-01-01T00:00:00Z","2026-01-01T00:00:00Z","2026-01-01T00:05:00Z"],
      "motion_speed_kt":[None,None,20],
      "radar_motion_speed_kt":[None,None,18],
      "radar_motion_confidence":[0,0,.8],
      "touches_grid_edge":[False,False,False],
    })
    r=audit(d)
    assert r["tracks"]==2
    assert r["singleton_tracks"]==1
    assert r["multi_scan_tracks"]==1
    assert r["singleton_track_fraction"]==0.5
