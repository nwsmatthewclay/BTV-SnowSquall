from datetime import timezone
from pathlib import Path
from scripts.historical_operational_replay import ordered_inputs, scan_time

def test_scan_time_parses_common_level2_filename():
    value=scan_time(Path("KCXX20060224_140955_V06"))
    assert value.tzinfo==timezone.utc
    assert value.isoformat()=="2006-02-24T14:09:55+00:00"

def test_ordered_inputs_is_chronological(tmp_path):
    for name in ("KCXX20060224_141500_V06","KCXX20060224_140500_V06","KCXX20060224_143000_V06"):
        (tmp_path/name).write_bytes(b"placeholder")
    assert [p.name for p in ordered_inputs(tmp_path)]==[
        "KCXX20060224_140500_V06","KCXX20060224_141500_V06","KCXX20060224_143000_V06"
    ]


def test_replay_can_record_bad_scan_and_continue(tmp_path, monkeypatch):
    from scripts import historical_operational_replay as replay
    for name in ("KCXX20181121_160000_V06", "KCXX20181121_161000_V06"):
        (tmp_path / name).write_bytes(b"placeholder")
    calls=[]
    def fake_process(source, state_path, output_path, history_jsonl_path=None, history_csv_path=None, model_dir=None, research_replay=False):
        calls.append(source.name)
        if len(calls)==1:
            raise OSError("bad historical volume")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('{"metadata":{"scan_time_utc":"2018-11-21T16:10:00+00:00","object_count":2}}', encoding="utf-8")
        return True
    monkeypatch.setattr(replay, "process_volume", fake_process)
    result=replay.replay_case(tmp_path, tmp_path/"out", tmp_path/"state.json", "BTV20181121", continue_on_error=True)
    assert result["attempted_scan_count"]==2
    assert result["successful_scan_count"]==1
    assert result["failed_scan_count"]==1
    assert result["object_scan_count"]==2
    assert result["errors"][0]["error_type"]=="OSError"


def test_modern_surface_radar_distance_is_reasonable():
    from scripts.build_modern_surface_radar_diagnostic import distance_km
    assert 10 < distance_km(44.47, -73.15, 44.56, -73.15) < 11


def test_replay_respects_explicit_case_window(tmp_path, monkeypatch):
    from scripts import historical_operational_replay as replay
    for name in ("KCXX20191218_222000_V06", "KCXX20191218_224000_V06", "KCXX20191218_231000_V06"):
        (tmp_path / name).write_bytes(b"placeholder")

    calls=[]
    def fake_process(source, state_path, output_path, history_jsonl_path=None, history_csv_path=None, model_dir=None, research_replay=False):
        calls.append(source.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp={
            "KCXX20191218_224000_V06":"2019-12-18T22:40:00+00:00",
            "KCXX20191218_231000_V06":"2019-12-18T23:10:00+00:00",
        }[source.name]
        output_path.write_text(
            '{"metadata":{"scan_time_utc":"'+timestamp+'","object_count":1}}',
            encoding="utf-8",
        )
        return True

    monkeypatch.setattr(replay, "process_volume", fake_process)
    result=replay.replay_case(
        tmp_path,
        tmp_path/"out",
        tmp_path/"state.json",
        "CASE",
        window_start=replay.scan_time(tmp_path/"KCXX20191218_224000_V06"),
        window_end=replay.scan_time(tmp_path/"KCXX20191218_224000_V06"),
    )
    assert calls==["KCXX20191218_224000_V06"]
    assert result["attempted_scan_count"]==1
    assert result["successful_scan_count"]==1


def test_surface_radar_diagnostic_distinguishes_nonlocal_object():
    from scripts.build_modern_surface_radar_diagnostic import distance_km
    assert distance_km(44.20, -72.56, 43.82, -72.99) > 40


def test_candidate_runtime_is_blocked_outside_replay():
    from scripts.process_live_volume import score_with_runtime

    class FakeRuntime:
        model = object()
        enabled = False

        def score_candidate(self, frame):
            return [0.42]

        def score(self, frame):
            return [0.99]

    frame = __import__("pandas").DataFrame({"x": [1.0]})
    runtime = FakeRuntime()

    blocked, mode = score_with_runtime(frame, runtime, research_replay=False)
    assert blocked is None
    assert mode == "candidate_blocked"

    scored, mode = score_with_runtime(frame, runtime, research_replay=True)
    assert scored == [0.42]
    assert mode == "research_replay"


def test_replay_audit_requires_research_mode_for_scored_records(tmp_path):
    import json
    from scripts.audit_candidate_replay import audit_horizon

    horizon_dir = tmp_path / "15m"
    horizon_dir.mkdir()
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": None,
            "properties": {
                "track_id": "1",
                "probability_15min": 0.4,
            },
        }],
        "metadata": {
            "probability_status": "scored",
            "probability_mode": "released",
            "model_horizon_minutes": 15,
            "future_information_policy": "one_scan_at_a_time",
        },
    }
    (horizon_dir / "0001.geojson").write_text(json.dumps(payload), encoding="utf-8")
    (horizon_dir / "replay_manifest.json").write_text(
        json.dumps({
            "scan_count": 1,
            "failed_scan_count": 0,
            "object_scan_count": 1,
            "probability_status": "research_candidate_scored",
        }),
        encoding="utf-8",
    )

    import pytest
    with pytest.raises(ValueError, match="research_replay"):
        audit_horizon(tmp_path, 15)


