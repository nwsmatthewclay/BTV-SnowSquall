import pandas as pd

from processing.motion import add_motion_features


def test_motion_features_use_previous_scan_only():
    frame = pd.DataFrame([
        {"object_id": 1, "radar_site": "KCXX", "scan_time_utc": "2026-01-01T00:00:00Z", "centroid_lat": 44.0, "centroid_lon": -73.0},
        {"object_id": 1, "radar_site": "KCXX", "scan_time_utc": "2026-01-01T00:05:00Z", "centroid_lat": 44.05, "centroid_lon": -73.0},
    ])
    out = add_motion_features(frame)
    assert pd.isna(out.iloc[0]["motion_speed_kt"])
    assert out.iloc[1]["motion_speed_kt"] > 0
    assert 0 <= out.iloc[1]["motion_direction_deg"] <= 360


def test_motion_does_not_bridge_radar_sites_with_same_object_id():
    frame = pd.DataFrame([
        {"object_id": 1, "radar_site": "KCXX", "scan_time_utc": "2026-01-01T00:00:00Z", "centroid_lat": 44.0, "centroid_lon": -73.0},
        {"object_id": 1, "radar_site": "KTYX", "scan_time_utc": "2026-01-01T00:05:00Z", "centroid_lat": 43.0, "centroid_lon": -75.0},
    ])
    out = add_motion_features(frame)
    assert out["motion_speed_kt"].isna().all()


def test_implausible_centroid_jump_is_quarantined():
    import pandas as pd
    frame = pd.DataFrame([
        {
            "radar_site": "KCXX",
            "object_id": 1,
            "scan_time_utc": "2026-01-01T12:00:00Z",
            "centroid_lat": 44.0,
            "centroid_lon": -73.0,
        },
        {
            "radar_site": "KCXX",
            "object_id": 1,
            "scan_time_utc": "2026-01-01T12:05:00Z",
            "centroid_lat": 45.0,
            "centroid_lon": -74.0,
        },
    ])
    out = add_motion_features(frame)
    row = out.sort_values("scan_time_utc").iloc[-1]
    assert row["motion_qc_status"] == "implausible_displacement"
    assert row["motion_speed_kt_raw"] > 75.0
    assert pd.isna(row["motion_speed_kt"])
    assert pd.isna(row["motion_direction_deg"])
