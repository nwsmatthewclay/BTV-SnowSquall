import pandas as pd

from scripts.audit_radar_environment_contract import audit, ENVIRONMENT_REQUIRED_FIELDS


def _row(population, source_id):
    row = {
        "population": population,
        "case_id": source_id if population == "verified_case_context" else None,
        "null_id": source_id if population == "winter_null_candidate" else None,
        "base_reflectivity_mean_dbz": 20.0,
        "base_reflectivity_max_dbz": 35.0,
        "base_reflectivity_p90_dbz": 25.0,
        "base_reflectivity_valid_fraction": 0.8,
        "base_velocity_mean_kt": 2.0,
        "base_velocity_std_kt": 10.0,
        "base_velocity_p90_abs_kt": 15.0,
        "base_velocity_valid_fraction": 0.7,
        "velocity_mean_kt": 1.0,
        "velocity_std_kt": 8.0,
        "velocity_p90_abs_kt": 12.0,
    }
    row.update({name: 1.0 for name in ENVIRONMENT_REQUIRED_FIELDS})
    return row


def test_contract_passes_when_both_populations_have_required_data(tmp_path):
    frame = pd.DataFrame([
        _row("verified_case_context", "CASE1"),
        _row("winter_null_candidate", "NULL1"),
    ])
    source = tmp_path / "features.csv"
    output = tmp_path / "audit.json"
    frame.to_csv(source, index=False)

    report = audit(source, output)

    assert report["status"] == "pass"
    assert report["row_failures"] == 0
    assert report["population_summary"]["verified_case_context"]["contract_complete"] == 1.0
    assert report["population_summary"]["winter_null_candidate"]["contract_complete"] == 1.0


def test_contract_fails_when_one_training_row_lacks_base_velocity(tmp_path):
    good = _row("verified_case_context", "CASE1")
    bad = _row("winter_null_candidate", "NULL1")
    bad["base_velocity_mean_kt"] = None
    bad["base_velocity_std_kt"] = None
    bad["base_velocity_p90_abs_kt"] = None
    bad["base_velocity_valid_fraction"] = None

    source = tmp_path / "features.csv"
    frame = pd.DataFrame([good, bad])
    frame.to_csv(source, index=False)

    report = audit(source)

    assert report["status"] == "fail"
    assert report["row_failures"] == 1
    assert "base_velocity" in next(iter(report["failure_reason_counts"]))


def test_contract_fails_when_environment_package_is_incomplete(tmp_path):
    frame = pd.DataFrame([
        _row("verified_case_context", "CASE1"),
        _row("winter_null_candidate", "NULL1"),
    ])
    frame.loc[1, "cape_jkg"] = None

    source = tmp_path / "features.csv"
    frame.to_csv(source, index=False)

    report = audit(source)

    assert report["status"] == "fail"
    assert report["row_failures"] == 1
    assert "environment" in next(iter(report["failure_reason_counts"]))
