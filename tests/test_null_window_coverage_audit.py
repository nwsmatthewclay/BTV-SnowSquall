import pandas as pd
import pytest

from scripts.audit_null_window_coverage import audit


def test_null_window_coverage_requires_minimum_population(tmp_path):
    manifest = tmp_path / "manifest.csv"
    objects = tmp_path / "objects.csv"

    pd.DataFrame({"null_id": ["NULL0001", "NULL0002", "NULL0003"]}).to_csv(manifest, index=False)
    pd.DataFrame(
        {
            "null_id": ["NULL0001", "NULL0001", "NULL0002"],
            "radar_site": ["KCXX", "KCXX", "KTYX"],
            "scan_time_utc": [
                "2002-01-01T00:00:00Z",
                "2002-01-01T00:05:00Z",
                "2002-01-02T00:00:00Z",
            ],
        }
    ).to_csv(objects, index=False)

    with pytest.raises(ValueError):
        audit(manifest, objects, min_fraction=1.0)


def test_null_window_coverage_reports_empty_windows(tmp_path):
    manifest = tmp_path / "manifest.csv"
    objects = tmp_path / "objects.csv"

    pd.DataFrame({"null_id": ["NULL0001", "NULL0002"]}).to_csv(manifest, index=False)
    pd.DataFrame(
        {
            "null_id": ["NULL0001"],
            "radar_site": ["KCXX"],
            "scan_time_utc": ["2002-01-01T00:00:00Z"],
        }
    ).to_csv(objects, index=False)

    summary = audit(manifest, objects, min_fraction=0.5)
    assert summary["populated_null_windows"] == 1
    assert summary["empty_null_ids"] == ["NULL0002"]
    assert summary["population_fraction"] == 0.5
