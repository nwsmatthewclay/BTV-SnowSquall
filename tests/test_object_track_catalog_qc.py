import pandas as pd
from scripts.build_object_track_catalog import build_track_catalog

def test_track_catalog_flags_duplicate_times_and_implausible_motion(tmp_path):
    path=tmp_path/'objects.csv'
    pd.DataFrame([{
        'radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00:00Z',
        'max_reflectivity_dbz':30,'mean_reflectivity_dbz':20,'area_km2':20,'aspect_ratio':2,
        'motion_speed_kt':25,'geometry_wkt':'POLYGON((0 0,1 0,1 1,0 0))'
      },{
        'radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00:00Z',
        'max_reflectivity_dbz':32,'mean_reflectivity_dbz':21,'area_km2':25,'aspect_ratio':2.2,
        'motion_speed_kt':125,'geometry_wkt':'POLYGON((0 0,1 0,1 1,0 0))'
      }]).to_csv(path,index=False)
    row=build_track_catalog(path).iloc[0]
    assert row['duplicate_scan_times']==1
    assert row['max_motion_speed_kt']==125
    assert row['qc_status']=='review'
    assert 'duplicate_scan_time' in row['qc_flags']
    assert 'implausible_motion_gt_100kt' in row['qc_flags']
