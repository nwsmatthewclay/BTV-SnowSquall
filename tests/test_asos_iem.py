import pandas as pd

from acquisition.asos_iem import standardize
from scripts.audit_surface_truth import audit


def test_standardize_visibility_and_wind():
    source = pd.DataFrame({
        "station": ["KBTV", "KBTV"],
        "valid": ["2010-11-27T17:00:00Z", "2010-11-27T17:05:00Z"],
        "vsby": [1.0, 0.2],
        "sknt": [15, 20],
        "gust": [25, 30],
        "peak_wind_gust": [26, 31],
        "drct": [300, 310],
        "tmpf": [32, 31],
        "dwpf": [28, 27],
    })
    result = standardize(source)
    assert result.loc[0, "visibility_mi"] == 1.0
    assert result.loc[1, "visibility_le_0p4km"]
    assert result.loc[1, "wind_gust_kt"] == 30


def test_surface_audit_finds_timing(tmp_path):
    root = tmp_path / "surface"
    station = root / "KBTV"
    station.mkdir(parents=True)
    pd.DataFrame({
        "valid": [
            "2010-11-27T16:45:00Z",
            "2010-11-27T17:05:00Z",
        ],
        "visibility_m": [1600, 300],
        "visibility_le_0p8km": [False, True],
        "visibility_le_0p4km": [False, True],
        "wind_gust_kt": [20, 31],
        "peak_wind_gust_kt": [20, 31],
    }).to_csv(station / "CASE.csv", index=False)

    cases = pd.DataFrame({
        "case_id": ["CASE"],
        "event_start_utc": ["2010-11-27T17:00:00Z"],
        "observing_station": ["KBTV"],
        "min_visibility_km": [0.4],
        "peak_wind_kt": [31],
    })
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)

    result = audit(cases_path, root)
    assert len(result) == 1
    assert result.loc[0, "surface_timing_consistent"]
    assert result.loc[0, "maximum_peak_wind_gust_kt"] == 31


def test_iem_request_retries_transient_503(monkeypatch):
    import requests
    import pandas as pd
    from acquisition import asos_iem

    calls = {"n": 0}

    class FakeResponse:
        def raise_for_status(self):
            if calls["n"] < 2:
                raise requests.HTTPError(
                    "503 Server Error",
                    response=type("R", (), {"status_code": 503})(),
                )

        text = (
            "station,valid,vsby,sknt,gust\n"
            "KBTV,2010-11-27 17:00,1.0,15,25\n"
        )

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return FakeResponse()

    monkeypatch.setattr(asos_iem.requests, "get", fake_get)
    monkeypatch.setattr(asos_iem.time, "sleep", lambda _: None)

    result = asos_iem.request_observations(
        "KBTV",
        pd.Timestamp("2010-11-27T16:00:00Z"),
        pd.Timestamp("2010-11-27T18:00:00Z"),
    )
    assert calls["n"] == 3
    assert len(result) == 1
