import pandas as pd
import pytest
from scripts.audit_environment_attachment import audit

def test_environment_attachment_audit_passes_time_matched_row(tmp_path):
    p=tmp_path/'env.csv'
    pd.DataFrame([{'scan_time_utc':'2020-01-01T12:00:00Z','environment_valid_time_utc':'2020-01-01T11:00:00Z','environment_source':'RAP'}]).to_csv(p,index=False)
    result=audit(p,max_age_minutes=180)
    assert result['environment_attached_records']==1

def test_environment_attachment_audit_blocks_future_analysis(tmp_path):
    p=tmp_path/'env.csv'
    pd.DataFrame([{'scan_time_utc':'2020-01-01T12:00:00Z','environment_valid_time_utc':'2020-01-01T13:00:00Z','environment_source':'RAP'}]).to_csv(p,index=False)
    with pytest.raises(ValueError,match='future environment'): audit(p)

def test_environment_attachment_audit_blocks_wrong_historical_provider(tmp_path):
    p=tmp_path/'env.csv'
    pd.DataFrame([{'scan_time_utc':'2006-02-01T12:00:00Z','environment_valid_time_utc':'2006-02-01T11:00:00Z','environment_source':'RAP'}]).to_csv(p,index=False)
    with pytest.raises(ValueError,match='provider outside'): audit(p)