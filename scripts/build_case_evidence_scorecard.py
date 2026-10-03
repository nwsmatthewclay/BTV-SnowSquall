"""Build an auditable snow-squall case evidence scorecard."""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

STRONG = {
    "official_documented", "official_plus_independent_report", "official_plus_warning",
    "official_plus_warning_and_report", "official_plus_warning_verified",
    "official_study_warning_verified", "official_plus_study", "study_verified",
    "study_warning_verified",
}

def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    text = str(value).strip().lower()
    if text in {'true','1','yes','y','t'}:
        return True
    if text in {'false','0','no','n','f',''}:
        return False
    return False

def collapse_duplicate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the first copy of duplicate column names from joined evidence."""
    return frame.loc[:, ~frame.columns.duplicated()].copy()


def num(value, default=0.0):
    try:
        value=float(value)
        return value if pd.notna(value) else default
    except (TypeError, ValueError):
        return default

def score_row(row):
    evidence=[]
    points=0
    cls=str(row.get('verification_class') or '')
    if cls in STRONG:
        points += 4; evidence.append('documented_source')
    if 'IEM_COW_SQW' in str(row.get('source_types') or ''):
        points += 1; evidence.append('snow_squall_warning')
    if as_bool(row.get('warning_verified_by_iem')):
        points += 2; evidence.append('iem_warning_verification')
    if num(row.get('lsr_count')) > 0:
        points += 1; evidence.append('independent_lsr')
    if num(row.get('nws_text_evidence_count')) > 0:
        points += 1; evidence.append('nws_text')
    if as_bool(row.get('surface_timing_consistent')):
        points += 2; evidence.append('surface_timing')
    if num(row.get('observation_count')) > 0:
        points += 1; evidence.append('surface_observations')
    if num(row.get('radar_scan_count')) > 0:
        points += 2; evidence.append('radar_reconstruction')
    if num(row.get('radar_coverage_fraction')) >= 0.75:
        points += 1; evidence.append('radar_coverage_ge_75pct')
    study_id = row.get('study_case_id')
    study_id_text = '' if study_id is None or pd.isna(study_id) else str(study_id).strip()
    if study_id_text and study_id_text.lower() not in {'nan','<na>'}:
        points += 3; evidence.append('study_anchor')

    # Evidence tiers are descriptive promotion queues. They are not truth labels.
    if cls in {'study_verified','official_plus_study','study_warning_verified','official_study_warning_verified'} and points >= 6:
        tier='A_anchor_supported'
    elif points >= 7:
        tier='A_multi_source'
    elif points >= 5:
        tier='B_multi_evidence'
    elif points >= 3:
        tier='C_partial_evidence'
    else:
        tier='D_review_only'
    return points,tier,','.join(evidence)

def training_eligibility(row):
    """Return (eligible, reason) for the initial supervised positive population.

    A case can be retained as a documented/review candidate without being used
    as a hard supervised positive. The first supervised population requires:
    (1) documented/study evidence, (2) observed surface timing, (3) at least
    one reconstructed radar object scan, and (4) at least six evidence points.
    """
    cls=str(row.get('verification_class') or '')
    documented = cls in STRONG
    surface_ok = as_bool(row.get('surface_timing_consistent')) and num(row.get('observation_count')) > 0
    radar_ok = num(row.get('radar_scan_count')) > 0
    points = num(row.get('verification_points'))
    if documented and surface_ok and radar_ok and points >= 6:
        return True, 'documented_source_plus_surface_timing_plus_radar_reconstruction'
    reasons=[]
    if not documented:
        reasons.append('no_strong_documented_source')
    if not surface_ok:
        reasons.append('surface_timing_missing_or_inconsistent')
    if not radar_ok:
        reasons.append('radar_reconstruction_missing')
    if points < 6:
        reasons.append('insufficient_evidence_points')
    return False, ';'.join(reasons)


def build(cases_path, surface_path, objects_path, radar_path, output_path, mping_path=None):
    cases=pd.read_csv(cases_path)
    for path in [surface_path, objects_path, radar_path]:
        if path and not Path(path).exists():
            raise FileNotFoundError(path)
    if surface_path:
        s=pd.read_csv(surface_path)
        s_cols=[c for c in ['case_id','surface_timing_consistent','observation_count','minimum_visibility_m','maximum_gust_kt'] if c in s.columns]
        cases=cases.merge(s[s_cols].drop_duplicates('case_id'),on='case_id',how='left')
    if objects_path:
        o=pd.read_csv(objects_path)
        if 'case_id' in o.columns:
            detected=o.dropna(subset=['case_id']).copy()
            if 'context_only' in detected.columns:
                detected=detected[pd.to_numeric(detected['context_only'],errors='coerce').fillna(0).eq(0)]
            counts=detected.groupby('case_id').size().rename('radar_scan_count')
            cases=cases.merge(counts,on='case_id',how='left')
    if radar_path:
        r=pd.read_csv(radar_path)
        r_cols=[c for c in ['candidate_id','radar_distance_km','coordinate_precision'] if c in r.columns]
        if r_cols and 'candidate_id' in r.columns:
            cases=cases.merge(r[r_cols].drop_duplicates('candidate_id'),left_on='candidate_id',right_on='candidate_id',how='left')
    if mping_path and Path(mping_path).exists():
        m=pd.read_csv(mping_path)
        # Some acquisition joins can leave duplicate column names. Collapse duplicate
        # names before grouping so pandas receives a one-dimensional case_id key.
        m = collapse_duplicate_columns(m)
        if 'case_id' in m.columns:
            counts=m.groupby('case_id').size().rename('mping_report_count')
            cases=cases.merge(counts,on='case_id',how='left')
            if 'ptype_bucket' in m.columns:
                pivot=m.pivot_table(index='case_id',columns='ptype_bucket',values='mping_id' if 'mping_id' in m.columns else 'case_id',aggfunc='count',fill_value=0)
                rename={
                    'snow':'mping_snow_report_count',
                    'mixed':'mping_mixed_report_count',
                    'freezing_rain':'mping_freezing_rain_report_count',
                    'rain':'mping_rain_report_count',
                    'other':'mping_other_report_count',
                }
                pivot=pivot.rename(columns=rename).reset_index()
                cases=cases.merge(pivot,on='case_id',how='left')
    cases['radar_scan_count']=cases.get('radar_scan_count',pd.Series(0,index=cases.index)).fillna(0)
    for col in ('mping_report_count','mping_snow_report_count','mping_mixed_report_count','mping_freezing_rain_report_count','mping_rain_report_count','mping_other_report_count'):
        cases[col]=cases.get(col,pd.Series(0,index=cases.index)).fillna(0).astype(int)
    cases['verification_points'],cases['verification_tier'],cases['verification_evidence']=zip(*cases.apply(score_row,axis=1))
    elig = cases.apply(training_eligibility, axis=1, result_type='expand')
    cases['training_eligible'] = elig[0].astype(bool)
    cases['training_exclusion_reason'] = elig[1]
    cases['verification_policy']='descriptive_evidence_promotion_queue_v1'
    cases.to_csv(output_path,index=False)
    print('Case evidence scorecard:',len(cases))
    print(cases['verification_tier'].value_counts(dropna=False).to_string())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cases',required=True)
    p.add_argument('--surface',required=True)
    p.add_argument('--objects',required=True)
    p.add_argument('--radar',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--mping', default=None, help='Optional historical mPING evidence CSV; diagnostics only.')
    a=p.parse_args()
    build(Path(a.cases),Path(a.surface),Path(a.objects),Path(a.radar),Path(a.output),Path(a.mping) if a.mping else None)

if __name__=='__main__':
    main()