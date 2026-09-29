def test_candidate_inventory_enforces_non_scoring_boundary(tmp_path):
    from scripts.build_modern_candidate_inventory import build
    import json
    import pandas as pd

    manifest = tmp_path / "manifest.csv"
    replay = tmp_path / "replay"
    surface = tmp_path / "surface"
    mrms = tmp_path / "mrms"
    replay_case = replay / "CASE1" / "KCXX"
    replay_case.mkdir(parents=True)
    surface_station = surface / "KBTV"
    surface_station.mkdir(parents=True)
    (mrms / "CASE1" / "KCXX").mkdir(parents=True)

    pd.DataFrame([{
        "case_id":"CASE1","episode_id":"SQE1","year":2024,
        "episode_start_utc":"2024-01-01T00:00:00Z",
        "episode_end_utc":"2024-01-01T01:00:00Z",
        "window_start_utc":"2023-12-31T23:30:00Z",
        "window_end_utc":"2024-01-01T01:30:00Z",
        "radar_site":"KCXX","level2_volume_count":1,
        "truth_status":"not_established","probability_status":"not_scored"
    }]).to_csv(manifest,index=False)

    (replay_case / "replay_manifest.json").write_text(json.dumps({
        "attempted_scan_count":1,"successful_scan_count":1,"failed_scan_count":0,
        "object_scan_count":2
    }),encoding="utf-8")

    pd.DataFrame([{"station":"KBTV"}]).to_csv(surface_station/"CASE1.csv",index=False)

    payload=build(
        manifest,replay,surface,mrms,
        tmp_path/"inventory.json",tmp_path/"inventory.csv"
    )
    assert payload["training_eligible"] is False
    assert payload["scoring_status"] == "not_scored"
    assert payload["records"][0]["training_eligible"] is False
