from pathlib import Path


def test_pilot_report_includes_operational_qc_inputs():
    root = Path(__file__).resolve().parents[1]
    report = (root / "scripts/build_pilot_report.py").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "object-dataset-pilot.yml").read_text(encoding="utf-8")

    assert "--positive-environment-audit" in report
    assert "--null-environment-audit" in report
    assert "environment_attachment_section" in report
    assert "--positive-environment-audit data/derived/positive_environment_audit.json" in workflow
    assert "--null-environment-audit data/derived/null_environment_audit.json" in workflow
    assert "--plsr-status" in report
    assert "--plsr-status data/derived/swdi_plsr_status.json" in workflow
    assert "SWDI preliminary Local Storm Reports" in report
