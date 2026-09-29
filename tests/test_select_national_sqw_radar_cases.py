import pandas as pd

from scripts.select_national_sqw_radar_cases import attach_radars, haversine_km


def test_haversine_reasonable():
    d = haversine_km(44.5, -73.2, 44.6, -73.2)
    assert 10 < d < 12


def test_attach_radars_selects_nearest_sites():
    frame = pd.DataFrame([{
        "case_id": "X",
        "warning_issue_utc": "2025-01-01T12:00:00Z",
        "warning_expire_utc": "2025-01-01T12:30:00Z",
        "wfo": "BTV",
        "lat": 44.5,
        "lon": -73.2,
        "iem_verified": True,
        "verifying_lsr_count": 2,
        "supervision_class": "warning_verified",
    }])
    locations = {
        "KCXX": (44.51111, -73.16639, 317.0),
        "KTYX": (43.75583, -75.68, 1846.0),
    }
    out = attach_radars(frame, locations, max_radars=1, max_range_km=230)
    assert len(out) == 1
    assert out.iloc[0]["radar_site"] == "KCXX"
    assert bool(out.iloc[0]["iem_verified"]) is True
