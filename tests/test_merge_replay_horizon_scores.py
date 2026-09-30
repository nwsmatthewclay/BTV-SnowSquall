import json

from scripts.merge_replay_horizon_scores import merge


def _write_geo(root, horizon, timestamp, track_id, probability):
    directory = root / f"{horizon}m"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": None,
            "properties": {
                "track_id": track_id,
                "timestamp": timestamp,
                "radar_site": "KCXX",
                "max_reflectivity_dbz": 35.0,
                f"probability_{horizon}min": probability,
            },
        }],
        "metadata": {
            "scan_time_utc": timestamp,
            "object_count": 1,
            "probability_status": "scored",
            "model_horizon_minutes": horizon,
            "future_information_policy": "one_scan_at_a_time",
        },
    }
    (directory / f"0001_{horizon}.geojson").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_merge_replay_horizons_projects_cumulative_probabilities(tmp_path):
    ts = "2026-01-01T12:10:00Z"
    _write_geo(tmp_path, 15, ts, "7", 0.60)
    _write_geo(tmp_path, 30, ts, "7", 0.50)
    _write_geo(tmp_path, 45, ts, "7", 0.80)
    _write_geo(tmp_path, 60, ts, "7", 0.90)

    report = merge(tmp_path)

    assert report["status"] == "pass"
    assert report["record_count"] == 1
    record = report["records"][0]
    values = list(record["cumulative_probabilities"].values())
    assert values == sorted(values)
    assert record["cumulative_probabilities"]["15"] == 0.55
    assert record["cumulative_probabilities"]["30"] == 0.55
    assert record["cumulative_probabilities"]["45"] == 0.80
    assert record["cumulative_probabilities"]["60"] == 0.90


def test_merge_replay_horizons_detects_alignment_gap(tmp_path):
    ts = "2026-01-01T12:10:00Z"
    _write_geo(tmp_path, 15, ts, "7", 0.30)
    _write_geo(tmp_path, 30, ts, "7", 0.40)
    _write_geo(tmp_path, 45, ts, "7", 0.50)

    report = merge(tmp_path)

    assert report["status"] == "fail"
    assert report["alignment_gap_count"] == 1
