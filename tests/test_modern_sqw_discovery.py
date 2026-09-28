import pandas as pd


def test_sqw_candidate_discovery_never_auto_promotes(monkeypatch, tmp_path):
    from scripts import discover_modern_sqw_candidates as discover

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "events": [{
                    "year": 2024, "wfo": "KBTV", "eventid": "0001",
                    "phenomena": "SQ", "significance": "W",
                    "issue": "2024-01-01T12:00:00Z",
                    "expire": "2024-01-01T13:00:00Z",
                    "uri": "https://example.invalid/event"
                }]
            }

    monkeypatch.setattr(discover.requests, "get", lambda *a, **k: Response())
    out = tmp_path / "candidates.csv"
    df = discover.discover([2024], out)
    assert len(df) == 1
    assert df.iloc[0]["review_status"] == "candidate_review_required"
    assert bool(df.iloc[0]["reconstruction_eligible"]) is False


def test_sqw_warning_products_cluster_into_episodes():
    from scripts.cluster_modern_sqw_candidates import cluster
    df = pd.DataFrame([
        {"year": 2024, "event_id": 1, "issue": "2024-01-01T12:00:00Z", "expire": "2024-01-01T13:00:00Z"},
        {"year": 2024, "event_id": 2, "issue": "2024-01-01T12:25:00Z", "expire": "2024-01-01T13:25:00Z"},
        {"year": 2024, "event_id": 3, "issue": "2024-01-01T14:30:00Z", "expire": "2024-01-01T15:00:00Z"},
    ])
    result = cluster(df, gap_minutes=30)
    assert len(result) == 2
    assert result.iloc[0]["warning_count"] == 2
    assert result.iloc[1]["warning_count"] == 1
    assert result.iloc[0]["episode_end"] == pd.Timestamp("2024-01-01T13:25:00Z")
