import pandas as pd


def test_modern_reconstruction_cohort_is_deterministic_and_year_covered(tmp_path):
    from scripts.build_modern_reconstruction_cohort import build

    frame = tmp_path / "frame.csv"
    existing = tmp_path / "existing.csv"
    output = tmp_path / "cohort.csv"

    pd.DataFrame([
        {"episode_id":"A2019","episode_start":"2019-01-01T00:00:00Z","episode_end":"2019-01-01T01:00:00Z","year":2019},
        {"episode_id":"B2019","episode_start":"2019-02-01T00:00:00Z","episode_end":"2019-02-01T01:00:00Z","year":2019},
        {"episode_id":"A2020","episode_start":"2020-01-01T00:00:00Z","episode_end":"2020-01-01T01:00:00Z","year":2020},
        {"episode_id":"B2020","episode_start":"2020-02-01T00:00:00Z","episode_end":"2020-02-01T01:00:00Z","year":2020},
    ]).to_csv(frame,index=False)
    pd.DataFrame([{"case_id":"BTV201918"}]).to_csv(existing,index=False)

    result = build(frame, existing, output)
    assert "BTV201918" in set(result["case_id"])
    selected = result[result["selection_basis"] == "one_hash_selected_episode_per_year"]
    assert set(selected["year"]) == {2019, 2020}
    assert selected.groupby("year").size().to_dict() == {2019:1, 2020:1}
    assert (selected["training_eligible"] == False).all()
