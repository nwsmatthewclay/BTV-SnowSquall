import pandas as pd

from scripts.audit_training_dataset import audit


def _frame():
    return pd.DataFrame([{
        "scan_time_utc": "2026-01-01T00:00:00Z",
        "object_id": "OBJ-1",
        "case_id": "CASE-1",
        "split_group": "CASE-1",
        "label_status": "prospective_positive",
        "squall_onset_within_15m": 1,
        "squall_onset_within_30m": 1,
        "squall_onset_within_45m": 1,
        "squall_onset_within_60m": 1,
    }, {
        "scan_time_utc": "2026-01-01T00:05:00Z",
        "object_id": "OBJ-2",
        "case_id": "CASE-2",
        "split_group": "CASE-2",
        "label_status": "case_associated_nonimpact",
        "squall_onset_within_15m": 0,
        "squall_onset_within_30m": 0,
        "squall_onset_within_45m": 0,
        "squall_onset_within_60m": 0,
    }])


def test_audit_reports_population_and_clean_horizon_contract(tmp_path):
    path = tmp_path / "training.csv"
    _frame().to_csv(path, index=False)
    result = audit(path)
    assert result["records"] == 2
    assert result["unique_cases"] == 2
    assert result["duplicate_object_scan_rows"] == 0
    assert result["issues"] == []


def test_audit_flags_nonmonotone_horizons_and_duplicate_identity(tmp_path):
    frame = _frame()
    frame.loc[0, "squall_onset_within_30m"] = 0
    frame.loc[1, "scan_time_utc"] = frame.loc[0, "scan_time_utc"]
    frame.loc[1, "object_id"] = frame.loc[0, "object_id"]
    path = tmp_path / "training.csv"
    frame.to_csv(path, index=False)
    result = audit(path)
    assert any(issue.startswith("nonmonotone_onset_horizons:15m_to_30m") for issue in result["issues"])
    assert any(issue.startswith("duplicate_object_scan_identity") for issue in result["issues"])


def test_audit_reports_known_label_coverage_by_horizon_and_case(tmp_path):
    frame = _frame()
    frame.loc[1, "squall_onset_within_30m"] = pd.NA
    frame.loc[1, "squall_onset_within_45m"] = pd.NA
    frame.loc[1, "squall_onset_within_60m"] = pd.NA
    path = tmp_path / "training.csv"
    frame.to_csv(path, index=False)

    result = audit(path)
    assert result["horizon_coverage"]["15"]["rows_known"] == 2
    assert result["horizon_coverage"]["30"]["rows_known"] == 1
    assert result["horizon_coverage"]["30"]["coverage_fraction"] == 0.5
    assert result["case_horizon_coverage"]["30"]["cases_with_known_targets"] == 1
    assert result["label_status_horizon_coverage"]["30"]["case_associated_nonimpact"]["unknown"] == 1
    assert result["rows_with_any_onset_target_known"] == 2


def test_audit_flags_case_split_group_leakage(tmp_path):
    frame = _frame()
    frame.loc[0, "split_group"] = "SPLIT-A"
    frame.loc[1, "split_group"] = "SPLIT-B"
    frame.loc[1, "case_id"] = "CASE-1"
    path = tmp_path / "training.csv"
    frame.to_csv(path, index=False)

    result = audit(path)
    assert result["case_split_integrity"]["cases_in_multiple_split_groups"] == 1
    assert any(issue.startswith("case_spans_multiple_split_groups") for issue in result["issues"])
