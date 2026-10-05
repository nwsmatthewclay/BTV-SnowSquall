import pandas as pd

from scripts.evaluate_event_thresholds import build_case_table, threshold_metrics


def test_event_threshold_uses_case_level_hits_and_null_window_false_alerts():
    cases = pd.DataFrame({
        "case_id": ["CASE1", "CASE2"],
        "event_start_utc": [
            "2026-01-01T01:00:00Z",
            "2026-01-02T01:00:00Z",
        ],
    })
    pred = pd.DataFrame({
        "split_group": ["case:CASE1", "case:CASE1", "case:CASE2", "null:N1", "null:N1"],
        "population": [
            "verified_case_context", "verified_case_context",
            "verified_case_context",
            "winter_null_candidate", "winter_null_candidate",
        ],
        "case_id": ["CASE1", "CASE1", "CASE2", None, None],
        "null_id": [None, None, None, "N1", "N1"],
        "radar_site": ["KCXX", "KCXX", "KTYX", "KCXX", "KTYX"],
        "object_id": ["O1", "O1", "O2", "N1O1", "N1O1"],
        "scan_time_utc": pd.to_datetime([
            "2026-01-01T00:30:00Z",
            "2026-01-01T00:45:00Z",
            "2026-01-02T00:30:00Z",
            "2026-01-03T00:30:00Z",
            "2026-01-03T00:40:00Z",
        ], utc=True),
        "probability": [0.55, 0.70, 0.10, 0.65, 0.20],
    })

    table = build_case_table(pred, cases, "probability")
    metrics = threshold_metrics(table, pred.assign(_event_start_dt=pd.NaT), "probability")
    row = metrics.loc[metrics["threshold"].eq(0.60)].iloc[0]

    assert row["positive_cases"] == 2
    assert row["positive_hits"] == 1
    assert row["null_windows"] == 1
    assert row["false_alert_windows"] == 1
    assert abs(row["pod"] - 0.5) < 1e-12
    assert abs(row["false_alarm_ratio"] - 0.5) < 1e-12
