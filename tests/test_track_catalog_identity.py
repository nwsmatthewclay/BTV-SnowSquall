import pandas as pd
from scripts.build_object_track_catalog import build_track_catalog

def test_track_catalog_does_not_merge_reused_ids_across_cases(tmp_path):
    p=tmp_path/'objects.csv'
    pd.DataFrame([
      {'population':'verified_case_context','case_id':'CASE1','radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00Z','max_reflectivity_dbz':30,'mean_reflectivity_dbz':20,'area_km2':20,'aspect_ratio':2,'geometry_wkt':'POLYGON((0 0,1 0,1 1,0 0))'},
      {'population':'verified_case_context','case_id':'CASE2','radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-02T12:00Z','max_reflectivity_dbz':31,'mean_reflectivity_dbz':21,'area_km2':21,'aspect_ratio':2.1,'geometry_wkt':'POLYGON((0 0,1 0,1 1,0 0))'},
    ]).to_csv(p,index=False)
    out=build_track_catalog(p)
    assert len(out)==2
    assert set(out['case_id'])=={'CASE1','CASE2'}
    assert set(out['scan_count'])=={1}