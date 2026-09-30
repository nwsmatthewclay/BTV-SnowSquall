import pandas as pd

from scripts.build_modern_validation_manifest import build


def test_modern_validation_manifest_uses_window_start_when_anchor_missing(tmp_path):
    source=tmp_path/'source.csv'
    output=tmp_path/'cases.csv'
    radar=tmp_path/'radar.csv'
    pd.DataFrame([
        {
            'case_id':'BTV20181121',
            'event_date_utc':'2018-11-21',
            'event_anchor_utc':'',
            'radar_site':'KCXX',
            'observing_station':'KBTV',
            'evidence_source':'test',
            'visibility_miles':0.125,
            'wind_gust_kt':34.8,
            'truth_role':'validation_candidate',
            'independence_status':'independent_candidate',
            'reconstruction_eligible':True,
            'analysis_window_start_utc':'2018-11-21T16:30:00Z',
            'analysis_window_end_utc':'2018-11-21T18:30:00Z',
        }
    ]).to_csv(source,index=False)
    build(source,output,radar)
    cases=pd.read_csv(output)
    out=pd.read_csv(radar)
    assert cases.loc[0,'event_start_utc']=='2018-11-21T16:30:00Z'
    assert cases.loc[0,'anchor_source']=='validation_window_start'
    assert out.loc[0,'window_start_utc']=='2018-11-21T16:30:00Z'


def test_modern_validation_manifest_preserves_explicit_anchor(tmp_path):
    source=tmp_path/'source.csv'; output=tmp_path/'cases.csv'; radar=tmp_path/'radar.csv'
    pd.DataFrame([
        {
            'case_id':'BTV20191218','event_date_utc':'2019-12-18',
            'event_anchor_utc':'2019-12-18T22:40:00Z','radar_site':'KCXX',
            'observing_station':'KMPV','evidence_source':'test',
            'truth_role':'validation_candidate','independence_status':'independent_candidate',
            'reconstruction_eligible':True,'analysis_window_start_utc':'2019-12-18T22:25:00Z',
            'analysis_window_end_utc':'2019-12-18T23:40:00Z'
        }
    ]).to_csv(source,index=False)
    build(source,output,radar)
    cases=pd.read_csv(output)
    assert cases.loc[0,'event_start_utc']=='2019-12-18T22:40:00Z'
    assert cases.loc[0,'anchor_source']=='case_anchor'
