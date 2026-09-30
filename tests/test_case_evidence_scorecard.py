import pandas as pd

from scripts.build_case_evidence_scorecard import score_row


def test_study_anchor_with_independent_evidence_gets_anchor_tier():
    points,tier,evidence=score_row({
        'verification_class':'study_verified',
        'source_types':'BANACOS_STUDY_2014,IEM_COW_SQW',
        'warning_verified_by_iem':True,
        'lsr_count':2,
        'surface_timing_consistent':True,
        'observation_count':8,
        'radar_scan_count':20,
        'radar_coverage_fraction':1.0,
        'study_case_id':'BTV20020323',
    })
    assert points >= 6
    assert tier == 'A_anchor_supported'
    assert 'study_anchor' in evidence


def test_warning_only_without_independent_support_stays_review_class():
    points,tier,evidence=score_row({
        'verification_class':'warning_only',
        'source_types':'IEM_COW_SQW',
        'warning_verified_by_iem':False,
        'lsr_count':0,
        'surface_timing_consistent':False,
        'observation_count':0,
        'radar_scan_count':0,
        'radar_coverage_fraction':0.0,
    })
    assert points <= 2
    assert tier == 'D_review_only'
