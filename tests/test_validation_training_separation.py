import pandas as pd
import pytest


def test_validation_training_separation_rejects_overlap(tmp_path):
    from scripts.audit_validation_training_separation import audit

    modern = tmp_path / "modern.csv"
    development = tmp_path / "development.csv"

    pd.DataFrame([{"case_id": "MODERN1"}]).to_csv(modern, index=False)
    pd.DataFrame([{"case_id": "MODERN1"}]).to_csv(development, index=False)

    with pytest.raises(ValueError, match="overlap"):
        audit(modern, [development])


def test_validation_training_separation_accepts_disjoint_cases(tmp_path):
    from scripts.audit_validation_training_separation import audit

    modern = tmp_path / "modern.csv"
    development = tmp_path / "development.csv"

    pd.DataFrame([{"case_id": "MODERN1"}]).to_csv(modern, index=False)
    pd.DataFrame([{"case_id": "TRAIN1"}]).to_csv(development, index=False)

    result = audit(modern, [development])
    assert result["training_separation_ok"] is True
