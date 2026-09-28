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
