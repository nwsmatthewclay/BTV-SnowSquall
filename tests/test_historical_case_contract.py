import csv
from pathlib import Path


def test_historical_case_crosswalk_covers_all_36_banacos_cases():
    root = Path(__file__).parents[1]
    with (root / "data/historical/case_id_crosswalk.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 36
    assert all(row["source_study_case_id"] and row["historical_case_id"] for row in rows)
    assert len({row["source_study_case_id"] for row in rows}) == 36
    assert len({row["historical_case_id"] for row in rows}) == 36


def test_replay_windows_are_five_minute_causal_steps():
    root = Path(__file__).parents[1]
    with (root / "data/historical/replay_windows.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 1000
    offsets = sorted({int(row["offset_min"]) for row in rows})
    assert offsets[0] == -60
    assert offsets[-1] == 90
    assert all((b - a) == 5 for a, b in zip(offsets, offsets[1:]))
    assert all(row["valid_time_utc"] <= row["event_start_utc"] for row in rows if int(row["offset_min"]) <= 0)
