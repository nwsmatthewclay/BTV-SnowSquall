from src.snow_squall.features import select_features
import pandas as pd

def test_radar_storm_motion_is_declared_feature():
    d=pd.DataFrame({
        "motion_speed_kt":[20.0],"motion_direction_deg":[90.0],
        "radar_motion_speed_kt":[22.0],"radar_motion_direction_deg":[95.0],
        "radar_motion_confidence":[0.8],
    })
    cols=select_features(d)
    assert "radar_motion_speed_kt" in cols
    assert "radar_motion_direction_deg" in cols
    assert "radar_motion_confidence" in cols
