import numpy as np
from scripts.reconstruct_pilot import object_shape_metrics

def test_historical_shape_metrics_match_live_contract():
    rows=np.array([10,10,10,11,12,13])
    cols=np.array([2,3,4,5,6,7])
    major,minor,orientation=object_shape_metrics(rows,cols,1.0)
    assert major>minor
    assert 0<=orientation<180