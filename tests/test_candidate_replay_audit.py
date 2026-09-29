import json

import pytest

from scripts.audit_candidate_replay import audit_horizon


def _write_replay(root, horizon, probabilities, wrong=None):
    d = root / f"{horizon}m"
    d.mkdir(parents=True)
    (d / "replay_manifest.json").write_text(json.dumps({
        "scan_count": 1,
        "object_scan_count": 1,
        "failed_scan_count": 0,
        "probability_status": "research_candidate_scored",
    }), encoding="utf-8")
    props = {f"probability_{h}min": None for h in (15,30,45,60)}
    props[f"probability_{horizon}min"] = probabilities
    if wrong:
        props[wrong[0]] = wrong[1]
    (d / "0001_test.geojson").write_text(json.dumps({
        "metadata": {
            "probability_status": "scored",
            "model_horizon_minutes": horizon,
            "future_information_policy": "one_scan_at_a_time",
        },
        "features": [{"type":"Feature","geometry":None,"properties":props}],
    }), encoding="utf-8")


def test_audit_accepts_correct_horizon(tmp_path):
    _write_replay(tmp_path, 30, 0.42)
    result = audit_horizon(tmp_path, 30)
    assert result["scored_object_count"] == 1


def test_audit_rejects_probability_in_wrong_horizon(tmp_path):
    _write_replay(tmp_path, 30, None, wrong=("probability_15min", 0.5))
    with pytest.raises(ValueError, match="leaked into probability_15min"):
        audit_horizon(tmp_path, 30)


def test_audit_rejects_failed_scan(tmp_path):
    d = tmp_path / "45m"
    d.mkdir()
    (d / "replay_manifest.json").write_text(json.dumps({"scan_count":1,"object_scan_count":1,"failed_scan_count":1}), encoding="utf-8")
    with pytest.raises(ValueError, match="failed scans"):
        audit_horizon(tmp_path, 45)
