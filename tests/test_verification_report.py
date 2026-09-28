import pandas as pd
import pytest
from scripts.build_verification_report import verify

def test_verification_report_computes_probability_metrics():
    frame=pd.DataFrame({
      'y':[0,0,0,1,1,1],
      'p':[0.05,0.2,0.35,0.55,0.8,0.95]
    })
    report=verify(frame,'y','p')
    assert report['overall']['rows']==6
    assert 0.0 <= report['overall']['roc_auc'] <= 1.0
    assert report['overall']['brier_score'] >= 0.0
    assert len(report['threshold_diagnostics'])==4
    assert len(report['reliability']) > 0

def test_verification_rejects_invalid_probability_values():
    frame=pd.DataFrame({'y':[0,1,0,1],'p':[0.1,0.9,1.2,0.3]})
    report=verify(frame,'y','p')
    assert report['overall']['rows']==3

def test_verification_requires_both_classes():
    frame=pd.DataFrame({'y':[1,1,1],'p':[0.4,0.5,0.6]})
    with pytest.raises(ValueError,match='both observed classes'):
        verify(frame,'y','p')
