import pandas as pd
from scripts.label_historical_outcomes import build_labels


def test_missing_event_end_does_not_create_ongoing_labels(tmp_path):
    objects = pd.DataFrame([{
        'case_id': 'CASE1', 'radar_site': 'KCXX', 'object_id': 1,
        'scan_time_utc': '2020-01-01T12:05:00Z',
        'centroid_lat': 44.47, 'centroid_lon': -73.15,
    }])
    cases = pd.DataFrame([{
        'case_id': 'CASE1', 'observing_station': 'KBTV',
        'event_start_utc': '2020-01-01T12:00:00Z',
        'vis_below_0p8_min': float('nan'),
    }])
    cases_path = tmp_path / 'cases.csv'
    cases.to_csv(cases_path, index=False)
    result = build_labels(objects, cases_path)
    assert int(result.loc[0, 'squall_onset_within_15m']) == 0
    assert int(result.loc[0, 'squall_ongoing_within_15m']) == 0
    assert result.loc[0, 'label_status'] == 'event_onset_no_verified_end'
