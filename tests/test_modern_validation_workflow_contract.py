from pathlib import Path


def test_modern_validation_workflow_uses_authoritative_manifest_path():
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github" / "workflows" / "modern-independent-validation.yml"
    ).read_text(encoding="utf-8")

    assert "data/manifests/modern_independent_validation_cases.csv" in workflow
    assert "data/derived/modern_independent_validation_cases.csv" not in workflow
    assert "--modern data/manifests/modern_independent_validation_cases.csv" in workflow
    assert "training_eligible" in workflow
    assert "not_scored" in workflow
