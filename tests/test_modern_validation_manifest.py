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
    with pytest.raises(ValueError,match='training') as exc:
        audit(p)