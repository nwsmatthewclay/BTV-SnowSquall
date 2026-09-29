import pandas as pd


def test_candidate_reconstruction_manifest_keeps_both_radars(tmp_path):
    from scripts.build_modern_candidate_reconstruction_manifest import build
    cohort=tmp_path/'cohort.csv'
    preflight=tmp_path/'preflight.csv'
    out=tmp_path/'out.csv'
    pd.DataFrame([{
        'case_id':'MODERN_A','episode_id':'SQEA','year':2024,
        'selection_basis':'one_hash_selected_episode_per_year'
    }]).to_csv(cohort,index=False)
    pd.DataFrame([
        {'case_id':'MODERN_A','episode_id':'SQEA','year':2024,'episode_start_utc':'2024-01-01T00:00:00Z','episode_end_utc':'2024-01-01T01:00:00Z','window_start_utc':'2023-12-31T23:30:00Z','window_end_utc':'2024-01-01T01:30:00Z','radar_site':'KCXX','level2_volume_count':20,'first_volume_utc':'2023-12-31T23:32:00Z','last_volume_utc':'2024-01-01T01:28:00Z','archive_status':'available'},
        {'case_id':'MODERN_A','episode_id':'SQEA','year':2024,'episode_start_utc':'2024-01-01T00:00:00Z','episode_end_utc':'2024-01-01T01:00:00Z','window_start_utc':'2023-12-31T23:30:00Z','window_end_utc':'2024-01-01T01:30:00Z','radar_site':'KTYX','level2_volume_count':18,'first_volume_utc':'2023-12-31T23:33:00Z','last_volume_utc':'2024-01-01T01:27:00Z','archive_status':'available'},
    ]).to_csv(preflight,index=False)
    result=build(cohort,preflight,out)
    assert set(result['radar_site'])=={'KCXX','KTYX'}
    assert (result['training_eligible']==False).all()
    assert (result['truth_status']=='not_established').all()
    assert (result['probability_status']=='not_scored').all()
