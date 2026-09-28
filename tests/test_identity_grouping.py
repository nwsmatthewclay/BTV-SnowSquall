import pandas as pd
from scripts.build_model_features import build_features
from scripts.build_unified_object_dataset import build

def test_feature_grouping_does_not_bridge_reused_object_ids_across_cases():
    frame=pd.DataFrame({
        'population':['verified_case_context']*2,
        'case_id':['CASE1','CASE2'],
        'null_id':[None,None],
        'radar_site':['KCXX','KCXX'],
        'object_id':[1,1],
        'scan_time_utc':['2020-01-01T12:00Z','2020-01-01T12:05Z'],
        'max_reflectivity_dbz':[20.0,30.0],
    })
    out=build_features(frame)
    assert out['track_scan_count_to_date'].tolist()==[1,1]

def test_unified_track_keys_include_case_identity(tmp_path):
    pos=tmp_path/'pos.csv'; nul=tmp_path/'null.csv'; out=tmp_path/'out.csv'
    pd.DataFrame([{'case_id':'CASE1','radar_site':'KCXX','object_id':1,'scan_time_utc':'2020-01-01T12:00Z'}]).to_csv(pos,index=False)
    pd.DataFrame([{'null_id':'NULL1','radar_site':'KCXX','object_id':1,'scan_time_utc':'2020-01-02T12:00Z'}]).to_csv(nul,index=False)
    build(pos,nul,out)
    d=pd.read_csv(out)
    assert d['population_track_key'].is_unique
    assert d.loc[d['population']=='verified_case_context','population_track_key'].iloc[0] != d.loc[d['population']=='winter_null_candidate','population_track_key'].iloc[0]