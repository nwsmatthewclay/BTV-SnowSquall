"""Accumulate expansion model-feature batches without duplicating object timesteps."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

def merge(current_path: Path, prior_path: Path | None, output_path: Path):
    current=pd.read_csv(current_path)
    frames=[current]
    prior_rows=0
    if prior_path is not None and prior_path.exists():
        prior=pd.read_csv(prior_path)
        prior_rows=len(prior)
        # Legacy expansion batches may contain positive rows created before the
        # supervised-positive gate. Never carry those positives into a new model
        # population. Null/research rows remain eligible for cumulative analysis.
        if "population" in prior.columns and "supervision_class" in prior.columns:
            legacy_positive = prior["population"].eq("verified_case_context") & prior["supervision_class"].ne("supervised_positive")
            dropped = int(legacy_positive.sum())
            if dropped:
                print({"dropped_legacy_positive_rows": dropped})
            prior = prior.loc[~legacy_positive].copy()
        elif "population" in prior.columns:
            legacy_positive = prior["population"].eq("verified_case_context")
            dropped = int(legacy_positive.sum())
            if dropped:
                print({"dropped_legacy_positive_rows": dropped})
            prior = prior.loc[~legacy_positive].copy()
        frames.insert(0, prior)
    combined=pd.concat(frames,ignore_index=True,sort=False)
    if 'row_identity_key' in combined.columns:
        combined=combined.drop_duplicates('row_identity_key',keep='last')
    else:
        keys=[c for c in ['population','case_id','null_id','radar_site','object_id','scan_time_utc'] if c in combined.columns]
        if keys:
            combined=combined.drop_duplicates(keys,keep='last')
    if 'scan_time_utc' in combined.columns:
        combined=combined.sort_values('scan_time_utc',kind='stable')
    output_path.parent.mkdir(parents=True,exist_ok=True)
    combined.to_csv(output_path,index=False)
    print({
        'prior_rows':prior_rows,
        'current_rows':len(current),
        'combined_rows':len(combined),
    })

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--current',required=True)
    p.add_argument('--prior',default=None)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    merge(Path(a.current),Path(a.prior) if a.prior else None,Path(a.output))

if __name__=='__main__':
    main()
