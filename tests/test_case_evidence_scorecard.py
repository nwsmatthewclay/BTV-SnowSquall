import pandas as pd

from scripts.build_case_evidence_scorecard import score_row, training_eligibility


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


def test_training_eligibility_requires_surface_and_radar_evidence():
    row={
        'verification_class':'study_verified',
        'surface_timing_consistent':True,
        'observation_count':5,
        'radar_scan_count':10,
        'verification_points':7,
    }
    eligible,reason=training_eligibility(row)
    assert eligible
    assert 'documented_source_plus_surface_timing_plus_radar_reconstruction' == reason


def test_documented_warning_without_surface_timing_is_not_hard_positive():
    row={
        'verification_class':'official_plus_warning_verified',
        'surface_timing_consistent':False,
        'observation_count':8,
        'radar_scan_count':25,
        'verification_points':9,
    }
    eligible,reason=training_eligibility(row)
    assert not eligible
    assert 'surface_timing_missing_or_inconsistent' in reason


def test_string_false_surface_timing_is_not_treated_as_true():
    eligible,reason=training_eligibility({
        'verification_class':'study_verified',
        'surface_timing_consistent':'False',
        'observation_count':10,
        'radar_scan_count':20,
        'verification_points':9,
    })
    assert not eligible
    assert 'surface_timing_missing_or_inconsistent' in reason


def test_mping_diagnostics_are_recorded_without_changing_evidence_points(tmp_path):
    from scripts.build_case_evidence_scorecard import build

    cases = tmp_path / "cases.csv"
    surface = tmp_path / "surface.csv"
    objects = tmp_path / "objects.csv"
    radar = tmp_path / "radar.csv"
    mping = tmp_path / "mping.csv"
    output = tmp_path / "scorecard.csv"

    pd.DataFrame([{
        "case_id": "CASE1",
        "candidate_id": "C1",
        "verification_class": "study_verified",
        "source_types": "STUDY",
        "surface_timing_consistent": True,
        "observation_count": 8,
    }]).to_csv(cases, index=False)
    pd.DataFrame([{"case_id": "CASE1"}]).to_csv(surface, index=False)
    pd.DataFrame([{"case_id": "CASE1"}]).to_csv(objects, index=False)
    pd.DataFrame([{"candidate_id": "C1", "radar_distance_km": 20, "coordinate_precision": "case"}]).to_csv(radar, index=False)
    pd.DataFrame([
        {"case_id": "CASE1", "mping_id": 1, "ptype_bucket": "snow"},
        {"case_id": "CASE1", "mping_id": 2, "ptype_bucket": "mixed"},
    ]).to_csv(mping, index=False)

    build(cases, surface, objects, radar, output, mping)
    result = pd.read_csv(output).iloc[0]

    assert int(result["mping_report_count"]) == 2
    assert int(result["mping_snow_report_count"]) == 1
    assert int(result["mping_mixed_report_count"]) == 1
