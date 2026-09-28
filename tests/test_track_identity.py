import pandas as pd

from scripts.build_object_track_catalog import build_track_catalog


def test_track_catalog_does_not_merge_same_object_id_across_radars(tmp_path):
    source = pd.DataFrame(
        {
            "radar_site": ["KCXX", "KCXX", "KTYX", "KTYX"],
            "object_id": [1, 1, 1, 1],
            "scan_time_utc": [
                "2006-02-07T03:00:00Z",
                "2006-02-07T03:05:00Z",
                "2006-02-07T03:00:00Z",
                "2006-02-07T03:05:00Z",
            ],
            "max_reflectivity_dbz": [20, 30, 10, 15],
            "mean_reflectivity_dbz": [10, 15, 8, 9],
            "area_km2": [10, 20, 5, 6],
            "geometry_wkt": ["POINT(0 0)"] * 4,
        }
    )
    path = tmp_path / "objects.csv"
    source.to_csv(path, index=False)

    result = build_track_catalog(path)

    assert len(result) == 2
    assert set(result["radar_site"]) == {"KCXX", "KTYX"}
    assert set(result["scan_count"]) == {2}
