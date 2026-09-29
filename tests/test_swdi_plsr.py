import pandas as pd

from scripts.acquire_swdi_plsr import acquire_case


def test_plsr_pre_2005_is_explicitly_archive_unavailable():
    frame, status = acquire_case(
        pd.Series({
            "case_id": "BTV20020323",
            "observing_station": "KBTV",
            "event_start_utc": "2002-03-23T22:11:00Z",
        })
    )
    assert frame.empty
    assert status["status"] == "archive_not_available"
    assert "2005" in status["error"]


def test_plsr_records_are_explicitly_preliminary_evidence():
    import scripts.acquire_swdi_plsr as plsr

    original = plsr._bulk_year

    def fake_bulk(_year, _start, _end, _state):
        return pd.DataFrame({
            "VALID": ["2005-02-13 09:20:00+00:00"],
            "STATE": ["VT"],
            "LAT": [44.5],
            "LON": [-73.1],
        })

    plsr._bulk_year = fake_bulk
    try:
        frame, status = acquire_case(
            pd.Series({
                "case_id": "BTV20050213",
                "observing_station": "KBTV",
                "event_start_utc": "2005-02-13T09:24:00Z",
            })
        )
    finally:
        plsr._bulk_year = original

    assert status["status"] == "available"
    assert len(frame) == 1
    assert frame.loc[0, "truth_source"] == "NCEI_SWDI_PLSR"
    assert frame.loc[0, "truth_status"] == "preliminary_local_storm_report"
