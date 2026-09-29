from datetime import datetime, timezone
import json

from scripts import historical_operational_replay as replay


def test_replay_uses_case_local_history(tmp_path, monkeypatch):
    input_dir=tmp_path/"input"
    output_dir=tmp_path/"case"
    input_dir.mkdir()
    source=input_dir/"KTYX20260101_120000_V06"
    source.write_bytes(b"stub")
    state_path=output_dir/"state.json"
    calls=[]

    def fake_process(source_path, state, output, history_jsonl_path=None, history_csv_path=None, model_dir=None):
        calls.append({
            "history_jsonl": str(history_jsonl_path),
            "history_csv": str(history_csv_path),
            "model_dir": str(model_dir) if model_dir else None,
        })
        payload={
            "metadata":{
                "scan_time_utc":"2026-01-01T12:00:00Z",
                "object_count":1,
            }
        }
        output.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(replay, "process_volume", fake_process)
    manifest=replay.replay_case(
        input_dir,
        output_dir,
        state_path,
        "CASE1",
        model_dir=tmp_path/"model",
    )

    assert calls[0]["history_jsonl"].endswith("case/replay_object_history.jsonl")
    assert calls[0]["history_csv"].endswith("case/replay_object_history.csv")
    assert calls[0]["model_dir"].endswith("model")
    assert manifest["probability_status"]=="research_candidate_scored"


def test_replay_manifest_is_unscored_without_model(tmp_path, monkeypatch):
    input_dir=tmp_path/"input"
    output_dir=tmp_path/"case"
    input_dir.mkdir()
    source=input_dir/"KTYX20260101_120000_V06"
    source.write_bytes(b"stub")

    def fake_process(source_path, state, output, history_jsonl_path=None, history_csv_path=None, model_dir=None):
        output.write_text(json.dumps({"metadata":{"scan_time_utc":"2026-01-01T12:00:00Z","object_count":0}}), encoding="utf-8")

    monkeypatch.setattr(replay, "process_volume", fake_process)
    manifest=replay.replay_case(input_dir, output_dir, output_dir/"state.json", "CASE1")

    assert manifest["probability_status"]=="not_scored"
    assert manifest["model_directory"] is None
