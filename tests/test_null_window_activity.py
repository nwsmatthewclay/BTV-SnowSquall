import pandas as pd
from scripts.classify_null_windows import classify

def test_null_activity_taxonomy_identifies_hard_negative_candidate():
    frame=pd.DataFrame({
        'null_id':['N1','N1','N2'],
        'radar_site':['KCXX','KTYX','KCXX'],
        'object_id':[1,2,3],
        'scan_time_utc':['2026-01-01T12:00Z','2026-01-01T12:05Z','2026-01-02T12:00Z'],
        'max_reflectivity_dbz':[42.0,35.0,18.0],
        'core_pixel_count':[3,0,0],
    })
    result=classify(frame)
    assert result.loc[result['null_id']=='N1','activity_class'].iloc[0]=='high_activity_hard_negative_candidate'
    assert result.loc[result['null_id']=='N2','activity_class'].iloc[0]=='light_activity'
    assert result['selection_policy'].eq('diagnostic_only').all()