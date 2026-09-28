import pandas as pd

from scripts.build_object_track_catalog import build_track_catalog


def test_track_catalog_handles_scalar_aspect_values(tmp_path):
    source = tmp_path / "object_scans.csv"
    output = tmp_path / "tracks.csv"
    pd.DataFrame({
        "object_id": [1, 1, 2],
        "radar_site": ["KCXX", "KCXX", "KTYX"],
        "scan_time_utc": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            "2026-01-01T00:00:00Z",
        ],
        "max_reflectivity_dbz": [30.0, 35.0, 25.0],
        "mean_reflectivity_dbz": [24.0, 28.0, 22.0],
        "area_km2": [20.0, 30.0, 40.0],
        "aspect_ratio": [2.0, 3.0, 1.5],
    }).to_csv(source, index=False)

    result = build_track_catalog(source)

    assert len(result) == 2
    track_one = result.loc[result["object_id"] == 1].iloc[0]
    assert track_one["scan_count"] == 2
    assert track_one["max_aspect_ratio"] == 3.0
    assert track_one["median_aspect_ratio"] == 2.5
