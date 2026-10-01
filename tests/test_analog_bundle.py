from pathlib import Path
import pandas as pd
from src.snow_squall.analogs import AnalogLibrary

def test_analog_library_round_trip(tmp_path):
    d=pd.DataFrame({"case_id":["A","B","C"],"scan_time_utc":["2026-01-01T00:00:00Z","2026-01-02T00:00:00Z","2026-01-03T00:00:00Z"],"max_reflectivity_dbz":[20,30,40],"snsq":[.5,1,2],"squall_onset_within_15m":[0,1,0],"squall_onset_within_30m":[0,1,1],"squall_onset_within_45m":[0,1,1],"squall_onset_within_60m":[0,1,1]})
    p=tmp_path/"analog.joblib"
    lib=AnalogLibrary.fit(d); lib.save(p); loaded=AnalogLibrary.load(p)
    q=loaded.query(d.iloc[[2]],top_k=2)
    assert Path(p).exists()
    assert q.iloc[0]["analog_count"]==2