import pandas as pd
import pytest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from snow_squall.features import add_derived_features
from snow_squall.labels import add_lead_time_target,exclude_leakage_columns

def test_derived_features():
    d=pd.DataFrame({"area_km2":[20.0],"length_km":[10.0],"reflectivity_max_dbz":[35.0],"reflectivity_mean_dbz":[25.0]})
    x=add_derived_features(d)
    assert x.loc[0,"area_per_length"] == pytest.approx(2.0)
    assert x.loc[0,"reflectivity_core_excess"]==10.0

def test_target_and_leakage():
    d=pd.DataFrame({"scan_time":["2026-01-01T00:00Z"],"truth_onset_time":["2026-01-01T00:20Z"]})
    x=add_lead_time_target(d)
    assert x.loc[0,"snow_squall_30min"]==1
    assert "truth_onset_time" not in exclude_leakage_columns(x.columns.tolist())
