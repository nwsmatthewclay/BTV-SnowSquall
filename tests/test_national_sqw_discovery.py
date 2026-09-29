from scripts.discover_national_sqw_cases import case_key, month_ranges


def test_case_key_is_stable():
    props={
        'issue':'2025-01-28T14:00:00+00:00',
        'wfo':'BTV',
        'eventid':'12',
    }
    assert case_key(props)==case_key(dict(props))


def test_month_ranges_respect_bounds():
    ranges=list(month_ranges(2025,2025))
    assert len(ranges)==12
    assert ranges[0][0].strftime('%Y-%m-%d')=='2025-01-01'
    assert ranges[-1][0].strftime('%Y-%m-%d')=='2025-12-01'
    assert ranges[-1][1].strftime('%Y-%m-%d')=='2025-12-31'

def test_cluster_does_not_use_series_dt_accessor():
    import pandas as pd
    from scripts.discover_national_sqw_cases import cluster
    frame = pd.DataFrame([
        {
            "case_id": "A",
            "warning_issue_utc": "2025-01-01T12:00:00Z",
            "warning_expire_utc": "2025-01-01T12:30:00Z",
            "wfo": "BTV",
            "lat": 44.5,
            "lon": -73.2,
            "iem_verified": True,
            "first_verifying_lsr_lead_min": 5.0,
            "verifying_lsr_count": 1,
            "all_in_buffer_lsr_count": 1,
        },
        {
            "case_id": "B",
            "warning_issue_utc": "2025-01-01T12:20:00Z",
            "warning_expire_utc": "2025-01-01T12:50:00Z",
            "wfo": "BTV",
            "lat": 44.52,
            "lon": -73.18,
            "iem_verified": False,
            "first_verifying_lsr_lead_min": None,
            "verifying_lsr_count": 0,
            "all_in_buffer_lsr_count": 0,
        },
    ])
    out = cluster(frame)
    assert len(out) == 1
    assert int(out.iloc[0]["warning_count"]) == 2
