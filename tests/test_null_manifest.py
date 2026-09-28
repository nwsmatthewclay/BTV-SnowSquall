import pandas as pd

from scripts.build_null_window_manifest import build_null_windows


def test_null_windows_do_not_use_case_ids(tmp_path):
    cases = pd.DataFrame(
        {"event_start_utc": ["2006-02-07T04:47:00Z"]}
    )
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)

    result = build_null_windows(
        cases_path,
        "2005-11-01T00:00:00Z",
        "2005-11-10T00:00:00Z",
        sample_count=2,
        seed=1,
        radars=("KCXX", "KTYX"),
    )

    assert len(result) == 4
    assert result["case_id"].eq("").all()
    assert result["window_id"].notna().all()
    assert result["window_id"].is_unique
    assert result["null_id"].nunique() == 2
