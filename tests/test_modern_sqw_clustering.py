import pandas as pd


def test_sqw_episode_clustering_merges_overlap_and_midnight():
    from scripts.cluster_modern_sqw_candidates import cluster
    df=pd.DataFrame([
        {"year":2019,"event_id":1,"issue":"2019-12-11T23:50:00Z","expire":"2019-12-12T00:40:00Z"},
        {"year":2019,"event_id":2,"issue":"2019-12-12T00:35:00Z","expire":"2019-12-12T01:20:00Z"},
        {"year":2019,"event_id":3,"issue":"2019-12-12T02:00:00Z","expire":"2019-12-12T02:30:00Z"},
        {"year":2019,"event_id":4,"issue":"2019-12-12T04:00:00Z","expire":"2019-12-12T04:30:00Z"},
    ])
    out=cluster(df,gap_minutes=30)
    assert len(out)==3
    assert out.iloc[0]["warning_count"]==2
    assert out.iloc[0]["episode_id"].startswith("SQE20191211T2350Z")
    assert out.iloc[1]["warning_count"]==1
