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

def fetch_product(pil: str, year: int, month: int) -> str:
    params = {
        "pil": pil,
        "center": "KBTV",
        "sdate": f"{year}{month:02d}01",
        "edate": f"{year}{month:02d}{pd.Period(f"{year}-{month:02d}").days_in_month:02d}",
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

def extract_candidates(raw: str, pil: str, year: int, month: int) -> list[dict]:
    lines = raw.splitlines()
    rows = []
    current = []
    for line in lines:
        if current and re.search(r"^\s*[A-Z]{3,5}\d?\s+[A-Z0-9]{4}\s+\d{6}\s*$", line.strip()):
            block = "\n".join(current)
            if TERMS.search(block):
                matches = list(re.finditer(r"(?:^|\n)\s*[A-Z]{3,5}\d?\s+([A-Z0-9]{4})\s+(\d{6})\s*(?:\n|$)", block))
                issued = None
                if matches:
                    m = matches[-1]
                    day_hhmm = m.group(2)
                    try:
                        issued = pd.Timestamp(
                            year=int(year),
                            month=int(month),
                            day=int(day_hhmm[:2]),
                            hour=int(day_hhmm[2:4]),
                            minute=int(day_hhmm[4:6]),
                            tz="UTC",
                        )
                        issued = issued.isoformat().replace("+00:00", "Z")
                    except Exception:
                        issued = None
                rows.append({
                    "source": "IEM_NWS_TEXT_ARCHIVE",
                    "pil": pil,
                    "year": year,
                    "issued_utc": issued,
                    "matched_terms": ",".join(sorted({m.group(0).lower() for m in TERMS.finditer(block)})),
                    "text": block[-20000:],
                })
            current = [line]
            continue
        current.append(line)
    if current:
        block = "\n".join(current)
        if TERMS.search(block):
            match = re.search(r"(?:^|\n)\s*[A-Z]{3,5}\d?\s+[A-Z0-9]{4}\s+(\d{6})\s*(?:\n|$)", block)
            issued = None
            if match:
                day_hhmm = match.group(1)
                try:
                    day = int(day_hhmm[:2])
                    if 1 <= day <= 31:
                        issued = pd.Timestamp(
                            year=int(year), month=int(month), day=day,
                            hour=int(day_hhmm[2:4]), minute=int(day_hhmm[4:6]), tz="UTC"
                        )
                        issued = issued.isoformat().replace("+00:00", "Z")
                except Exception:
                    issued = None
            rows.append({"source":"IEM_NWS_TEXT_ARCHIVE","pil":pil,"year":year,"issued_utc":issued,"matched_terms":",".join(sorted({m.group(0).lower() for m in TERMS.finditer(block)})),"text":block[-20000:]})
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
        for month in range(1, 13):
            for pil in PRODUCTS:
                print(f'IEM text {year}-{month:02d} {pil}')
                try:
                    raw = fetch_product(pil, year, month)
                    (out / f'{pil}_{year}_{month:02d}.txt').write_text(raw, encoding="utf-8")
                    rows.extend(extract_candidates(raw, pil, year, month))
            except Exception as exc:
                errors.append({'year': year, 'pil': pil, 'error_type': type(exc).__name__, 'error_message': str(exc)})
    pd.DataFrame(rows).to_csv(out / 'iem_nws_text_candidates.csv', index=False)
    pd.DataFrame(errors).to_csv(out / 'iem_nws_text_errors.csv', index=False)
    summary = {'start_year': args.start_year, 'end_year': args.end_year, 'months_requested': (args.end_year-args.start_year+1)*12, 'candidate_records': len(rows), 'download_errors': len(errors), 'policy': 'Text matches are review evidence only; absence is never a negative label.'}
    (out / 'iem_nws_text_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()