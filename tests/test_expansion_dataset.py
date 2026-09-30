import json
import pandas as pd
import pytest

from scripts.audit_expansion_dataset import audit


def test_expansion_audit_passes_clean_table(tmp_path):
    features = pd.DataFrame({
        "population": ["verified_case_context", "winter_null_candidate"],
        "case_id": ["C1", None],
        "null_id": [None, "N1"],
        "object_id": [1, 2],
        "population_track_key": ["verified_case_context:C1:KCXX:1", "winter_null_candidate:N1:KCXX:2"],
        "scan_time_utc": ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"],
        "row_identity_key": ["a", "b"],
        "max_reflectivity_dbz": [35.0, 20.0],
        "squall_onset_within_15m": [1, 0],
        "squall_onset_within_30m": [1, 0],
        "squall_onset_within_45m": [1, 0],
        "squall_onset_within_60m": [1, 0],
    })
    schema = {
        "future_information_policy": "current_and_past_only",
        "predictor_columns": ["max_reflectivity_dbz"],
        "operational_predictor_columns": ["max_reflectivity_dbz"],
        "target_columns": [
            "squall_onset_within_15m", "squall_onset_within_30m",
            "squall_onset_within_45m", "squall_onset_within_60m",
        ],
    }
    fp, sp, cp = tmp_path / "features.csv", tmp_path / "schema.json", tmp_path / "cases.csv"
    features.to_csv(fp, index=False)
    sp.write_text(json.dumps(schema))
    pd.DataFrame({"case_id": ["C1"]}).to_csv(cp, index=False)

    report = audit(fp, sp, cp)
    assert report["status"] == "pass"
    assert report["positive_cases_outside_current_supervised_cohort_count"] == 0


def test_expansion_audit_catches_duplicate_identity(tmp_path):
    features = pd.DataFrame({
        "population": ["winter_null_candidate", "winter_null_candidate"],
        "case_id": [None, None],
        "null_id": ["N1", "N1"],
        "object_id": [2, 2],
        "population_track_key": ["winter_null_candidate:N1:KCXX:2"] * 2,
        "scan_time_utc": ["2026-01-01T00:00:00Z"] * 2,
        "row_identity_key": ["duplicate", "duplicate"],
        "max_reflectivity_dbz": [20.0, 21.0],
    })
    schema = {
        "future_information_policy": "current_and_past_only",
        "predictor_columns": ["max_reflectivity_dbz"],
        "operational_predictor_columns": ["max_reflectivity_dbz"],
        "target_columns": [],
    }
    fp, sp = tmp_path / "features.csv", tmp_path / "schema.json"
    features.to_csv(fp, index=False)
    sp.write_text(json.dumps(schema))
    report = audit(fp, sp)
    assert report["status"] == "fail"
    assert any("duplicate_row_identity_keys" in e for e in report["errors"])
