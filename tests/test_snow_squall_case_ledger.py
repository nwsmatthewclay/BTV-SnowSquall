import pandas as pd

from scripts.merge_snow_squall_case_sources import load_study_records, canonical_class


def test_banacos_study_records_are_stable(tmp_path):
    study = pd.DataFrame([{
        'case_id':'BTV20020323',
        'source_case_id':'01',
        'event_start_utc':'2002-03-23T22:11:00Z',
        'observing_station':'KBTV',
        'min_visibility_km':0.4,
        'vis_below_0p8_min':48,
        'peak_wind_kt':19,
        'hybrid_case':True,
        'notes':'Original Table 2',
    }])
    path=tmp_path/'study.csv'
    study.to_csv(path,index=False)
    records=load_study_records(path)
    assert len(records)==1
    record=records[0]
    assert record['case_id']=='BTV20020323'
    assert record['candidate_id']=='BTV20020323'
    assert record['source_types']=={'BANACOS_STUDY_2014'}
    assert record['event_end_utc']=='2002-03-23T22:59:00+00:00'
    assert record['study_hybrid_case'] is True


def test_study_plus_ncei_is_strong_class():
    assert canonical_class({'BANACOS_STUDY_2014','NCEI_STORM_EVENTS'})=='official_plus_study'
    assert canonical_class({'BANACOS_STUDY_2014','IEM_COW_SQW'}, True)=='study_warning_verified'
