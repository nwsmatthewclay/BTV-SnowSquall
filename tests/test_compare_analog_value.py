import pandas as pd
from scripts.compare_analog_value import evaluate

def test_fold_safe_analog_comparison_runs_on_small_case_set():
    rows=[]
    for i,case in enumerate(["A","B","C","D","E","F"]):
        rows.append({
            "case_id":case,
            "scan_time_utc":f"2026-01-0{i+1}T12:00:00Z",
            "max_reflectivity_dbz":30+i,
            "mean_reflectivity_dbz":25+i,
            "area_km2":10+i,
            "snsq":1+i*0.1,
            "cape_jkg":100+i*10,
            "squall_onset_within_15m":int(i%2==0),
        })
    report=evaluate(pd.DataFrame(rows),"squall_onset_within_15m")
    assert report["status"]=="ok"
    assert "analogs_hgb" in report["models"]
    assert "baseline_hgb" in report["models"]
