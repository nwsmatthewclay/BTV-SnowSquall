import pandas as pd

from processing.motion import add_motion_features


def test_motion_features_use_previous_scan_only():
    frame = pd.DataFrame([
        {"object_id": 1, "scan_time_utc": "2026-01-01T00:00:00Z", "centroid_lat": 44.0, "centroid_lon": -73.0},
        {"object_id": 1, "scan_time_utc": "2026-01-01T00:05:00Z", "centroid_lat": 44.05, "centroid_lon": -73.0},
    ])
    out = add_motion_features(frame)
    assert pd.isna(out.iloc[0]["motion_speed_kt"])
    assert out.iloc[1]["motion_speed_kt"] > 0
    assert 0 <= out.iloc[1]["motion_direction_deg"] <= 360
