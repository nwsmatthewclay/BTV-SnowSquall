import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snow_squall.features import add_derived_features
from training.train_models import train_baselines


def test_shear_motion_ratio_handles_zero_speed():
    frame = pd.DataFrame({
        "shear_0_6km_kt": [20.0],
        "motion_speed_kt": [0.0],
    })
    result = add_derived_features(frame)
    assert result.loc[0, "shear_motion_ratio"] == pytest.approx(20_000_000.0)


def test_legacy_trainer_uses_boolean_case_split_masks():
    rows=[]
    for case_index in range(6):
        for row_index in range(3):
            rows.append({
                "case_id": f"CASE{case_index}",
                "scan_time": f"2026-01-{case_index+1:02d}T0{row_index}:00:00Z",
                "snow_squall_30min": int(case_index % 2 == 0 and row_index == 0),
                "area_km2": 20.0 + row_index,
                "length_km": 10.0,
                "reflectivity_max_dbz": 30.0 + case_index,
                "reflectivity_mean_dbz": 20.0,
            })
    frame = pd.DataFrame(rows)
    results = train_baselines(frame)
    assert len(results) == 3
    assert all("brier_score" in result.metrics for result in results)
