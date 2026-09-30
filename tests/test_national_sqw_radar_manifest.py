import pandas as pd

from scripts.select_national_sqw_radar_cases import attach_radars


def test_attach_radars_preserves_warning_label_geometry():
    frame = pd.DataFrame([{
        "case_id": "NSQWTEST",
        "warning_issue_utc": "2024-01-10T12:00:00Z",
        "warning_expire_utc": "2024-01-10T13:00:00Z",
        "lat": 44.0,
        "lon": -73.0,
        "wfo": "BTV",
        "iem_verified": True,
        "verifying_lsr_count": 2,
        "supervision_class": "warning_verified",
    }])
    locations = {"KCXX": (44.5, -73.2, 100.0)}
    result = attach_radars(frame, locations, max_radars=1, max_range_km=230.0)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["warning_issue_utc"] == "2024-01-10T12:00:00Z"
    assert row["lat"] == 44.0
    assert row["lon"] == -73.0
