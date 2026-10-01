import pandas as pd
from src.snow_squall.analogs import AnalogLibrary, add_causal_analog_features

def base():
    return pd.DataFrame({
        "case_id": ["A", "B", "C", "D"],
        "scan_time_utc": ["2026-01-01T12:00:00Z", "2026-01-02T12:00:00Z", "2026-01-03T12:00:00Z", "2026-01-01T11:00:00Z"],
        "max_reflectivity_dbz": [30, 31, 32, 30],
        "mean_reflectivity_dbz": [25, 26, 27, 25],
        "area_km2": [10, 11, 12, 10],
        "snsq": [1.0, 1.1, 1.2, 1.0],
        "cape_jkg": [100, 110, 120, 100],
        "squall_onset_within_15m": [1, 0, 1, 1],
        "squall_onset_within_30m": [1, 0, 1, 1],
        "squall_onset_within_45m": [1, 0, 1, 1],
        "squall_onset_within_60m": [1, 0, 1, 1],
    })

def test_analogs_are_strictly_historical_and_exclude_current_case():
    out = add_causal_analog_features(base(), top_k=10)
    assert out.loc[1, "analog_count"] == 3
    assert out.loc[2, "analog_count"] == 3

def test_analog_outcomes_use_other_case_history_only():
    d = pd.DataFrame({
        "case_id": ["A", "A", "B"],
        "scan_time_utc": ["2026-01-01T12:00:00Z", "2026-01-01T12:05:00Z", "2026-01-02T12:00:00Z"],
        "max_reflectivity_dbz": [30, 31, 31],
        "snsq": [1, 1, 1],
        "squall_onset_within_15m": [1, 1, 0],
        "squall_onset_within_30m": [1, 1, 0],
        "squall_onset_within_45m": [1, 1, 0],
        "squall_onset_within_60m": [1, 1, 0],
    })
    out = add_causal_analog_features(d, top_k=10)
    assert out.loc[2, "analog_case_count"] == 1
    assert out.loc[2, "analog_onset_rate_15m"] == 0.0

def test_library_survives_sparse_fields():
    d = base()[["case_id", "scan_time_utc", "max_reflectivity_dbz",
               "squall_onset_within_15m", "squall_onset_within_30m",
               "squall_onset_within_45m", "squall_onset_within_60m"]]
    lib = AnalogLibrary.fit(d)
    q = lib.query(d.iloc[[1]], top_k=5)
    assert q.iloc[0]["analog_count"] == 1