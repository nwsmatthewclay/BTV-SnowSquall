import json
import pandas as pd
from scripts.compare_research_operational_replay import compare, load_replay

def test_replay_comparator_matches_nearby_objects(tmp_path):
    research=pd.DataFrame([
      {'scan_time_utc':'2026-01-01T12:00Z','object_id':1,'centroid_lat':44.0,'centroid_lon':-73.0},
      {'scan_time_utc':'2026-01-01T12:00Z','object_id':2,'centroid_lat':44.5,'centroid_lon':-73.0},
    ])
    replay=pd.DataFrame([
      {'scan_time_utc':pd.Timestamp('2026-01-01T12:00Z',tz='UTC'),'track_id':'1','centroid_lat':44.001,'centroid_lon':-73.0},
      {'scan_time_utc':pd.Timestamp('2026-01-01T12:00Z',tz='UTC'),'track_id':'2','centroid_lat':44.501,'centroid_lon':-73.0},
    ])
    report=compare(research,replay,match_radius_km=2)
    assert report['scans_compared']==1
    assert report['matched_objects']==2
    assert report['match_fraction_research']==1.0
    assert report['median_match_distance_km'] < 0.2

def test_load_replay_ignores_malformed_geojson(tmp_path):
    (tmp_path/'bad.geojson').write_text('{not json',encoding='utf-8')
    result=load_replay(tmp_path)
    assert result.empty