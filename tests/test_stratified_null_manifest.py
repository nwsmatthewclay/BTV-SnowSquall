import pandas as pd
import pytest

from scripts.build_stratified_null_manifest import build_null_windows


def test_stratified_nulls_avoid_case_exclusion_and_separate_windows(tmp_path):
    cases = pd.DataFrame(
        {
            "case_id": ["CASE1"],
            "event_start_utc": ["2005-02-13T09:24:00Z"],
        }
    )
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)

    result = build_null_windows(
        cases_path,
        "2005-02-01T00:00:00Z",
        "2005-03-01T00:00:00Z",
        sample_count=3,
        seed=42,
        min_separation_hours=24,
        radars=("KCXX",),
    )

    centers = pd.to_datetime(result["window_center_utc"], utc=True)
    assert result["case_id"].eq("").all()
    assert result["window_id"].is_unique
    assert result["null_id"].nunique() == 3
    assert not ((centers - pd.Timestamp("2005-02-13T09:24:00Z")).abs() <= pd.Timedelta(hours=7)).any()


def test_stratified_nulls_raise_when_constraints_impossible(tmp_path):
    cases = pd.DataFrame(
        {"case_id": ["CASE1"], "event_start_utc": ["2005-02-13T09:24:00Z"]}
    )
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)

    with pytest.raises(ValueError):
        build_null_windows(
            cases_path,
            "2005-02-13T00:00:00Z",
            "2005-02-13T12:00:00Z",
            sample_count=2,
            seed=1,
            min_separation_hours=24,
            radars=("KCXX",),
        )


def test_stratified_nulls_cover_multiple_years(tmp_path):
    years = pd.DataFrame(
        {
            "case_id": ["CASE1"],
            "event_start_utc": ["2005-02-13T09:24:00Z"],
        }
    )
    cases_path = tmp_path / "cases.csv"
    years.to_csv(cases_path, index=False)

    result = build_null_windows(
        cases_path,
        "2002-11-01T00:00:00Z",
        "2005-03-31T21:00:00Z",
        sample_count=6,
        seed=7,
        min_separation_hours=24,
        radars=("KCXX",),
    )

    selected = pd.to_datetime(result["window_center_utc"], utc=True)
    assert selected.dt.year.nunique() >= 3
