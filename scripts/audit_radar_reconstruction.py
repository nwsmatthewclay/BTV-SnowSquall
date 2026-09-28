"""Audit reconstructed Level-II object tables and volume-error logs.

The audit distinguishes successful volumes that produced objects, successful
volumes with zero candidates, and failed volumes. A configurable failure-rate
gate prevents materially incomplete reconstruction from passing as clean.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import pandas as pd

def input_files(input_root:Path):
    return [p for p in input_root.rglob("*") if p.is_file() and not p.name.endswith((".part",".tmp"))]

def audit(objects_path:Path,errors_path:Path,input_root:Path|None=None,max_failure_rate:float|None=None)->dict:
    objects=pd.read_csv(objects_path)
    errors=pd.read_csv(errors_path)
    required={"source_file","reader_backend"}
    missing=required-set(objects.columns)
    if missing: raise ValueError(f"Object reconstruction missing required columns: {sorted(missing)}")
    object_volume_counts=objects.groupby("reader_backend",dropna=False)["source_file"].nunique()
    failed=set(errors["source_file"].dropna().astype(str)) if "source_file" in errors else set()
    observed=set(objects["source_file"].dropna().astype(str))
    expected_files={str(p) for p in input_files(input_root)} if input_root is not None else set()
    if expected_files:
        known_failed=failed&expected_files
        successful=expected_files-known_failed
        expected_count=len(expected_files)
        processed_count=len(successful)
        zero_object_count=len(successful-observed)
        failure_rate=len(known_failed)/expected_count if expected_count else 0.0
    else:
        expected_count=processed_count=zero_object_count=None
        failure_rate=None
    summary={
        "object_records":int(len(objects)),
        "volumes_with_candidate_objects":int(len(observed)),
        "failed_volumes":int(len(failed)),
        "reader_backend_volume_counts":{str(k):int(v) for k,v in object_volume_counts.items()},
        "error_type_counts":errors["error_type"].value_counts(dropna=False).to_dict() if "error_type" in errors.columns else {},
        "error_files_with_object_records":int(len(failed&observed)),
        "objects_with_missing_reader_backend":int(objects["reader_backend"].isna().sum()),
        "expected_input_volumes":expected_count,
        "successful_input_volumes":processed_count,
        "successful_zero_object_volumes":zero_object_count,
        "failure_rate":round(failure_rate,6) if failure_rate is not None else None,
    }
    if failed&observed:
        raise ValueError(f"{len(failed&observed)} failed source files also appear in the object table")
    if max_failure_rate is not None and failure_rate is not None and failure_rate>max_failure_rate:
        raise ValueError(f"Radar reconstruction failure rate {failure_rate:.1%} exceeds configured maximum {max_failure_rate:.1%}")
    return summary

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("objects_csv")
    parser.add_argument("--errors",required=True)
    parser.add_argument("--report",required=True)
    parser.add_argument("--input-root")
    parser.add_argument("--max-failure-rate",type=float,default=0.20)
    args=parser.parse_args()
    summary=audit(Path(args.objects_csv),Path(args.errors),Path(args.input_root) if args.input_root else None,args.max_failure_rate)
    report=Path(args.report); report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))

if __name__=="__main__":
    main()
