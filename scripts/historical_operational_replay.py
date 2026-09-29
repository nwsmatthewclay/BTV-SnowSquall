"""Replay archived Level-II scans through the live object-processing path.

The replay processes files chronologically, one scan at a time, through
scripts.process_live_volume.process_volume(). It produces a case-specific
timeline and manifest while preserving the operational information boundary.
"""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from scripts.process_live_volume import process_volume

TIME_RE = re.compile(r"(\d{8})[_-]?(\d{6})")

def scan_time(path: Path) -> datetime:
    match = TIME_RE.search(path.name)
    if not match:
        raise ValueError(f"Cannot determine scan time from filename: {path.name}")
    return datetime.strptime(match.group(1)+match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

def ordered_inputs(input_dir: Path) -> list[Path]:
    files=[p for p in input_dir.rglob("*") if p.is_file() and not p.name.endswith((".part",".tmp"))]
    return sorted(files, key=scan_time)

def replay_case(input_dir: Path, output_dir: Path, state_path: Path, case_id: str, max_scans: int|None=None, resume: bool=False, continue_on_error: bool=False, window_start: datetime|None=None, window_end: datetime|None=None, model_dir: Path|None=None) -> dict:
    scans=ordered_inputs(input_dir)
    if window_start is not None:
        scans=[p for p in scans if scan_time(p) >= window_start]
    if window_end is not None:
        scans=[p for p in scans if scan_time(p) <= window_end]
    if max_scans is not None: scans=scans[:max_scans]
    if not scans: raise RuntimeError(f"No replayable Level-II files found under {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True); state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists() and not resume:
        state_path.unlink()
    records=[]
    errors=[]
    history_jsonl = output_dir / "replay_object_history.jsonl"
    history_csv = output_dir / "replay_object_history.csv"
    for index,source in enumerate(scans,1):
        output=output_dir/f"{index:04d}_{source.stem}.geojson"
        started=datetime.now(timezone.utc)
        try:
            process_volume(
                source,
                state_path,
                output,
                history_jsonl_path=history_jsonl,
                history_csv_path=history_csv,
                model_dir=model_dir,
            )
        except Exception as exc:
            errors.append({"sequence":index,"source_file":source.name,"error_type":type(exc).__name__,"error_message":str(exc)})
            print(f"REPLAY ERROR {source.name}: {type(exc).__name__}: {exc}")
            if not continue_on_error:
                raise
            continue
        finished=datetime.now(timezone.utc)
        payload=json.loads(output.read_text(encoding="utf-8"))
        metadata=payload.get("metadata",{})
        records.append({
            "sequence":index,"source_file":source.name,
            "scan_time_utc":metadata.get("scan_time_utc"),
            "object_count":metadata.get("object_count",0),
            "output_file":str(output.relative_to(output_dir)),
            "processing_seconds":round((finished-started).total_seconds(),3),
            "probability_status":metadata.get("probability_status","not_scored"),
        })
    probability_statuses=[r.get("probability_status","not_scored") for r in records]
    if "scored" in probability_statuses:
        probability_status = "research_candidate_scored"
    elif "model_error" in probability_statuses:
        probability_status = "model_error"
    else:
        probability_status = "not_scored"

    manifest={
        "case_id":case_id,
        "mode":"historical_replay_through_live_processor",
        "probability_status": probability_status,
        "probability_status_counts": {s: probability_statuses.count(s) for s in sorted(set(probability_statuses))},
        "model_directory": str(model_dir) if model_dir else None,
        "future_information_policy":"one_scan_at_a_time",
        "input_directory":str(input_dir),
        "window_start_utc":window_start.isoformat() if window_start else None,
        "window_end_utc":window_end.isoformat() if window_end else None,
        "attempted_scan_count":len(scans),
        "successful_scan_count":len(records),
        "failed_scan_count":len(errors),
        "scan_count":len(records),
        "object_scan_count":sum(r["object_count"] for r in records),
        "first_scan_utc":records[0]["scan_time_utc"] if records else None,
        "last_scan_utc":records[-1]["scan_time_utc"] if records else None,
        "records":records,
        "errors":errors,
    }
    (output_dir/"replay_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--case-id",required=True)
    parser.add_argument("--input-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--state-path",type=Path,default=None)
    parser.add_argument("--max-scans",type=int,default=None)
    parser.add_argument("--resume",action="store_true",help="Resume from an existing replay tracker state instead of resetting it.")
    parser.add_argument("--continue-on-error",action="store_true",help="Record unreadable scans and continue replaying later volumes.")
    parser.add_argument("--window-start-utc",default=None)
    parser.add_argument("--window-end-utc",default=None)
    parser.add_argument("--model-dir",type=Path,default=None,help="Optional learned-model bundle for offline candidate replay; release gating is bypassed only for research replay.")
    args=parser.parse_args()
    state=args.state_path or (args.output_dir/"replay_state.json")
    window_start=datetime.fromisoformat(args.window_start_utc.replace("Z","+00:00")) if args.window_start_utc else None
    window_end=datetime.fromisoformat(args.window_end_utc.replace("Z","+00:00")) if args.window_end_utc else None
    manifest=replay_case(args.input_dir,args.output_dir,state,args.case_id,args.max_scans,args.resume,args.continue_on_error,window_start,window_end,args.model_dir)
    print(json.dumps({k:manifest[k] for k in ("case_id","scan_count","object_scan_count","first_scan_utc","last_scan_utc")},indent=2))

if __name__=="__main__":
    main()
