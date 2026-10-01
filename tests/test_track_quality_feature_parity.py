import pandas as pd
from scripts.live_model_features import build_live_feature_row
from scripts.build_model_features import build_features

def test_track_quality_diagnostics_propagate():
    row=build_live_feature_row({
      "timestamp":"2026-01-01T12:05:00Z","track_id":"1",
      "track_association_distance_px":2.0,"track_association_gate_px":10.0,
      "track_association_cost":0.2,"track_age_scans":4,"track_missed_scans":0,
      "track_competing_track_count":1,"track_competing_object_count":2,
      "track_merge_candidate":True,"track_split_candidate":True,
      "max_reflectivity_dbz":35.0,"mean_reflectivity_dbz":28.0,
      "area_km2":20.0,"length_km":8.0
    })
    assert row["track_association_distance_px"]==2.0
    assert row["track_merge_candidate"] is True

def test_historical_builder_keeps_track_quality_fields():
    d=pd.DataFrame({
      "population":["null"],"radar_site":["KCXX"],"object_id":[1],
      "scan_time_utc":["2026-01-01T00:00:00Z"],
      "max_reflectivity_dbz":[35.0],"mean_reflectivity_dbz":[28.0],
      "area_km2":[20.0],"track_association_cost":[0.2],
      "squall_onset_within_15m":[0],
    })
    out=build_features(d)
    assert "track_association_cost" in out.columns
