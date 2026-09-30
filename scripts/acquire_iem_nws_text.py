"""Acquire archived NWS BTV text products for snow-squall evidence discovery."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
PRODUCTS = ("PNSBTV", "SPSBTV", "AFDBTV")
TERMS = re.compile(
    r"(?:\bsnow\s+squall(?:s)?\b|\bwhite[- ]?out\b|\bnear[- ]?zero\s+visibility\b|\bnear[- ]?zero\s+vis\b|\bblinding\s+snow\b|\bflash\s+freeze\b)",
    re.I,
)

def fetch_product(pil: str, year: int) -> str:
    params = {
        "pil": pil,
        "center": "KBTV",
        "sdate": f"{year}0101",
        "edate": f"{year + 1}0101",
        "fmt": "text",
        "limit": 10000,
    }
    headers = {"User-Agent": "BTV-SnowSquall research archive builder/1.0"}
    last = None
    for attempt, delay in enumerate((0, 2, 5, 10), start=1):
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(BASE, params=params, headers=headers, timeout=120)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last = exc
            if attempt == 4:
                raise
    raise RuntimeError(str(last))

def extract_candidates(raw: str, pil: str, year: int) -> list[dict]:
    lines = raw.splitlines()
    rows = []
    current = []
    for line in lines:
        if current and line.strip().startswith("$$") and TERMS.search("\n".join(current)):
            rows.append({
                "source": "IEM_NWS_TEXT_ARCHIVE",
                "pil": pil,
                "year": year,
                "matched_terms": ",".join(sorted({m.group(0).lower() for m in TERMS.finditer("\n".join(current))})),
                "text": "\n".join(current)[-20000:],
            })
            current = []
            continue
        current.append(line)
    if current and TERMS.search("\n".join(current)):
        rows.append({
            "source": "IEM_NWS_TEXT_ARCHIVE",
            "pil": pil,
            "year": year,
            "matched_terms": ",".join(sorted({m.group(0).lower() for m in TERMS.finditer("\n".join(current))})),
            "text": "\n".join(current)[-20000:],
        })
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-year', type=int, default=2002)
    parser.add_argument('--end-year', type=int, default=2026)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    errors = []
    for year in range(args.start_year, args.end_year + 1):
        for pil in PRODUCTS:
            print(f'IEM text {year} {pil}')
            try:
                raw = fetch_product(pil, year)
                (out / f'{pil}_{year}.txt').write_text(raw, encoding='utf-8', errors='replace')
                rows.extend(extract_candidates(raw, pil, year))
            except Exception as exc:
                errors.append({'year': year, 'pil': pil, 'error_type': type(exc).__name__, 'error_message': str(exc)})
    pd.DataFrame(rows).to_csv(out / 'iem_nws_text_candidates.csv', index=False)
    pd.DataFrame(errors).to_csv(out / 'iem_nws_text_errors.csv', index=False)
    summary = {'start_year': args.start_year, 'end_year': args.end_year, 'candidate_records': len(rows), 'download_errors': len(errors), 'policy': 'Text matches are review evidence only; absence is never a negative label.'}
    (out / 'iem_nws_text_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()