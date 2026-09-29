import gzip
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_radar_window_coverage import audit


def test_radar_window_coverage_counts_matching_volumes(tmp_path):
    manifest = tmp_path / "manifest.csv"
    raw = tmp_path / "raw" / "KCXX" / "20020101"
    raw.mkdir(parents=True)
    pd.DataFrame(
        {
            "null_id": ["NULL0001", "NULL0002"],
            "radar_site": ["KCXX", "KCXX"],
            "window_start_utc": ["2002-01-01T00:00:00Z", "2002-01-01T01:00:00Z"],
            "window_end_utc": ["2002-01-01T00:30:00Z", "2002-01-01T01:30:00Z"],
        }
    ).to_csv(manifest, index=False)

    (raw / "KCXX20020101_000000_V06").write_bytes(b"test")

    summary = audit(manifest, tmp_path / "raw", min_fraction=0.5)
    assert summary["rows_with_level2"] == 1
    assert summary["rows_without_level2"] == 1
    assert summary["no_level2_identifiers"] == ["NULL0002"]


def test_radar_window_coverage_fails_when_required(tmp_path):
    manifest = tmp_path / "manifest.csv"
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame(
        {
            "null_id": ["NULL0001"],
            "radar_site": ["KCXX"],
            "window_start_utc": ["2002-01-01T00:00:00Z"],
            "window_end_utc": ["2002-01-01T00:30:00Z"],
        }
    ).to_csv(manifest, index=False)

    with pytest.raises(ValueError):
        audit(manifest, raw, min_fraction=1.0)

def test_radar_window_coverage_can_gate_on_primary_priority(tmp_path):
    manifest = tmp_path / "manifest.csv"
    raw = tmp_path / "raw" / "KCXX" / "20020101"
    raw.mkdir(parents=True)
    pd.DataFrame(
        {
            "case_id": ["CASE1", "CASE1"],
            "radar_site": ["KCXX", "KTYX"],
            "acquisition_priority": ["primary", "supplemental"],
            "window_start_utc": ["2002-01-01T00:00:00Z"] * 2,
            "window_end_utc": ["2002-01-01T00:30:00Z"] * 2,
        }
    ).to_csv(manifest, index=False)
    (raw / "KCXX20020101_000000_V06").write_bytes(b"test")

    summary = audit(
        manifest,
        tmp_path / "raw",
        min_fraction=1.0,
        required_priority="primary",
    )
    assert summary["coverage_scope"] == "primary"
    assert summary["evaluated_manifest_rows"] == 1
    assert summary["evaluated_coverage_fraction"] == 1.0
    assert summary["passed"] is True

