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
