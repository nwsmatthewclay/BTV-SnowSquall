import json

from scripts.shadow_live_model_scorer import score_site


class FakeRuntime:
    def __init__(self, horizon):
        self.model = object()
        self.metadata = {
            "model_version": f"test-{horizon}",
            "operational_release_status": "candidate_only",
            "target": f"squall_onset_within_{horizon}m",
        }
        self.feature_columns = ["max_reflectivity_dbz"]

    def score_candidate(self, frame):
        horizon=int(self.metadata["target"].split("_")[-1][:-1])
        return [0.1 * horizon]


def test_shadow_scoring_keeps_candidate_non_operational(tmp_path, monkeypatch):
    live = tmp_path / "live"
    models = tmp_path / "models"
    live.mkdir()
    models.mkdir()
    (live / "KCXX_objects.geojson").write_text(json.dumps({
        "metadata": {"scan_time_utc": "2026-01-01T12:05:00Z"},
        "features": [{"type":"Feature","geometry":None,"properties":{"track_id":"7","timestamp":"2026-01-01T12:05:00Z","max_reflectivity_dbz":30.0}}]
    }), encoding="utf-8")
    (live / "KCXX_history.json").write_text(json.dumps([
        {"track_id":"7","timestamp":"2026-01-01T12:00:00Z","max_reflectivity_dbz":25.0},
        {"track_id":"7","timestamp":"2026-01-01T12:05:00Z","max_reflectivity_dbz":30.0}
    ]), encoding="utf-8")
    for site in ("KTYX",):
        (live / f"{site}_objects.geojson").write_text(json.dumps({"features":[],"metadata":{}}), encoding="utf-8")
        (live / f"{site}_history.json").write_text("[]", encoding="utf-8")

    class Stub:
        def __call__(self, directory):
            horizon=int(directory.name.replace("baseline_expansion_", "").replace("m", ""))
            return FakeRuntime(horizon)

    monkeypatch.setattr("scripts.shadow_live_model_scorer.ModelRuntime.load", Stub())
    payload, rows = score_site("KCXX", live, models)
    assert payload["mode"] == "live_shadow_research"
    assert payload["operational_release_status"] == "candidate_only_not_operational"
    assert rows[0]["research_probabilities"]
    assert sorted(rows[0]["research_probabilities"]) == ["15", "30", "45", "60"]
