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
