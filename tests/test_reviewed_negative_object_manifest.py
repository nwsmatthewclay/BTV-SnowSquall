import pandas as pd
import pytest

from scripts.build_reviewed_negative_object_manifest import build


def test_expands_reviewed_nulls_to_exact_object_timesteps():
    features = pd.DataFrame({
        "population": [
            "winter_null_candidate",
            "winter_null_candidate",
            "winter_null_candidate",
        ],
        "null_id": ["N1", "N1", "N2"],
        "radar_site": ["KCXX", "KCXX", "KTYX"],
        "object_id": ["O1", "O2", "O3"],
        "scan_time_utc": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-02T00:00:00Z",
        ],
        "row_identity_key": ["r1", "r2", "r3"],
        "case_id": ["", "", ""],
    })
    promoted = pd.DataFrame({
        "null_id": ["N1"],
        "negative_truth_status": ["reviewed_negative"],
        "hard_negative_score": [5],
        "reviewer": ["forecaster"],
        "reviewed_at_utc": ["2026-10-05T17:00:00Z"],
    })

    rows, summary = build(features, promoted)

    assert list(rows["row_identity_key"]) == ["r1", "r2"]
    assert len(rows) == 2
    assert summary["reviewed_negative_windows"] == 1
    assert summary["reviewed_negative_object_rows"] == 2
    assert summary["reviewed_negative_object_rows_by_radar"]["KCXX"] == 2


def test_rejects_promoted_window_without_feature_rows():
    features = pd.DataFrame({
        "population": ["winter_null_candidate"],
        "null_id": ["N2"],
        "scan_time_utc": ["2026-01-02T00:00:00Z"],
    })
    promoted = pd.DataFrame({
        "null_id": ["N1"],
        "negative_truth_status": ["reviewed_negative"],
    })

    with pytest.raises(ValueError, match="no matching winter-null feature rows"):
        build(features, promoted)


def test_rejects_case_contamination():
    features = pd.DataFrame({
        "population": ["winter_null_candidate"],
        "null_id": ["N1"],
        "scan_time_utc": ["2026-01-01T00:00:00Z"],
        "case_id": ["CASE1"],
    })
    promoted = pd.DataFrame({
        "null_id": ["N1"],
        "negative_truth_status": ["reviewed_negative"],
    })

    with pytest.raises(ValueError, match="case_id"):
        build(features, promoted)
