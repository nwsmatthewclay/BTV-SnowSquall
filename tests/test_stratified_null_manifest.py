import pandas as pd
import pytest

from scripts.build_stratified_null_manifest import build_null_windows


def test_stratified_nulls_avoid_case_exclusion_and_separate_windows(tmp_path):
    cases = pd.DataFrame(
        {
            "case_id": ["CASE1"],
            "event_start_utc": ["2005-02-13T09:24:00Z"],
            "vis_below_0p8_min": [89],
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
    event_start = pd.Timestamp("2005-02-13T09:24:00Z")
    event_end = event_start + pd.Timedelta(minutes=89)
    assert not (
        (centers >= event_start - pd.Timedelta(hours=3))
        & (centers <= event_end + pd.Timedelta(hours=4))
    ).any()


def test_stratified_nulls_work_with_cases_without_duration(tmp_path):
    cases = pd.DataFrame({
        "case_id": ["CASE1"],
        "event_start_utc": ["2005-02-13T09:24:00Z"],
    })
    cases_path = tmp_path / "cases.csv"
    cases.to_csv(cases_path, index=False)

    result = build_null_windows(
        cases_path,
        "2005-02-01T00:00:00Z",
        "2005-03-01T00:00:00Z",
        sample_count=2,
        seed=9,
        min_separation_hours=24,
        radars=("KCXX",),
    )
    assert len(result) == 2


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
