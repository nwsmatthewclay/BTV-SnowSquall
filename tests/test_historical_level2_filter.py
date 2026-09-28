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
