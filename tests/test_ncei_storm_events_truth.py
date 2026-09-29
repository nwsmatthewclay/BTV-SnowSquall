from scripts.acquire_ncei_storm_events import filter_candidates


def test_filter_candidates_keeps_relevant_full_state_names():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {"STATE": "VERMONT", "EVENT_TYPE": "Snow Squall", "EVENT_ID": 1, "SOURCE": "NWS"},
            {"STATE": "NEW YORK", "EVENT_TYPE": "High Wind", "EVENT_ID": 2, "SOURCE": "NWS"},
            {"STATE": "VERMONT", "EVENT_TYPE": "Flood", "EVENT_ID": 3, "SOURCE": "NWS"},
            {"STATE": "PENNSYLVANIA", "EVENT_TYPE": "Snow Squall", "EVENT_ID": 4, "SOURCE": "NWS"},
        ]
    )
    out = filter_candidates(frame)

    assert set(out["EVENT_ID"]) == {1, 2}
    assert set(out["truth_source"]) == {"NCEI_STORM_EVENTS"}
    assert set(out["truth_status"]) == {"official_storm_event_record"}


def test_filter_candidates_does_not_treat_absence_as_a_negative():
    import pandas as pd

    frame = pd.DataFrame(
        [{"STATE": "VERMONT", "EVENT_TYPE": "Flood", "EVENT_ID": 10}]
    )
    out = filter_candidates(frame)

    assert out.empty


def test_storm_event_audit_uses_station_coordinates_and_iterrows():
    import pandas as pd
    from scripts.audit_storm_event_timing import audit

    events = pd.DataFrame(
        [
            {
                "EVENT_TYPE": "Snow Squall",
                "EVENT_ID": 99,
                "SOURCE": "NWS",
                "STATE": "VERMONT",
                "BEGIN_YEARMONTH": 200203,
                "BEGIN_DAY": 23,
                "BEGIN_TIME": 1711,
                "BEGIN_LAT": 44.47,
                "BEGIN_LON": -73.15,
            }
        ]
    )
    cases = pd.DataFrame(
        [
            {
                "case_id": "BTV20020323",
                "observing_station": "KBTV",
                "event_start_utc": "2002-03-23T22:11:00Z",
            }
        ]
    )
    stations = {"KBTV": (44.471955, -73.153276)}

    out = audit(events, cases, stations)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["timing_consistent"]
    assert row["site_consistent"]
    assert row["training_truth_eligible"]
    assert row["evidence_status"] == "timing_and_site_consistent"


def test_storm_event_audit_marks_timing_mismatch_without_making_a_positive():
    import pandas as pd
    from scripts.audit_storm_event_timing import audit

    events = pd.DataFrame(
        [
            {
                "EVENT_TYPE": "Snow Squall",
                "EVENT_ID": 100,
                "SOURCE": "NWS",
                "STATE": "VERMONT",
                "BEGIN_YEARMONTH": 200203,
                "BEGIN_DAY": 23,
                "BEGIN_TIME": 1811,
                "BEGIN_LAT": 44.47,
                "BEGIN_LON": -73.15,
            }
        ]
    )
    cases = pd.DataFrame(
        [
            {
                "case_id": "BTV20020323",
                "observing_station": "KBTV",
                "event_start_utc": "2002-03-23T22:11:00Z",
            }
        ]
    )

    out = audit(events, cases, {"KBTV": (44.471955, -73.153276)})

    assert len(out) == 1
    row = out.iloc[0]
    assert not row["timing_consistent"]
    assert row["site_consistent"]
    assert not row["training_truth_eligible"]
    assert row["evidence_status"] == "verified_but_timing_mismatch"
