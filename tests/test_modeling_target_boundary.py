import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from snow_squall.labels import add_lead_time_target, add_multi_horizon_targets

def test_onset_at_scan_time_is_not_future_positive():
    frame=pd.DataFrame({'scan_time':['2026-01-01T12:00:00Z'],'truth_onset_time':['2026-01-01T12:00:00Z']})
    result=add_lead_time_target(frame)
    assert result.loc[0,'lead_time_min']==0
    assert result.loc[0,'snow_squall_30min']==0

def test_multi_horizon_targets_are_strictly_future():
    frame=pd.DataFrame({'scan_time':['2026-01-01T12:00:00Z'],'truth_onset_time':['2026-01-01T12:15:00Z']})
    result=add_multi_horizon_targets(frame)
    assert result.loc[0,'snow_squall_15min']==1
    assert result.loc[0,'snow_squall_30min']==1