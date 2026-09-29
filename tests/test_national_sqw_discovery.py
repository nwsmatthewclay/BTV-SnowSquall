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