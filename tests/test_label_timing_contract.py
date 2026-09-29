from pathlib import Path

import pandas as pd


def test_historical_label_pipeline_has_explicit_post_onset_guard():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts/label_historical_outcomes.py").read_text(encoding="utf-8")
    baseline = (root / "scripts/train_baseline_model.py").read_text(encoding="utf-8")

    assert "scan < start <= future_end" in script
    assert '"verified_event_interval"' in script
    assert "scan_dt < onset_dt" in baseline
    assert "post_onset_exclusion_policy" in baseline


def test_horizon_labels_are_monotonic_when_present():
    frame = pd.DataFrame({
        "squall_onset_within_15m": [0, 1, 0],
        "squall_onset_within_30m": [0, 1, 1],
        "squall_onset_within_45m": [0, 1, 1],
        "squall_onset_within_60m": [0, 1, 1],
    })
    for left, right in zip((15, 30, 45), (30, 45, 60)):
        assert not (
            frame[f"squall_onset_within_{left}m"].eq(1)
            & frame[f"squall_onset_within_{right}m"].eq(0)
        ).any()
