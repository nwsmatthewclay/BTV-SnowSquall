import pandas as pd

from scripts.build_unified_object_dataset import build


def test_expanded_dataset_version_is_explicit(tmp_path):
    positive = pd.DataFrame([{
        "scan_time_utc":"2026-01-01T12:00:00Z","object_id":"1","radar_site":"KCXX","case_id":"CASE1",
        "null_id":pd.NA,"label_status":"prospective_positive","squall_onset_within_15m":1
    }])
    nulls = pd.DataFrame([{
        "scan_time_utc":"2026-01-02T12:00:00Z","object_id":"2","radar_site":"KCXX","case_id":pd.NA,"null_id":"NULL1",
        "label_status":"candidate_null"
    }])
    p=tmp_path/'positive.csv'; n=tmp_path/'null.csv'; out=tmp_path/'out.csv'
    positive.to_csv(p,index=False); nulls.to_csv(n,index=False)
    build(p,n,out,dataset_version='object_population_expanded_v2')
    result=pd.read_csv(out)
    assert set(result["dataset_version"]) == {"object_population_expanded_v2"}