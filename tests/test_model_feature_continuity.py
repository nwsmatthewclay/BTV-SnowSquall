import pandas as pd
from scripts.build_model_features import build_features

def test_temporal_derivatives_reset_across_large_track_gap():
    frame=pd.DataFrame({
        'population':['winter_null_candidate']*3,
        'radar_site':['KCXX']*3,
        'object_id':[1,1,1],
        'scan_time_utc':['2026-01-01T12:00:00Z','2026-01-01T12:05:00Z','2026-01-01T12:20:00Z'],
        'max_reflectivity_dbz':[20.0,30.0,35.0],
        'centroid_lat':[44.0,44.01,44.03],
        'centroid_lon':[-73.0,-73.0,-73.0],
    })
    out=build_features(frame)
    assert out.loc[1,'max_reflectivity_dbz_delta']==10.0
    assert pd.isna(out.loc[2,'max_reflectivity_dbz_delta'])
    assert out.loc[2,'track_gap_gt_10min'] is True
    assert pd.isna(out.loc[2,'centroid_displacement_km'])