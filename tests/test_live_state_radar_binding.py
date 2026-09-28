import json
from pathlib import Path
import pytest
from scripts.process_live_volume import process_volume

def test_live_processor_rejects_state_from_different_radar(tmp_path,monkeypatch):
    state=tmp_path/'state.json'; output=tmp_path/'out.json'
    state.write_text(json.dumps({'radar_site':'KTYX','tracker':{}}),encoding='utf-8')
    class FakeRadar: pass
    radar=FakeRadar()
    monkeypatch.setattr('scripts.process_live_volume.read_level2',lambda p:radar)
    monkeypatch.setattr('scripts.process_live_volume.volume_metadata',lambda r,p:{'radar_id':'KCXX','scan_time_utc':'2026-01-01T12:00:00Z'})
    with pytest.raises(RuntimeError,match='belongs to KTYX'):
        process_volume(Path('KCXX_test'),state,output)