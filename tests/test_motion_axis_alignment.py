import pandas as pd
from scripts.live_model_features import build_live_feature_row

def test_band_axis_alignment_is_bounded():
    row=build_live_feature_row({
      "timestamp":"2026-01-01T12:05:00Z","track_id":"1",
      "orientation_deg":90.0,"motion_direction_deg":90.0,
      "radar_motion_direction_deg":0.0,"motion_speed_kt":20.0
    })
    assert row["motion_axis_alignment"] == 1.0
    assert row["radar_motion_axis_alignment"] == 0.0
