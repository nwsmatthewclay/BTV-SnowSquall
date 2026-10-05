from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_research_operational_candidate import evaluate


def _bundle(root: Path, horizon: int, positive_groups: int = 4, beats_climatology: bool = True):
    bundle = root / f"candidate_ensemble_refresh_{horizon}m"
    bundle.mkdir(parents=True)
    candidate_brier = 0.08 if beats_climatology else 0.20
    climate_brier = 0.12
    (bundle / "metrics.json").write_text(
        json.dumps({
            "calibration_status": "fit_on_oof_research_data",
            "positive_case_group_count": positive_groups,
            "evaluation_status": "case_held_out_exploratory",
            "metrics": {
                "brier_score": candidate_brier,
                "climatology": {"brier_score": climate_brier},
            },
            "operational_release_status": "candidate_only",
        }),
        encoding="utf-8",
    )


def _write_gate(path: Path, ok_horizons: set[int]):
    payload = {
        str(h): {"status": "ok" if h in ok_horizons else "no_valid_event_folds"}
        for h in (15, 30, 45, 60)
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_limited_data_candidate_can_be_shadow_ready(tmp_path: Path):
    for h in (15, 30, 45, 60):
        _bundle(tmp_path, h, positive_groups=2)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    gate = tmp_path / "gate.json"
    _write_gate(gate, {15, 30})
    result = evaluate(tmp_path, audit, gate)
    assert result["status"] == "limited_data_candidate"
    assert result["live_shadow_enablement"] is True
    assert result["probability_enablement"] is False


def test_research_operational_candidate_requires_minimum_support(tmp_path: Path):
    for h in (15, 30, 45, 60):
        _bundle(tmp_path, h, positive_groups=4)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    gate = tmp_path / "gate.json"
    _write_gate(gate, {15, 30, 45})
    result = evaluate(tmp_path, audit, gate)
    assert result["status"] == "research_operational_candidate"
    assert result["probability_enablement"] is False


def test_bootstrap_candidate_never_gets_strong_operational_status(tmp_path: Path):
    for h in (15, 30, 45, 60):
        _bundle(tmp_path, h, positive_groups=8, beats_climatology=True)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    gate = tmp_path / "gate.json"
    _write_gate(gate, {15, 30, 45, 60})
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps({"candidate_mode": "bootstrap_legacy_feature_contract"}),
        encoding="utf-8",
    )
    result = evaluate(tmp_path, audit, gate, summary)
    assert result["status"] == "limited_data_candidate"
    assert result["bootstrap_mode"] is True
    assert result["live_shadow_enablement"] is True
