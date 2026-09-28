import pandas as pd
from scripts.audit_modern_validation_manifest import audit

def test_modern_manifest_is_validation_only(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20181121','event_date_utc':'2018-11-21','radar_site':'KCXX',
      'truth_role':'validation_candidate','independence_status':'independent_candidate',
      'evidence_source':'NWS_BTV','source_url':'https://www.weather.gov/btv','reconstruction_eligible':True,'analysis_window_start_utc':'2018-11-21T16:30:00Z','analysis_window_end_utc':'2018-11-21T18:30:00Z'
    }]).to_csv(p,index=False)
    result=audit(p)
    assert result['training_eligible'] is False
    assert result['records']==1

def test_modern_manifest_rejects_non_validation_role(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20181121','event_date_utc':'2018-11-21','radar_site':'KCXX',
      'truth_role':'training_case','independence_status':'independent_candidate',
      'evidence_source':'NWS_BTV','source_url':'https://www.weather.gov/btv','reconstruction_eligible':True,'analysis_window_start_utc':'2018-11-21T16:30:00Z','analysis_window_end_utc':'2018-11-21T18:30:00Z'
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
    assert bool(df.loc[df['case_id']=='BTV20181121','reconstruction_eligible'].iloc[0]) is True
    assert bool(df.loc[df['case_id']=='BTV20191218','reconstruction_eligible'].iloc[0]) is True


def test_modern_manifest_rejects_missing_or_invalid_provenance_url(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20181121','event_date_utc':'2018-11-21','radar_site':'KCXX',
      'truth_role':'validation_candidate','independence_status':'independent_candidate',
      'evidence_source':'NWS_BTV','source_url':'not-a-url','reconstruction_eligible':True,'analysis_window_start_utc':'2018-11-21T16:30:00Z','analysis_window_end_utc':'2018-11-21T18:30:00Z'
    }]).to_csv(p,index=False)
    import pytest
    with pytest.raises(ValueError,match='invalid_source_url'):
        audit(p)


def test_modern_manifest_accepts_provenance_only_candidate_without_window(tmp_path):
    p=tmp_path/'modern.csv'
    pd.DataFrame([{
      'case_id':'BTV20191218','event_date_utc':'2019-12-18','radar_site':'KCXX',
      'truth_role':'validation_candidate','independence_status':'independent_candidate',
      'evidence_source':'NWSI_10-513','source_url':'https://www.weather.gov/media/directives/010_pdfs/pd01005013curr.pdf',
      'reconstruction_eligible':True,'analysis_window_start_utc':'2019-12-18T22:25:00Z','analysis_window_end_utc':'2019-12-18T23:40:00Z'
    }]).to_csv(p,index=False)
    result=audit(p)
    assert result['training_eligible'] is False


def test_modern_validation_workflow_is_non_scoring_and_manual():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    workflow=(root/'.github/workflows/modern-independent-validation.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in workflow
    assert 'Train case-held-out baseline models' not in workflow
    assert 'probability' not in workflow.lower() or 'probability_scored' in workflow
    assert 'Modern Independent Validation' in workflow
    assert 'modern_validation_level2_manifest.csv' in workflow
    assert 'acquire_modern_validation_mrms.py' in workflow


def test_case_summary_is_non_scoring(tmp_path, monkeypatch):
    from scripts.build_modern_validation_case_summary import build
    import json
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    (tmp_path/"data/raw/modern_surface/KMPV").mkdir(parents=True)
    (tmp_path/"data/derived").mkdir(parents=True)
    cases=tmp_path/"cases.csv"
    inventory=tmp_path/"inventory.json"
    pd.DataFrame([{
        "case_id":"CASE1","event_date_utc":"2019-12-18","radar_site":"KCXX",
        "observing_station":"KMPV","evidence_type":"warning_product_case_specific",
        "evidence_source":"NWS","source_url":"https://www.weather.gov/btv",
        "reconstruction_eligible":True,
        "analysis_window_start_utc":"2019-12-18T22:25:00Z",
        "analysis_window_end_utc":"2019-12-18T23:40:00Z",
    }]).to_csv(cases,index=False)
    inventory.write_text(json.dumps({"cases":[{
        "case_id":"CASE1","replay_scans":3,"replay_failed_scans":0,
        "replay_failure_rate":0.0,"replay_object_scan_count":12,
        "surface_rows":4,"min_visibility_mi":0.5,"max_gust_kt":31.0,
        "mrms_lcref_files":3,
    }]}),encoding="utf-8")
    out_json=tmp_path/"data/derived/summary.json"
    out_csv=tmp_path/"data/derived/summary.csv"
    payload=build(cases,inventory,out_json,out_csv)
    assert payload["training_eligible"] is False
    assert payload["scoring_status"]=="not_scored"
    assert payload["cases"][0]["probability_scored"] is False
