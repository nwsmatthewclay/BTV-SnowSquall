import pandas as pd


def test_modern_preflight_excludes_mdm_and_adds_both_radars(monkeypatch, tmp_path):
    from scripts import preflight_modern_reconstruction_cohort as preflight

    class FakePaginator:
        def paginate(self, **kwargs):
            return [{
                "Contents": [
                    {"Key": "2024/01/01/KCXX/KCXX20240101_120000_V06"},
                    {"Key": "2024/01/01/KCXX/KCXX20240101_120500_V06_MDM"},
                ]
            }]

    class FakeS3:
        def get_paginator(self, name):
            return FakePaginator()

    monkeypatch.setattr(preflight, "client", lambda: FakeS3())

    cohort = tmp_path / "cohort.csv"
    output = tmp_path / "preflight.csv"
    pd.DataFrame([{
        "case_id":"MODERN_SQE20240101T1200Z",
        "episode_id":"SQE20240101T1200Z",
        "year":2024,
        "episode_start":"2024-01-01T12:00:00Z",
        "episode_end":"2024-01-01T13:00:00Z",
        "selection_basis":"one_hash_selected_episode_per_year",
    }]).to_csv(cohort, index=False)

    result = preflight.build(cohort, output)
    assert set(result["radar_site"]) == {"KCXX", "KTYX"}
    assert (result["level2_volume_count"] == 1).all()
    assert (result["training_eligible"] == False).all()
