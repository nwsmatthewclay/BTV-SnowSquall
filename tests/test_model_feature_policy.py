import pandas as pd
from scripts.build_model_features import predictor_columns, write_schema

def test_geographic_coordinates_are_not_baseline_predictors():
    frame=pd.DataFrame({
        'centroid_lat':[44.47], 'centroid_lon':[-73.15],
        'reflectivity_max_dbz':[35.0], 'area_km2':[25.0],
        'track_age_min':[5.0], 'environment_age_minutes':[60.0],
    })
    cols=predictor_columns(frame)
    assert 'centroid_lat' not in cols
    assert 'centroid_lon' not in cols
    assert 'reflectivity_max_dbz' in cols
    assert 'track_age_min' in cols

def test_operational_predictors_are_declared_and_live_compatible():
    from scripts.build_model_features import OPERATIONAL_LIVE_PREDICTORS, predictor_columns
    frame=pd.DataFrame({
        "max_reflectivity_dbz":[35.0],
        "area_km2":[25.0],
        "track_age_min":[5.0],
        "centroid_lat":[44.47],
        "centroid_lon":[-73.15],
        "mucape_jkg":[100.0],
    })
    cols=predictor_columns(frame)
    assert "max_reflectivity_dbz" in cols
    assert "mucape_jkg" in OPERATIONAL_LIVE_PREDICTORS
    assert "centroid_lat" not in cols
