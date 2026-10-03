import json

from scripts.shadow_live_model_scorer import score_site


def rich_props(track_id="7", timestamp="2026-01-01T12:05:00Z", max_z=30.0):
    return {
        "track_id": track_id,
        "timestamp": timestamp,
        "max_reflectivity_dbz": max_z,
        "mean_reflectivity_dbz": 24.0,
        "area_km2": 12.0,
        "length_km": 5.0,
        "width_km": 2.0,
        "core_pixel_count": 4,
        "bbox_aspect_ratio": 2.5,
        "reflectivity_gradient_p90_dbkm": 7.0,
        "gradient_fraction_above_5dbkm": 0.2,
        "background_reflectivity_dbz": 18.0,
        "reflectivity_contrast_db": 6.0,
    }


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
        horizon = int(self.metadata["target"].split("_")[-1][:-1])
        return [0.1 * horizon]


def write_empty_site(live, site):
    (live / f"{site}_objects.geojson").write_text(
        json.dumps({"features": [], "metadata": {}}), encoding="utf-8"
    )
    (live / f"{site}_history.json").write_text("[]", encoding="utf-8")


def make_model_dirs(models, prefix="candidate_ensemble_expansion_"):
    for horizon in (15, 30, 45, 60):
        bundle = models / f"{prefix}{horizon}m"
        bundle.mkdir()
        (bundle / "metrics.json").write_text("{}", encoding="utf-8")


def test_shadow_scoring_keeps_candidate_non_operational(tmp_path, monkeypatch):
    live = tmp_path / "live"
    models = tmp_path / "models"
    live.mkdir()
    models.mkdir()
    make_model_dirs(models)

    current = rich_props()
    previous = rich_props(
        timestamp="2026-01-01T12:00:00Z",
        max_z=23.0,
    )

    (live / "KCXX_objects.geojson").write_text(json.dumps({
        "metadata": {"scan_time_utc": current["timestamp"]},
        "features": [{"type": "Feature", "geometry": None, "properties": current}],
    }), encoding="utf-8")
    (live / "KCXX_history.json").write_text(
        json.dumps([previous, current]), encoding="utf-8"
    )
    write_empty_site(live, "KTYX")

    def load_stub(directory):
        horizon = int(directory.name.split("_")[-1].replace("m", ""))
        return FakeRuntime(horizon)

    monkeypatch.setattr("scripts.shadow_live_model_scorer.ModelRuntime.load", load_stub)
    payload, rows = score_site("KCXX", live, models)

    assert payload["mode"] == "live_shadow_research"
    assert payload["operational_release_status"] == "candidate_only_not_operational"
    assert rows[0]["research_probabilities"]
    assert sorted(rows[0]["research_probabilities"]) == ["15", "30", "45", "60"]


def test_shadow_score_is_withheld_when_feature_coverage_is_low(tmp_path, monkeypatch):
    live = tmp_path / "live"
    models = tmp_path / "models"
    live.mkdir()
    models.mkdir()
    make_model_dirs(models)

    current = {
        "track_id": "1",
        "timestamp": "2026-01-01T12:05:00Z",
        "max_reflectivity_dbz": 30.0,
    }
    (live / "KCXX_objects.geojson").write_text(json.dumps({
        "metadata": {},
        "features": [{"type": "Feature", "geometry": None, "properties": current}],
    }), encoding="utf-8")
    (live / "KCXX_history.json").write_text("[]", encoding="utf-8")
    write_empty_site(live, "KTYX")

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
    make_model_dirs(models)

    current = rich_props(timestamp="2026-01-01T12:05:00Z", max_z=30.0)
    previous = rich_props(timestamp="2026-01-01T12:00:00Z", max_z=25.0)
    future = rich_props(timestamp="2026-01-01T12:10:00Z", max_z=99.0)

    (live / "KCXX_objects.geojson").write_text(json.dumps({
        "metadata": {"scan_time_utc": current["timestamp"]},
        "features": [{"type": "Feature", "geometry": None, "properties": current}],
    }), encoding="utf-8")
    (live / "KCXX_history.json").write_text(
        json.dumps([previous, current, future]), encoding="utf-8"
    )
    write_empty_site(live, "KTYX")

    captured = {}

    class StubRuntime:
        def __init__(self):
            self.model = object()
            self.metadata = {
                "model_version": "test",
                "operational_release_status": "candidate_only",
            }
            self.feature_columns = ["max_reflectivity_dbz"]

        def score_candidate(self, frame):
            captured.setdefault("rows", []).append(
                frame[["timestamp", "max_reflectivity_dbz"]].iloc[0].to_dict()
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