def test_validate_scan_sequence_rejects_duplicate_timestamps(tmp_path):
    from scripts.historical_operational_replay import validate_scan_sequence
    paths = [
        tmp_path / "KCXX20200101_120000_V06",
        tmp_path / "KCXX20200101_120000_V06.duplicate",
    ]
    result = validate_scan_sequence(paths)
    assert result["duplicate_scan_timestamp_count"] == 1
    assert result["strictly_increasing_scan_times"] is False


def test_replay_rejects_output_timestamp_mismatch(tmp_path, monkeypatch):
    from scripts import historical_operational_replay as replay
    source = tmp_path / "KCXX20191218_224000_V06"
    source.write_bytes(b"placeholder")

    def fake_process(source, state_path, output_path, history_jsonl_path=None, history_csv_path=None, model_dir=None, research_replay=False):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            '{"metadata":{"scan_time_utc":"2019-12-18T22:45:00Z","object_count":1}}',
            encoding="utf-8",
        )
        return True

    monkeypatch.setattr(replay, "process_volume", fake_process)
    import pytest
    with pytest.raises(ValueError, match="timestamp mismatch"):
        replay.replay_case(
            tmp_path,
            tmp_path / "out",
            tmp_path / "state.json",
            "CASE",
        )


def test_resume_uses_only_completed_output_prefix(tmp_path, monkeypatch):
    from scripts import historical_operational_replay as replay
    names = [
        "KCXX20200101_120000_V06",
        "KCXX20200101_121000_V06",
        "KCXX20200101_122000_V06",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"placeholder")
    out = tmp_path / "out"
    out.mkdir()
    state = tmp_path / "state.json"

    def write_output(path, timestamp):
        path.write_text(
            json.dumps({"metadata":{"scan_time_utc":timestamp,"object_count":1}}),
            encoding="utf-8",
        )

    import json
    write_output(out / "0001_KCXX20200101_120000_V06.geojson", "2020-01-01T12:00:00Z")
    state.write_text(json.dumps({
        "last_source": names[0],
        "processed_sources": [names[0]],
    }), encoding="utf-8")

    calls = []
    def fake_process(source, state_path, output_path, history_jsonl_path=None, history_csv_path=None, model_dir=None, research_replay=False):
        calls.append(source.name)
        write_output(output_path, {
            "KCXX20200101_121000_V06":"2020-01-01T12:10:00Z",
            "KCXX20200101_122000_V06":"2020-01-01T12:20:00Z",
        }[source.name])
        return True

    monkeypatch.setattr(replay, "process_volume", fake_process)
    result = replay.replay_case(
        tmp_path, out, state, "CASE", resume=True
    )
    assert calls == names[1:]
    assert result["scan_count"] == 3


def test_resume_rejects_noncontiguous_outputs(tmp_path):
    from scripts import historical_operational_replay as replay
    names = [
        "KCXX20200101_120000_V06",
        "KCXX20200101_121000_V06",
        "KCXX20200101_122000_V06",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"placeholder")
    out = tmp_path / "out"
    out.mkdir()
    import json
    for index, name in ((1, names[0]), (3, names[2])):
        (out / f"{index:04d}_{name}.geojson").write_text(
            json.dumps({"metadata":{"scan_time_utc":"2020-01-01T12:00:00Z","object_count":1}}),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="contiguous prefix"):
        replay.replay_case(tmp_path, out, tmp_path/"state.json", "CASE", resume=True)
