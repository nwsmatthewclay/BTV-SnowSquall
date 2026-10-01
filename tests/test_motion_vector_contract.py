import pandas as pd
from processing.motion import add_motion_features
from scripts.live_model_features import build_live_feature_row

def test_motion_vectors_avoid_direction_wraparound():
    frame=pd.DataFrame([
      {"object_id":1,"radar_site":"KCXX","scan_time_utc":"2026-01-01T00:00:00Z","centroid_lat":44.0,"centroid_lon":-73.0},
      {"object_id":1,"radar_site":"KCXX","scan_time_utc":"2026-01-01T00:05:00Z","centroid_lat":44.05,"centroid_lon":-73.0},
    ])
    out=add_motion_features(frame)
    assert out.iloc[1]["motion_v_kt"] > 0
    assert abs(out.iloc[1]["motion_u_kt"]) < out.iloc[1]["motion_speed_kt"]

def test_live_motion_vector_contract():
    row=build_live_feature_row({
      "timestamp":"2026-01-01T12:05:00Z","track_id":"1",
      "motion_speed_kt":20.0,"motion_direction_deg":90.0,
      "radar_motion_speed_kt":18.0,"radar_motion_direction_deg":90.0,
      "radar_motion_u_kt":18.0,"radar_motion_v_kt":0.0,
    })
    assert row["motion_u_kt"] > 19.9
