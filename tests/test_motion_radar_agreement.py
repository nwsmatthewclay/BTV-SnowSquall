import pandas as pd
from processing.motion import add_motion_features

def test_object_motion_reports_radar_agreement():
    frame=pd.DataFrame([
      {"object_id":1,"radar_site":"KCXX","scan_time_utc":"2026-01-01T00:00:00Z","centroid_lat":44.0,"centroid_lon":-73.0},
      {"object_id":1,"radar_site":"KCXX","scan_time_utc":"2026-01-01T00:05:00Z","centroid_lat":44.05,"centroid_lon":-73.0,
       "radar_motion_speed_kt":33.0,"radar_motion_direction_deg":0.0,"radar_motion_u_kt":0.0,"radar_motion_v_kt":33.0},
    ])
    out=add_motion_features(frame)
    assert out.iloc[1]["motion_speed_minus_radar_kt"] != 0
    assert out.iloc[1]["motion_direction_error_deg"] >= 0
    assert -1 <= out.iloc[1]["motion_radar_alignment"] <= 1
