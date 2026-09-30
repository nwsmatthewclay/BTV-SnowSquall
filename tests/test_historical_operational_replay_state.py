
import json
from pathlib import Path
import scripts.historical_operational_replay as replay


def test_replay_resets_existing_state_by_default(tmp_path, monkeypatch):
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    (source_dir / "KCXX20060224_140500_V06").write_text("x")
    output_dir = tmp_path / "out"
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"stale": True}), encoding="utf-8")

    def fake_process(source, state_path, output, history_jsonl_path=None, history_csv_path=None, model_dir=None, research_replay=False):
        assert not state_path.exists()
        Path(output).write_text(json.dumps({
            "metadata": {"scan_time_utc": "2006-02-24T14:05:00+00:00", "object_count": 0},
            "features": [],
        }), encoding="utf-8")
        state_path.write_text(json.dumps({"fresh": True}), encoding="utf-8")

    monkeypatch.setattr(replay, "process_volume", fake_process)
    result = replay.replay_case(source_dir, output_dir, state, "CASE1")
    assert result["scan_count"] == 1
    assert json.loads(state.read_text())["fresh"] is True
