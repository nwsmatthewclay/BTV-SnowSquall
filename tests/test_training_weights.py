import pandas as pd
from src.snow_squall.training import case_scan_balanced_weights

def test_case_scan_weights_equalize_cases_and_scans():
    d=pd.DataFrame({
      "case_id":["A","A","A","B","B"],
      "scan_time_utc":[
        "2026-01-01T00:00:00Z","2026-01-01T00:00:00Z","2026-01-01T00:05:00Z",
        "2026-01-02T00:00:00Z","2026-01-02T00:05:00Z"],
    })
    w=case_scan_balanced_weights(d)
    assert abs(w[:3].sum()-w[3:].sum())<1e-9
    assert abs(w[0]-w[1])<1e-9
    assert w[2]>w[0]
