import pandas as pd

from scripts.annotate_object_population import annotate


def test_null_annotation_uses_null_id_not_case_id(tmp_path):
    objects = pd.DataFrame(
        {
            "radar_site": ["KCXX", "KCXX"],
            "scan_time_utc": [
                "2005-11-01T01:30:00Z",
                "2005-11-01T04:30:00Z",
            ],
            "object_id": [1, 2],
        }
    )
    manifest = pd.DataFrame(
        {
            "case_id": ["", ""],
            "window_id": ["NULL0001_KCXX", "NULL0002_KCXX"],
            "radar_site": ["KCXX", "KCXX"],
            "null_id": ["NULL0001", "NULL0002"],
            "window_center_utc": [
                "2005-11-01T01:30:00Z",
                "2005-11-01T04:30:00Z",
            ],
            "window_start_utc": [
                "2005-11-01T00:00:00Z",
                "2005-11-01T03:00:00Z",
            ],
            "window_end_utc": [
                "2005-11-01T03:00:00Z",
                "2005-11-01T06:00:00Z",
            ],
            "source": ["test", "test"],
        }
    )

    input_path = tmp_path / "objects.csv"
    manifest_path = tmp_path / "manifest.csv"
    output_path = tmp_path / "annotated.csv"
    objects.to_csv(input_path, index=False)
    manifest.to_csv(manifest_path, index=False)

    annotate(input_path, manifest_path, output_path)
    result = pd.read_csv(output_path)

    assert result["case_id"].isna().all()
    assert list(result["null_id"]) == ["NULL0001", "NULL0002"]
    assert list(result["population_id"]) == ["NULL0001", "NULL0002"]
    assert list(result["window_id"]) == ["NULL0001_KCXX", "NULL0002_KCXX"]
