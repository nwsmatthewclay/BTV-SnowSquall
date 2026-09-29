import pandas as pd

from scripts.acquire_swdi_plsr import acquire_case


def test_plsr_acquisition_records_unavailable_without_creating_truth():
    import scripts.acquire_swdi_plsr as plsr

    original = plsr._request

    def fail(_url):
        raise RuntimeError("service unavailable")

    plsr._request = fail
    try:
        frame, status = acquire_case(
            pd.Series(
                {
                    "case_id": "BTV20020323",
                    "observing_station": "KBTV",
                    "event_start_utc": "2002-03-23T22:11:00Z",
                }
            )
        )
    finally:
        plsr._request = original

    assert frame.empty
    assert status["status"] == "unavailable"
    assert status["record_count"] == 0


def test_plsr_records_are_explicitly_preliminary_evidence():
    import scripts.acquire_swdi_plsr as plsr

    class Response:
        text = "VALID,VALID2,LAT,LON\n2002-03-23 22:10,2002-03-23 22:10,44.5,-73.1\n"

        def raise_for_status(self):
            return None

    original = plsr._request
    plsr._request = lambda _url: Response()
    try:
        frame, status = acquire_case(
            pd.Series(
                {
                    "case_id": "BTV20020323",
                    "observing_station": "KBTV",
                    "event_start_utc": "2002-03-23T22:11:00Z",
                }
            )
        )
    finally:
        plsr._request = original

    assert status["status"] == "available"
    assert len(frame) == 1
    assert frame.loc[0, "truth_source"] == "NCEI_SWDI_PLSR"
    assert frame.loc[0, "truth_status"] == "preliminary_local_storm_report"
