import pandas as pd

from scripts.evaluate_temporal_holdout import filter_evaluation_population


def base_frame():
    return pd.DataFrame({
        "population": [
            "verified_case_context",
            "verified_case_context",
            "winter_null_candidate",
            "winter_null_candidate",
        ],
        "supervision_class": [
            "supervised_positive",
            "supervised_positive",
            "null_candidate",
            "null_candidate",
        ],
        "label_status": [
            "prospective_positive",
            "verified_event_interval",
            "unknown",
            "unknown",
        ],
        "track_event_associated": [True, True, False, False],
        "case_id": ["C1", "C1", None, None],
        "null_id": [None, None, "N1", "N2"],
        "activity_class": ["", "", "high_activity_hard_negative_candidate", "quiet"],
        "scan_time_utc": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T01:00:00Z",
            "2026-01-02T00:00:00Z",
            "2026-01-03T00:00:00Z",
        ],
        "case_event_start_utc": [
            "2026-01-01T01:30:00Z",
            "2026-01-01T00:30:00Z",
            None,
            None,
        ],
    })


def test_unreviewed_hard_negative_candidates_are_excluded():
    filtered = filter_evaluation_population(base_frame(), set())
    assert "N1" not in set(filtered["null_id"].dropna())
    assert "N2" in set(filtered["null_id"].dropna())
    assert len(filtered) == 2


def test_reviewed_hard_negative_is_admitted():
    filtered = filter_evaluation_population(base_frame(), {"N1"})
    assert {"N1", "N2"}.issubset(set(filtered["null_id"].dropna()))
    assert len(filtered) == 3


def test_post_onset_case_rows_are_excluded():
    filtered = filter_evaluation_population(base_frame(), set())
    assert filtered["case_event_start_utc"].astype(str).eq("2026-01-01T00:30:00+00:00").sum() == 0
