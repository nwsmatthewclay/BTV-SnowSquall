import pandas as pd

from scripts.evaluate_temporal_holdout import filter_evaluation_population


def test_historical_context_requires_track_association_and_known_target():
    frame = pd.DataFrame([
        {
            "population": "historical_case_context_only",
            "track_event_associated": True,
            "label_status": "prospective_positive",
            "scan_time_utc": "2014-01-01T11:50:00Z",
            "case_event_start_utc": "2014-01-01T12:00:00Z",
            "squall_onset_within_15m": 1,
            "case_id": "CASE_A",
        },
        {
            "population": "historical_case_context_only",
            "track_event_associated": True,
            "label_status": "case_associated_nonimpact",
            "scan_time_utc": "2014-01-01T10:30:00Z",
            "case_event_start_utc": "2014-01-01T12:00:00Z",
            "squall_onset_within_15m": 0,
            "case_id": "CASE_A",
        },
        {
            "population": "historical_case_context_only",
            "track_event_associated": False,
            "label_status": "unassociated_object",
            "scan_time_utc": "2014-01-01T11:55:00Z",
            "case_event_start_utc": "2014-01-01T12:00:00Z",
            "squall_onset_within_15m": float("nan"),
            "case_id": "CASE_A",
        },
    ])
    result = filter_evaluation_population(frame, set())
    assert len(result) == 2
    assert set(result["squall_onset_within_15m"].astype(int)) == {0, 1}


def test_string_false_association_is_not_treated_as_true():
    frame = pd.DataFrame([
        {
            "population": "verified_case_context",
            "track_event_associated": "False",
            "supervision_class": "supervised_positive",
            "label_status": "case_associated_nonimpact",
            "scan_time_utc": "2014-01-01T11:50:00Z",
            "case_event_start_utc": "2014-01-01T12:00:00Z",
            "squall_onset_within_15m": 0,
            "case_id": "CASE_A",
        }
    ])
    result = filter_evaluation_population(frame, set())
    assert result.empty
