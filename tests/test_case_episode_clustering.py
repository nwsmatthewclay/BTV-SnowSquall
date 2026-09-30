import pandas as pd

from scripts.merge_snow_squall_case_sources import assign_episode_ids


def test_adjacent_county_records_share_physical_episode():
    frame = pd.DataFrame([
        {"candidate_id":"A","candidate_source":"NCEI_STORM_EVENTS","event_start_utc":"2026-01-01T15:00:00Z","lat":44.2,"lon":-73.1},
        {"candidate_id":"B","candidate_source":"NCEI_STORM_EVENTS","event_start_utc":"2026-01-01T15:25:00Z","lat":44.4,"lon":-73.2},
    ])
    result = assign_episode_ids(frame)
    assert result["episode_id"].nunique() == 1


def test_far_apart_records_are_separate_episodes():
    frame = pd.DataFrame([
        {"candidate_id":"A","candidate_source":"NCEI_STORM_EVENTS","event_start_utc":"2026-01-01T15:00:00Z","lat":44.2,"lon":-73.1},
        {"candidate_id":"B","candidate_source":"NCEI_STORM_EVENTS","event_start_utc":"2026-01-01T15:25:00Z","lat":46.5,"lon":-70.1},
    ])
    result = assign_episode_ids(frame)
    assert result["episode_id"].nunique() == 2


def test_cross_source_reconciliation_uses_tighter_linkage():
    frame = pd.DataFrame([
        {"candidate_id":"A","candidate_source":"NCEI_STORM_EVENTS","event_start_utc":"2026-01-01T15:00:00Z","lat":44.2,"lon":-73.1},
        {"candidate_id":"B","candidate_source":"IEM_LSR","event_start_utc":"2026-01-01T15:40:00Z","lat":44.8,"lon":-73.4},
    ])
    result = assign_episode_ids(frame)
    assert result["episode_id"].nunique() == 1
