import json
from pathlib import Path

import pandas as pd

from scripts.score_model_replay import load_cases, radar_metrics, summarize_case


def test_radar_metrics_detects_pre_onset_crossing():
    onset = pd.Timestamp("2026-01-01T12:30:00Z")
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01T11:40:00Z",
            "2026-01-01T12:00:00Z",
            "2026-01-01T12:15:00Z",
        ], utc=True),
        "track_id": ["1", "1", "1"],
        "radar_site": ["KCXX", "KCXX", "KCXX"],
        "probability_15min": [0.05, 0.20, 0.60],
        "probability_30min": [0.10, 0.35, 0.70],
        "probability_45min": [0.10, 0.35, 0.70],
        "probability_60min": [0.10, 0.35, 0.70],
    })
    metrics = pd.DataFrame(radar_metrics(frame, onset))
    row = metrics[(metrics.horizon_min == 15) & (metrics.threshold == 0.5)].iloc[0]
    assert row["hit_within_horizon"]
    assert row["first_crossing_lead_min"] == 15.0


def test_case_summary_uses_best_radar_for_event_hit():
    radar = pd.DataFrame([
        {"case_id":"A","horizon_min":30,"threshold":0.25,"peak_pre_onset_probability":0.1,
         "peak_post_onset_30min_probability":0.5,"first_crossing_lead_min":float("nan"),
         "hit_within_horizon":False,"radar_site":"KCXX"},
        {"case_id":"A","horizon_min":30,"threshold":0.25,"peak_pre_onset_probability":0.6,
         "peak_post_onset_30min_probability":0.8,"first_crossing_lead_min":20.0,
         "hit_within_horizon":True,"radar_site":"KTYX"},
    ])
    result = summarize_case(radar)
    row = result.iloc[0]
    assert row["hit_within_horizon"] == 1
    assert row["peak_pre_onset_probability"] == 0.6
    assert row["first_crossing_lead_min"] == 20.0
