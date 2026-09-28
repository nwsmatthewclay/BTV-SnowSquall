import pandas as pd
from scripts.audit_modern_validation_manifest import audit

def test_modern_manifest_is_validation_only(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20181121','event_date_utc':'2018-11-21','radar_site':'KCXX',
      'truth_role':'validation_candidate','independence_status':'independent_candidate',
      'evidence_source':'NWS_BTV'
    }]).to_csv(p,index=False)
    result=audit(p)
    assert result['training_eligible'] is False
    assert result['records']==1

def test_modern_manifest_rejects_non_validation_role(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20181121','event_date_utc':'2018-11-21','radar_site':'KCXX',
      'truth_role':'training_case','independence_status':'independent_candidate',
      'evidence_source':'NWS_BTV'
    }]).to_csv(p,index=False)
    import pytest
    with pytest.raises(ValueError,match='non_validation_truth_role') as exc:
        audit(p)

def test_repository_modern_manifest_is_csv_parseable():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    df=pd.read_csv(root/'data/manifests/modern_independent_validation_cases.csv')
    assert len(df)==2
    assert set(df['truth_role'])=={'validation_candidate'}
    assert set(df['independence_status'])=={'independent_candidate'}


def test_modern_manifest_rejects_missing_or_invalid_provenance_url(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20181121','event_date_utc':'2018-11-21','radar_site':'KCXX',
      'truth_role':'validation_candidate','independence_status':'independent_candidate',
      'evidence_source':'NWS_BTV','source_url':'not-a-url'
    }]).to_csv(p,index=False)
    import pytest
    with pytest.raises(ValueError,match='invalid_source_url'):
        audit(p)
