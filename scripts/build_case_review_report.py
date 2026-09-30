"""Render the unified snow-squall case ledger as a compact human-review report."""
from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd

def build(cases_path: Path, summary_path: Path, output: Path):
    cases = pd.read_csv(cases_path)
    summary = summary_path.read_text(encoding='utf-8') if summary_path.exists() else '{}'
    cols = [
        "candidate_id","episode_id","event_start_utc","event_end_utc","state","county",
        "verification_class","verification_status","candidate_source","source_types",
        "evidence_sources","event_type","lsr_count","warning_verified_by_iem",
        "ncei_explicit_snow_squall","radar_site","radar_distance_km","coordinate_precision",
        "narrative","text_matched_terms"
    ]
    present=[c for c in cols if c in cases.columns]
    table=cases[present].copy()
    for col in table.columns:
        table[col]=table[col].fillna('')
    table=table.sort_values(['event_start_utc','verification_class'],kind='stable')
    headers=''.join(f'<th>{html.escape(str(c))}</th>' for c in present)
    body=[]
    for _,row in table.iterrows():
        cells="".join(f"<td>{html.escape(str(row[c]))}</td>" for c in present)
        body.append(f'<tr>{cells}</tr>')
    page=f'''<!doctype html>
<html><head><meta charset="utf-8"><title>BTV Snow Squall Case Review</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;background:#111820;color:#e7eef5}}
h1{{margin-bottom:6px}}.meta{{color:#9fb0bf;font-size:13px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #30404e;padding:6px;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#1b2935}}tr:nth-child(even){{background:#151f28}}
td:last-child{{max-width:700px;white-space:pre-wrap}}</style></head>
<body><h1>BTV Snow Squall Case Review</h1>
<div class="meta">Candidates: {len(table)}<br>Ledger summary JSON: {html.escape(summary[:4000])}</div>
<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table></body></html>'''
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(page,encoding='utf-8')
    print(f'Wrote {output} with {len(table)} candidate rows')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cases',required=True)
    p.add_argument('--summary',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    build(Path(a.cases),Path(a.summary),Path(a.output))

if __name__=='__main__':
    main()
