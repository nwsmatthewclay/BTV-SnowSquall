import pandas as pd

from scripts.merge_expansion_feature_batches import merge


def test_merge_drops_legacy_positive_rows(tmp_path):
    prior = pd.DataFrame({
        "population": ["verified_case_context", "winter_null_candidate"],
        "supervision_class": [None, "null_candidate"],
        "row_identity_key": ["legacy-positive", "null-row"],
        "scan_time_utc": ["2020-01-01T00:00:00Z", "2020-01-01T00:05:00Z"],
        "max_reflectivity_dbz": [40.0, 20.0],
    })
    current = pd.DataFrame({
        "population": ["verified_case_context"],
        "supervision_class": ["supervised_positive"],
        "row_identity_key": ["new-positive"],
        "scan_time_utc": ["2026-01-01T00:00:00Z"],
        "max_reflectivity_dbz": [45.0],
    })
    pp, cp, op = tmp_path / "prior.csv", tmp_path / "current.csv", tmp_path / "out.csv"
    prior.to_csv(pp, index=False)
    current.to_csv(cp, index=False)

    merge(cp, pp, op)
    out = pd.read_csv(op)
    assert "legacy-positive" not in set(out["row_identity_key"])
    assert set(out["row_identity_key"]) == {"null-row", "new-positive"}
