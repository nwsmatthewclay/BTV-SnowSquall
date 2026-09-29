import pandas as pd

from scripts.annotate_object_population import annotate
from scripts.build_model_features import build_features


def test_episode_id_is_propagated_from_manifest(tmp_path):
    objects = pd.DataFrame([{
        "scan_time_utc": "2025-01-01T12:00:00Z",
        "radar_site": "KCXX",
        "object_id": "1",
    }])
    manifest = pd.DataFrame([{
        "case_id": "CASE1",
        "episode_id": "EP1",
        "radar_site": "KCXX",
        "window_start_utc": "2025-01-01T11:00:00Z",
        "window_end_utc": "2025-01-01T13:00:00Z",
        "window_center_utc": "2025-01-01T12:00:00Z",
        "source": "test",
    }])
    op = tmp_path / "objects.csv"
    mp = tmp_path / "manifest.csv"
    out = tmp_path / "annotated.csv"
    objects.to_csv(op, index=False)
    manifest.to_csv(mp, index=False)
    annotate(op, mp, out)
    result = pd.read_csv(out)
    assert result.iloc[0]["episode_id"] == "EP1"


def test_feature_builder_accepts_episode_id_group(tmp_path):
    frame = pd.DataFrame([
        {
            "population": "verified_case_context",
            "episode_id": "EP1",
            "case_id": "CASE1",
            "null_id": None,
            "radar_site": "KCXX",
            "object_id": "1",
            "scan_time_utc": "2025-01-01T12:00:00Z",
            "max_reflectivity_dbz": 30.0,
            "mean_reflectivity_dbz": 20.0,
            "area_km2": 10.0,
        },
        {
            "population": "verified_case_context",
            "episode_id": "EP1",
            "case_id": "CASE1",
            "null_id": None,
            "radar_site": "KCXX",
            "object_id": "1",
            "scan_time_utc": "2025-01-01T12:05:00Z",
            "max_reflectivity_dbz": 35.0,
            "mean_reflectivity_dbz": 22.0,
            "area_km2": 12.0,
        },
    ])
    result = build_features(frame)
    assert result.iloc[1]["track_scan_index"] == 1
