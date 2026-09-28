"""Audit native NEXRAD Level-II field availability on a sample of volumes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter

from acquisition.level2_reader import read_level2, resolve_fields, volume_metadata


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--limit",type=int,default=40)
    args=parser.parse_args()

    files=[p for p in sorted(Path(args.input).rglob("*")) if p.is_file()]
    if args.limit>0:
        files=files[:args.limit]

    backend=Counter()
    resolved=Counter()
    native=Counter()
    failures=[]

    for path in files:
        try:
            radar=read_level2(path)
            meta=volume_metadata(radar,path)
            backend[meta.get("reader_backend") or "unknown"] += 1
            for field in meta.get("fields",[]):
                native[field]+=1
            fields=resolve_fields(radar)
            for canonical,actual in fields.items():
                if actual:
                    resolved[canonical]+=1
            print(path.name, fields)
        except Exception as exc:
            failures.append({
                "file":str(path),
                "error_type":type(exc).__name__,
                "error":str(exc),
            })

    payload={
        "sampled_files":len(files),
        "successful_reads":sum(backend.values()),
        "failed_reads":len(failures),
        "reader_backends":dict(backend),
        "resolved_field_counts":dict(resolved),
        "native_field_counts":dict(native),
        "failures":failures,
    }
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(payload,indent=2,sort_keys=True))
    if not backend and failures:
        raise SystemExit("No sample volumes could be decoded.")


if __name__=="__main__":
    main()
