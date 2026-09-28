import json
import numpy as np
from pathlib import Path
from scripts.process_live_volume import process_volume

def test_live_product_marks_edge_objects(monkeypatch,tmp_path):
    class FakeRadar: pass
    fake=FakeRadar()
    monkeypatch.setattr('scripts.process_live_volume.read_level2',lambda p:fake)
    monkeypatch.setattr('scripts.process_live_volume.volume_metadata',lambda radar,path:{'radar_id':'KCXX','scan_time_utc':'2026-01-01T12:00:00Z'})
    monkeypatch.setattr('scripts.process_live_volume.apply_radar_origin',lambda *a,**k:None)
    monkeypatch.setattr('scripts.process_live_volume.resolve_fields',lambda radar:{'reflectivity':'z'})
    monkeypatch.setattr('scripts.process_live_volume.grid_lowest_sweep',lambda *a,**k:object())
    monkeypatch.setattr('scripts.process_live_volume.grid_field_2d',lambda *a,**k:np.ones((2,2)))
    monkeypatch.setattr('scripts.process_live_volume.grid_latlon',lambda grid:(np.array([[44,44],[44.01,44.01]]),np.array([[-73,-72.99],[-73,-72.99]])))
    monkeypatch.setattr('scripts.process_live_volume.detect_reflectivity_objects',lambda data:[{'object_id':1,'pixel_count':4,'max_reflectivity_dbz':30.0,'mean_reflectivity_dbz':25.0,'core_pixel_count':0,'row_centroid':0.5,'column_centroid':0.5,'row_indices':[0,0,1,1],'column_indices':[0,1,0,1],'touches_grid_edge':True}])
    from processing.object_tracker import CentroidTracker
    monkeypatch.setattr('scripts.process_live_volume.CentroidTracker',lambda *a,**k:CentroidTracker())
    monkeypatch.setattr('scripts.process_live_volume.acquire_for_radar_time',lambda *a,**k:None)
    monkeypatch.setattr('scripts.process_live_volume.append_history',lambda *a,**k:None)
    state=tmp_path/'state.json'; output=tmp_path/'out.geojson'
    process_volume(Path('KCXX_test'),state,output)
    geo=json.loads(output.read_text())
    p=geo['features'][0]['properties']
    assert p['touches_grid_edge'] is True
    assert p['data_quality']=='review'