import pandas as pd

from acquisition.mping import bbox_for_point, ptype_bucket, acquire_cases


def test_mping_ptype_bucket_is_conservative():
    assert ptype_bucket("Rain/Snow", "Snow") == "snow"
    assert ptype_bucket("Rain/Snow", "Sleet/Ice Pellets") == "mixed"
    assert ptype_bucket("Rain/Snow", "Freezing Rain") == "freezing_rain"
    assert ptype_bucket("Rain/Snow", "Rain") == "rain"
    assert ptype_bucket("Other", "Unknown") == "other"


def test_mping_bbox_contains_requested_point():
    bbox = [float(x) for x in bbox_for_point(44.5, -73.2, 75).split(",")]
    min_lon, min_lat, max_lon, max_lat = bbox
    assert min_lat < 44.5 < max_lat
    assert min_lon < -73.2 < max_lon


def test_mping_missing_key_is_fail_soft(tmp_path, monkeypatch):
    monkeypatch.delenv("MPING_API_KEY", raising=False)
    cases = tmp_path / "cases.csv"
    cases.write_text(
        "case_id,event_start_utc\n"
        "CASE1,2020-01-02T12:00:00Z\n",
        encoding="utf-8",
    )
    out = tmp_path / "mping.csv"
    status = tmp_path / "mping_status.json"

    summary = acquire_cases(cases, out, status)

    assert summary["status"] == "disabled_no_api_key"
    assert pd.read_csv(out).empty
    assert status.exists()
