import numpy as np
from scripts.train_baseline_model import grouped_bootstrap_intervals

def test_grouped_bootstrap_returns_95pct_intervals():
    y=np.array([0,1,0,1,0,1,0,1])
    p=np.array([0.1,0.8,0.2,0.7,0.3,0.9,0.4,0.6])
    groups=np.array(['A','A','B','B','C','C','D','D'])
    result=grouped_bootstrap_intervals(y,p,groups,n_boot=100,seed=42)
    assert result['group_count']==4
    assert result['auc_roc']['lower'] <= result['auc_roc']['median'] <= result['auc_roc']['upper']
    assert result['average_precision']['samples'] > 0