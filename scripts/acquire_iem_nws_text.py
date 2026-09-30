"""Acquire archived BTV NWS text products for snow-squall evidence discovery.

Text matches are supplementary review evidence only. They are never converted
into positive or negative model labels by themselves.
"""
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
    r"(?:\bsnow\s+squall(?:s)?\b|\bwhite[- ]?out\b|"
    r"\bnear[- ]?zero\s+visibility\b|\bnear[- ]?zero\s+vis\b|"
    r"\bblinding\s+snow\b|\bflash\s+freeze\b)",
    re.I,
)
HEADER_RE = re.compile(
    r"^\s*[A-Z]{3,5}\d?\s+[A-Z0-9]{4}\s+(\d{6})\s*$"
)


def fetch_product(pil: str, year: int, month: int) -> str:
    first = pd.Timestamp(year=int(year), month=int(month), day=1)
    last_day = int(first.days_in_month)
    params = {
        "pil": pil,
        "center": "KBTV",
        "sdate": first.strftime("%Y%m%d"),
        "edate": first.replace(day=last_day).strftime("%Y%m%d"),
        "fmt": "text",
        "limit": 10000,
    }
    headers = {"User-Agent": "BTV-SnowSquall research archive builder/1.0"}

    last_error = None
    for attempt, delay in enumerate((0, 2, 5, 10), start=1):
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(
                BASE,
                params=params,
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 4:
                raise
    raise RuntimeError(f"IEM NWS text request failed: {last_error}")


def parse_header_timestamp(value: str, year: int, month: int) -> str | None:
    try:
        day = int(value[:2])
        hour = int(value[2:4])
        minute = int(value[4:6])
        issued = pd.Timestamp(
            year=int(year),
            month=int(month),
            day=day,
            hour=hour,
            minute=minute,
            tz="UTC",
        )
        return issued.isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        return None


def extract_candidates(raw: str, pil: str, year: int, month: int) -> list[dict]:
    lines = raw.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if HEADER_RE.match(line.strip()) and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)

    rows = []
    for block_lines in blocks:
        block = "\n".join(block_lines)
        if not TERMS.search(block):
            continue

        issued = None
        headers = list(HEADER_RE.finditer(block, re.MULTILINE))
        if headers:
            issued = parse_header_timestamp(headers[-1].group(1), year, month)

        rows.append({
            "source": "IEM_NWS_TEXT_ARCHIVE",
            "pil": pil,
            "year": int(year),
            "month": int(month),
            "issued_utc": issued,
            "matched_terms": ",".join(
                sorted({m.group(0).lower() for m in TERMS.finditer(block)})
            ),
            "text": block[-20000:],
        })

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2002)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    errors: list[dict] = []

    for year in range(args.start_year, args.end_year + 1):
        for month in range(1, 13):
            for pil in PRODUCTS:
                print(f"IEM text {year}-{month:02d} {pil}")
                try:
                    raw = fetch_product(pil, year, month)
                    (out / f"{pil}_{year}_{month:02d}.txt").write_text(
                        raw,
                        encoding="utf-8",
                    )
                    rows.extend(extract_candidates(raw, pil, year, month))
                except Exception as exc:
                    errors.append({
                        "year": year,
                        "month": month,
                        "pil": pil,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    })

    pd.DataFrame(rows).to_csv(out / "iem_nws_text_candidates.csv", index=False)
    pd.DataFrame(errors).to_csv(out / "iem_nws_text_errors.csv", index=False)
    summary = {
        "start_year": args.start_year,
        "end_year": args.end_year,
        "months_requested": (args.end_year - args.start_year + 1) * 12,
        "candidate_records": len(rows),
        "download_errors": len(errors),
        "policy": (
            "Text matches are review evidence only; absence is never a "
            "negative label."
        ),
    }
    (out / "iem_nws_text_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
