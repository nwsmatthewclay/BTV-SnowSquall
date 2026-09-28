import pandas as pd
from scripts.enrich_object_environment import enrich

def test_null_population_status_is_explicit(tmp_path, monkeypatch):
    source=tmp_path/'objects.csv'; output=tmp_path/'out.csv'
    pd.DataFrame([{'scan_time_utc':'2026-01-01T12:00:00Z','object_id':1,'centroid_lat':44.47,'centroid_lon':-73.15}]).to_csv(source,index=False)
    monkeypatch.setattr('scripts.enrich_object_environment.acquire_for_radar_time', lambda *args, **kwargs: None)
    enrich(source,output,tmp_path/'rap',tmp_path/'ruc')
    result=pd.read_csv(output)
    assert result.loc[0,'label_status']=='candidate_null'