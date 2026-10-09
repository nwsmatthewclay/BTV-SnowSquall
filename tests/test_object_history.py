import json
from pathlib import Path

from scripts.append_live_object_history import append_history


def _geojson(path):
    payload = {
        "type": "FeatureCollection",
        "metadata": {"source_file": "KCXX_TEST_V06"},
        "features": [{
            "type": "Feature",
            "geometry": None,
            "properties": {
                "track_id": "7",
                "timestamp": "2026-01-01T00:00:00Z",
                "radar_site": "KCXX",
                "max_reflectivity_dbz": 42.0,
                "research_probability_now": 0.63,
                "probability_now": 0.63,
                "research_probabilities": {"now": 0.63, "15": 0.66, "30": 0.58},
                "radar_component_score": 72.0,
                "environment_component_score": 48.0,
                "environment_status": "complete",
                "environment": {
                    "source": "RAP",
                    "source_valid_time_utc": "2026-01-01T00:00:00+00:00",
                    "age_minutes": 0.0,
                    "fields": {"cape_jkg": 125.0, "shear_0_6km_ms": 12.0},
                },
            },
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_append_history_and_deduplicate(tmp_path: Path):
    geo = tmp_path / "objects.geojson"
    jsonl = tmp_path / "history.jsonl"
    csv = tmp_path / "history.csv"
    _geojson(geo)

    assert append_history(geo, jsonl, csv) == 1
    assert append_history(geo, jsonl, csv) == 0

    records = [json.loads(x) for x in jsonl.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["cape_jkg"] == 125.0
    assert records[0]["shear_0_6km_ms"] == 12.0
    assert records[0]["label_status"] == "unlabeled"
    assert records[0]["research_probability_now"] == 0.63
    assert records[0]["probability_now"] == 0.63
    assert json.loads(records[0]["research_probabilities"]) == {"now": 0.63, "15": 0.66, "30": 0.58}
    assert records[0]["radar_component_score"] == 72.0
    assert records[0]["environment_component_score"] == 48.0
