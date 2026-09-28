import json
import pandas as pd
import pytest
from scripts.audit_pilot_labels import main

def test_pilot_label_audit_rejects_implausible_station_distance(tmp_path, monkeypatch):
    labeled=tmp_path/"labeled.csv"
    cases=tmp_path/"cases.csv"
    out=tmp_path/"out.json"
    pd.DataFrame([{
        "case_id":"BTVTEST","scan_time_utc":"2026-09-28T12:00:00Z",
        "centroid_lat":44.5,"centroid_lon":0.0,"radar_site":"KCXX",
        "track_event_associated":False,
        "squall_onset_within_15m":0,"squall_onset_within_30m":0,
        "squall_onset_within_45m":0,"squall_onset_within_60m":0
    }]).to_csv(labeled,index=False)
    pd.DataFrame([{
        "case_id":"BTVTEST","observing_station":"KBTV","event_start_utc":"2026-09-28T12:05:00Z"
    }]).to_csv(cases,index=False)
    monkeypatch.setattr("sys.argv",["audit_pilot_labels.py",str(labeled),"--cases",str(cases),"--output",str(out)])
    with pytest.raises(ValueError,match="Coordinate sanity guard"):
        main()
    report=json.loads(out.read_text())
    assert report["coordinate_guard_failures"]
