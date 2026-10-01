import numpy as np
import pandas as pd
from processing.object_detector import detect_reflectivity_objects
from scripts.build_object_track_catalog import build_track_catalog

def test_detector_marks_boundary_touching_object():
    field=np.zeros((30,30),dtype=float)
    field[0:6,0:5]=30.0
    objs=detect_reflectivity_objects(field)
    assert len(objs)==1
    assert objs[0]['touches_grid_edge'] is True

def test_track_catalog_flags_boundary_touching_track(tmp_path):
    p=tmp_path/'objects.csv'
    pd.DataFrame([
      {'radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00:00Z','max_reflectivity_dbz':30,'mean_reflectivity_dbz':20,'area_km2':20,'aspect_ratio':2,'motion_speed_kt':20,'touches_grid_edge':True,'geometry_wkt':'POLYGON((0 0,1 0,1 1,0 0))'},
      {'radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:05:00Z','max_reflectivity_dbz':32,'mean_reflectivity_dbz':21,'area_km2':22,'aspect_ratio':2.1,'motion_speed_kt':21,'touches_grid_edge':False,'geometry_wkt':'POLYGON((0 0,1 0,1 1,0 0))'},
    ]).to_csv(p,index=False)
    row=build_track_catalog(p).iloc[0]
    assert row['qc_status']=='review'
    assert 'touches_grid_edge' in row['qc_flags']