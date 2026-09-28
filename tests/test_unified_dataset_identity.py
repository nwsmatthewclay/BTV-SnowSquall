import pandas as pd
import pytest
from scripts.build_unified_object_dataset import build

def test_unified_dataset_rejects_duplicate_object_timesteps(tmp_path):
    pos=tmp_path/'pos.csv'; nul=tmp_path/'null.csv'; out=tmp_path/'out.csv'
    row={'case_id':'CASE1','radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00:00Z'}
    pd.DataFrame([row,row]).to_csv(pos,index=False)
    pd.DataFrame([{'null_id':'N1','radar_site':'KCXX','object_id':2,'scan_time_utc':'2026-01-02T12:00:00Z'}]).to_csv(nul,index=False)
    with pytest.raises(ValueError,match='duplicate object-timestep'): build(pos,nul,out)

def test_unified_dataset_rejects_cross_population_identity_contamination(tmp_path):
    pos=tmp_path/'pos.csv'; nul=tmp_path/'null.csv'; out=tmp_path/'out.csv'
    pd.DataFrame([{'case_id':'CASE1','null_id':'N1','radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00:00Z'}]).to_csv(pos,index=False)
    pd.DataFrame([{'null_id':'N2','radar_site':'KCXX','object_id':2,'scan_time_utc':'2026-01-02T12:00:00Z'}]).to_csv(nul,index=False)
    with pytest.raises(ValueError,match='must not contain null_id'): build(pos,nul,out)

def test_unified_dataset_writes_unique_row_identity(tmp_path):
    pos=tmp_path/'pos.csv'; nul=tmp_path/'null.csv'; out=tmp_path/'out.csv'
    pd.DataFrame([{'case_id':'CASE1','radar_site':'KCXX','object_id':1,'scan_time_utc':'2026-01-01T12:00:00Z'}]).to_csv(pos,index=False)
    pd.DataFrame([{'null_id':'N1','radar_site':'KCXX','object_id':2,'scan_time_utc':'2026-01-02T12:00:00Z'}]).to_csv(nul,index=False)
    build(pos,nul,out)
    result=pd.read_csv(out)
    assert result['row_identity_key'].is_unique