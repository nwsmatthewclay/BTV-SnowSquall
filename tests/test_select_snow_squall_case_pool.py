import pandas as pd

from scripts.select_snow_squall_case_pool import exclude_protected_candidates, choose_diverse


def test_exclude_protected_candidates(tmp_path):
    candidates = pd.DataFrame({
        "candidate_id": ["A", "B", "C"],
        "event_start_utc": ["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z", "2025-01-03T00:00:00Z"],
    })
    protected = tmp_path / 'protected.csv'
    pd.DataFrame({'case_id':['B']}).to_csv(protected, index=False)
    result = exclude_protected_candidates(candidates, str(protected))
    assert result["candidate_id"].tolist() == ["A", "C"]


def test_choose_diverse_round_robins_years():
    candidates = pd.DataFrame({
        "candidate_id": ["A","B","C","D"],
        "event_start_utc": ["2022-01-01T00:00:00Z","2022-02-01T00:00:00Z","2023-01-01T00:00:00Z","2023-02-01T00:00:00Z"],
        'lsr_count':[1,0,1,0],
        'ncei_explicit_snow_squall':[True,False,True,False],
    })
    result=choose_diverse(candidates,4)
    assert pd.to_datetime(result["event_start_utc"]).dt.year.tolist() == [2022, 2023, 2022, 2023]