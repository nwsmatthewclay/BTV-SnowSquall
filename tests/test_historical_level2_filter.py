from acquisition.historical_level2 import filter_manifest_rows

def test_manifest_filter_selects_requested_case_and_radar():
    rows=[
      {'case_id':'CASE1','window_id':'W1_KCXX','radar_site':'KCXX'},
      {'case_id':'CASE1','window_id':'W1_KTYX','radar_site':'KTYX'},
      {'case_id':'CASE2','window_id':'W2_KCXX','radar_site':'KCXX'},
    ]
    result=filter_manifest_rows(rows,case_id='CASE1',radar_site='KCXX')
    assert result==[rows[0]]

def test_mdm_maintenance_file_is_not_treated_as_radar_volume():
    from acquisition.historical_level2 import key_time
    assert key_time('KCXX20181121_165948_V06_MDM') is None


def test_prepare_downloads_deduplicates_overlapping_windows(monkeypatch):
    from acquisition import historical_level2 as level2

    calls = []

    def fake_list(client, radar, day):
        calls.append((radar, day.date()))
        return [
            "2020/01/02/KCXX/KCXX20200102_120000_V06",
            "2020/01/02/KCXX/KCXX20200102_121000_V06",
            "2020/01/02/KCXX/KCXX20200102_123000_V06",
        ]

    monkeypatch.setattr(level2, "list_volume_keys", fake_list)
    rows = [
        {
            "case_id": "A",
            "radar_site": "KCXX",
            "window_start_utc": "2020-01-02T11:55:00Z",
            "window_end_utc": "2020-01-02T12:15:00Z",
        },
        {
            "case_id": "B",
            "radar_site": "KCXX",
            "window_start_utc": "2020-01-02T12:05:00Z",
            "window_end_utc": "2020-01-02T12:35:00Z",
        },
    ]

    targets, row_matches, listing_count = level2._prepare_downloads(object(), rows)

    assert calls == [("KCXX", __import__("datetime").date(2020, 1, 2))]
    assert listing_count == 1
    assert row_matches == {"A": 2, "B": 2}
    assert len(targets) == 3
