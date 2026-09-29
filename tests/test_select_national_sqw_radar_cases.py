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


def test_radar_locations_excludes_terminal_identifiers(monkeypatch):
    import types
    import sys

    fake_module = types.SimpleNamespace(
        NEXRAD_LOCATIONS={
            "KCXX": {"lat": 44.511, "lon": -73.166, "elev": 317},
            "TBOS": {"lat": 42.1515, "lon": -70.9302, "elev": 264},
            "KTYX": {"lat": 43.756, "lon": -75.680, "elev": 1846},
        }
    )
    monkeypatch.setitem(sys.modules, "pyart", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pyart.io", types.SimpleNamespace(nexrad_common=fake_module))
    monkeypatch.setitem(sys.modules, "pyart.io.nexrad_common", fake_module)

    from scripts.select_national_sqw_radar_cases import radar_locations
    out = radar_locations()
    assert set(out) == {"KCXX", "KTYX"}
