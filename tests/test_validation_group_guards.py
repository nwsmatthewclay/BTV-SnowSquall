import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from snow_squall.validation import case_splits, chronological_case_split

def frame():
    return pd.DataFrame({'case_id':['A','A','B','B'],'scan_time':['2026-01-01','2026-01-01','2026-01-02','2026-01-02']})

def test_case_splits_reject_missing_group_identity():
    d=frame(); d.loc[0,'case_id']=None
    with pytest.raises(ValueError,match='missing values'): case_splits(d)

def test_chronological_split_returns_masks_for_valid_cases():
    train,test=chronological_case_split(frame(),fraction=0.5)
    assert train.dtype==bool and test.dtype==bool
    assert int(train.sum())==2
    assert int(test.sum())==2