import json
from pathlib import Path

import pandas as pd


from scripts.audit_feature_coverage import audit


def test_feature_coverage_reports_missing_schema_fields(tmp_path):
    frame = pd.DataFrame(
        {
            "scan_time_utc": ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"],
            "object_id": [1, 1],
            "radar_site": ["KCXX", "KCXX"],
            "max_reflectivity_dbz": [35.0, 40.0],
            "zdr_mean_db": [0.5, None],
        }
    )
    input_csv = tmp_path / "objects.csv"
    frame.to_csv(input_csv, index=False)

    schema_csv = tmp_path / "schema.csv"
    pd.DataFrame(
        {
            "field": [
                "scan_time_utc",
                "object_id",
                "radar_site",
                "max_reflectivity_dbz",
                "zdr_mean_db",
                "kdp_mean_degkm",
            ],
            "group": [
                "identity",
                "identity",
                "identity",
                "reflectivity",
                "dualpol",
                "dualpol",
            ],
        }
    ).to_csv(schema_csv, index=False)

    result = audit(input_csv, schema_csv)

    detail = {row["field"]: row for row in result["field_coverage"]}
    assert detail["max_reflectivity_dbz"]["coverage_pct"] == 100.0
    assert detail["zdr_mean_db"]["coverage_pct"] == 50.0
    assert detail["kdp_mean_degkm"]["coverage_pct"] == 0.0
    assert "kdp_mean_degkm" in result["zero_coverage_fields"]

    
def test_coverage_distinguishes_defined_and_populated_fields(tmp_path):
    frame = pd.DataFrame(
        {
            "scan_time_utc": ["2006-02-07T12:00:00Z", "2006-02-07T12:05:00Z"],
            "object_id": [1, 2],
            "radar_site": ["KCXX", "KCXX"],
            "zdr_mean_db": [1.0, None],
        }
    )
    schema = pd.DataFrame(
        {
            "field": ["scan_time", "zdr_mean_db", "kdp_mean_degkm"],
            "group": ["identity", "dualpol", "dualpol"],
        }
    )
    input_csv = tmp_path / "features.csv"
    schema_csv = tmp_path / "schema.csv"
    frame.to_csv(input_csv, index=False)
    schema.to_csv(schema_csv, index=False)

    result = audit(input_csv, schema_csv)
    dualpol = next(row for row in result["group_coverage"] if row["group"] == "dualpol")
    assert dualpol["fields_present"] == 1
    assert dualpol["fields_with_values"] == 1
    assert dualpol["mean_field_coverage_pct"] == 25.0
