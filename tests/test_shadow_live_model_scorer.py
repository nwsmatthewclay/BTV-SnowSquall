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
    for horizon in (15, 30, 45, 60):
        bundle = models / ('candidate_ensemble_expansion_' + str(horizon) + 'm')
        bundle.mkdir()
        (bundle / 'metrics.json').write_text('{}')
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
            name=directory.name
            prefix="candidate_ensemble_expansion_" if name.startswith("candidate_ensemble_expansion_") else "baseline_expansion_"
            horizon=int(name.replace(prefix, "").replace("m", ""))
            return FakeRuntime(horizon)

    monkeypatch.setattr("scripts.shadow_live_model_scorer.ModelRuntime.load", Stub())
    payload, rows = score_site("KCXX", live, models)
    assert payload["mode"] == "live_shadow_research"
    assert payload["operational_release_status"] == "candidate_only_not_operational"
    assert rows[0]["research_probabilities"]
    assert sorted(rows[0]["research_probabilities"]) == ["15", "30", "45", "60"]


def test_shadow_score_is_withheld_when_feature_coverage_is_low(tmp_path, monkeypatch):
    import json
    live = tmp_path / "live"
    models = tmp_path / "models"
    live.mkdir()
    models.mkdir()
    (live / "KCXX_objects.geojson").write_text(json.dumps({
        "metadata": {},
        "features": [{
            "type": "Feature",
            "geometry": None,
            "properties": {
                "track_id": "1",
                "timestamp": "2026-01-01T12:05:00Z",
                "max_reflectivity_dbz": 30.0,
            },
        }],
    }), encoding="utf-8")
    (live / "KCXX_history.json").write_text(json.dumps([]), encoding="utf-8")
    (live / "KTYX_objects.geojson").write_text(json.dumps({"features":[],"metadata":{}}), encoding="utf-8")
    (live / "KTYX_history.json").write_text("[]", encoding="utf-8")

    class StubRuntime:
        def __init__(self):
            self.model = object()
            self.metadata = {"operational_release_status": "candidate_only"}
            self.feature_columns = ["missing_a", "missing_b"]

        def score_candidate(self, frame):
            return [0.99]

    monkeypatch.setattr(
        "scripts.shadow_live_model_scorer.ModelRuntime.load",
        lambda directory: StubRuntime(),
    )
    payload, rows = score_site("KCXX", live, models)
    assert rows[0]["research_probabilities"] == {}
    assert "low_feature_coverage" in rows[0]["score_errors"]["15"]
    assert payload["scored_object_count"] == 0

def test_shadow_scoring_excludes_future_history(tmp_path, monkeypatch):
    live = tmp_path / "live"
    models = tmp_path / "models"
    live.mkdir()
    models.mkdir()
    for horizon in (15, 30, 45, 60):
        bundle = models / ("candidate_ensemble_expansion_" + str(horizon) + "m")
        bundle.mkdir()
        (bundle / "metrics.json").write_text("{}", encoding="utf-8")

    (live / "KCXX_objects.geojson").write_text(json.dumps({
        "metadata": {"scan_time_utc": "2026-01-01T12:05:00Z"},
        "features": [{
            "type": "Feature",
            "geometry": None,
            "properties": {
                "track_id": "7",
                "timestamp": "2026-01-01T12:05:00Z",
                "max_reflectivity_dbz": 30.0,
            },
        }],
    }), encoding="utf-8")
    (live / "KCXX_history.json").write_text(json.dumps([
        {"track_id":"7","timestamp":"2026-01-01T12:00:00Z","max_reflectivity_dbz":25.0},
        {"track_id":"7","timestamp":"2026-01-01T12:05:00Z","max_reflectivity_dbz":30.0},
        {"track_id":"7","timestamp":"2026-01-01T12:10:00Z","max_reflectivity_dbz":99.0},
    ]), encoding="utf-8")
    for site in ("KTYX",):
        (live / f"{site}_objects.geojson").write_text(
            json.dumps({"features":[],"metadata":{}}), encoding="utf-8"
        )
        (live / f"{site}_history.json").write_text("[]", encoding="utf-8")

    captured = {}

    class StubRuntime:
        def __init__(self):
            self.model = object()
            self.metadata = {"model_version":"test","operational_release_status":"candidate_only"}
            self.feature_columns = ["max_reflectivity_dbz"]

        def score_candidate(self, frame):
            captured.setdefault("rows", []).append(
                frame[["timestamp","max_reflectivity_dbz"]].iloc[0].to_dict()
            )
            return [float(frame["max_reflectivity_dbz"].iloc[0]) / 100.0]

    monkeypatch.setattr(
        "scripts.shadow_live_model_scorer.ModelRuntime.load",
        lambda directory: StubRuntime(),
    )
    payload, rows = score_site("KCXX", live, models)
    assert payload["scored_object_count"] == 1
    assert rows[0]["research_probabilities"]["15"] == 0.3
    assert all(row["max_reflectivity_dbz"] == 30.0 for row in captured["rows"])
