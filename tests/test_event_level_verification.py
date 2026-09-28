import pandas as pd
from scripts.build_event_level_verification import build

def test_event_level_verification_collapses_many_rows_to_one_group():
    frame=pd.DataFrame({
        'population':['verified_case_context']*3+['winter_null_candidate']*3,
        'case_id':['CASE1']*3+[None]*3,
        'null_id':[None]*3+['NULL1']*3,
        'y':[1,1,1,0,0,0],
        'p':[0.2,0.7,0.4,0.05,0.15,0.1],
    })
    report=build(frame,'y','p')
    assert report['positive_case_count']==1
    assert report['null_window_count']==1
    assert report['positive_cases'][0]['rows']==3
    assert report['positive_cases'][0]['max_probability']==0.7
    assert report['threshold_diagnostics'][1]['case_detection_fraction']==1.0
    assert report['threshold_diagnostics'][1]['null_window_alert_fraction']==0.0