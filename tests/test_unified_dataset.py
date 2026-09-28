import pandas as pd
from pathlib import Path

from scripts.build_unified_object_dataset import build


def test_unified_dataset_preserves_candidate_null_status(tmp_path):
    positive = tmp_path / "positive.csv"
    nulls = tmp_path / "null.csv"
    output = tmp_path / "combined.csv"

    pd.DataFrame({
        "object_id": [1],
        "scan_time_utc": ["2006-02-07T01:00:00Z"],
        "case_id": ["BTV20060207"],
    }).to_csv(positive, index=False)

    pd.DataFrame({
        "object_id": [2],
        "scan_time_utc": ["2006-02-08T01:00:00Z"],
        "null_id": ["NULL0002"],
    }).to_csv(nulls, index=False)

    build(positive, nulls, output)
    result = pd.read_csv(output)

    assert set(result["population"]) == {"verified_case_context", "winter_null_candidate"}
    assert result.loc[result["object_id"] == 2, "truth_status"].iloc[0] == "unverified_null_candidate"
    assert result["population_track_key"].notna().all()
