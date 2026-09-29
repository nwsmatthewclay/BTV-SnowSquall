import pandas as pd

from scripts.build_unified_object_dataset import build


def test_unified_dataset_carries_null_activity_metadata(tmp_path):
    positive = pd.DataFrame(
        [{
            "case_id": "CASE1",
            "object_id": "1",
            "radar_site": "KCXX",
            "scan_time_utc": "2020-01-01T00:00:00Z",
        }]
    )
    nulls = pd.DataFrame(
        [{
            "null_id": "NULL1",
            "object_id": "2",
            "radar_site": "KCXX",
            "scan_time_utc": "2020-01-02T00:00:00Z",
        }]
    )
    activity = pd.DataFrame(
        [{
            "null_id": "NULL1",
            "activity_class": "high_activity_hard_negative_candidate",
        }]
    )

    positive_path = tmp_path / "positive.csv"
    null_path = tmp_path / "null.csv"
    activity_path = tmp_path / "activity.csv"
    output_path = tmp_path / "unified.csv"
    positive.to_csv(positive_path, index=False)
    nulls.to_csv(null_path, index=False)
    activity.to_csv(activity_path, index=False)

    build(positive_path, null_path, output_path, activity_path)
    result = pd.read_csv(output_path)

    row = result[result["null_id"].eq("NULL1")].iloc[0]
    assert row["activity_class"] == "high_activity_hard_negative_candidate"
