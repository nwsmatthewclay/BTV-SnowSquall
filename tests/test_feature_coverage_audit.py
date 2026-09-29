from pathlib import Path

import pandas as pd

from scripts.audit_feature_coverage import audit


def test_feature_coverage_reports_partial_and_unexpected_gaps(tmp_path):
    frame = pd.DataFrame({
        "scan_time_utc": ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"],
        "object_id": ["a", "b"],
        "radar_site": ["KCXX", "KCXX"],
        "foo": [1.0, None],
        "bar": [None, None],
    })
    schema = pd.DataFrame({
        "field": ["foo", "bar"],
        "group": ["radar", "radar"],
        "availability_policy": ["required", "required"],
    })
    data_path = tmp_path / "features.csv"
    schema_path = tmp_path / "schema.csv"
    frame.to_csv(data_path, index=False)
    schema.to_csv(schema_path, index=False)

    result = audit(data_path, schema_path)

    assert result["zero_coverage_unexpected"] == ["bar"]
    assert result["partial_coverage_fields"] == [{
        "field": "foo",
        "coverage_pct": 50.0,
        "availability_policy": "required",
    }]
