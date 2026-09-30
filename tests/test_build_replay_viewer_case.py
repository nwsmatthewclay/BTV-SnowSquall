import json

from scripts.build_replay_viewer_case import build


def test_build_replay_viewer_case_injects_existing_probability_contract(tmp_path):
    base = tmp_path / "15m"
    base.mkdir()
    geo = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": None,
            "properties": {
                "timestamp": "2026-01-01T12:10:00Z",
                "track_id": "7",
                "radar_site": "KCXX",
            },
        }],
        "metadata": {},
    }
    (base / "0001.geojson").write_text(json.dumps(geo), encoding="utf-8")

    timeline = tmp_path / "score_timeline.json"
    timeline.write_text(json.dumps({
        "records": [{
            "timestamp": "2026-01-01T12:10:00Z",
            "track_id": "7",
            "cumulative_probabilities": {
                "15": 0.25,
                "30": 0.40,
                "45": 0.55,
                "60": 0.70,
            },
            "raw_cumulative_probabilities": {
                "15": 0.25,
                "30": 0.30,
                "45": 0.55,
                "60": 0.70,
            },
            "interval_probabilities": {
                "15": 0.25,
                "30": 0.15,
                "45": 0.15,
                "60": 0.15,
            },
            "probability_projection": "isotonic_non_decreasing_horizon",
        }]
    }), encoding="utf-8")

    out = tmp_path / "viewer_case.geojson"
    metadata = build(base, timeline, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    props = payload["features"][0]["properties"]
    assert metadata["probability_status"] == "research_replay"
    assert props["research_probabilities"]["15min"] == 0.25
    assert props["research_probabilities"]["60min"] == 0.70
    assert props["research_interval_probabilities"]["30min"] == 0.15
    assert props["probability_mode"] == "research_replay"
    assert props["research_only"] is True
