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
    def fake_process(source, state_path, output_path):
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
