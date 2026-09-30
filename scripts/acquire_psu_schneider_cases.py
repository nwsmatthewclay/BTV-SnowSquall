"""Acquire the public Penn State Schneider et al. (2024) convective-snow case catalog.

The paper links a public Google Sheet containing the identified cases. This utility
downloads the public workbook without private credentials and normalizes case rows
into the repository's discovery schema. It intentionally assigns a non-strong
research verification class; downstream evidence gates decide training eligibility.
"""
from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import pandas as pd
import requests

SPREADSHEET_ID = "1ZMndvESyyDkYuklNGZ--DvKjaTRbJK0rVjJjqQtAlU0"
EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"

def clean_col(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")

def first_col(frame, patterns):
    for col in frame.columns:
        key = clean_col(col)
        if any(re.search(p, key) for p in patterns):
            return col
    return None

def normalize_sheet(frame, sheet_name):
    frame = frame.dropna(how="all").copy()
    if frame.empty:
        return pd.DataFrame()
    frame.columns = [clean_col(c) for c in frame.columns]
    date_col = first_col(frame, [r"^date$", r"event.*date", r"case.*date", r"datetime", r"timestamp", r"time_utc"])
    time_col = first_col(frame, [r"^time$", r"event.*time", r"time_utc"])
    start_col = first_col(frame, [r"event.*start", r"start.*time", r"first.*time"])
    mode_col = first_col(frame, [r"mode", r"type", r"s[1-4]"])
    case_col = first_col(frame, [r"case.*id", r"case.*number", r"event.*id", r"id"])
    if start_col:
        start = pd.to_datetime(frame[start_col], utc=True, errors="coerce", format="mixed")
    elif date_col and time_col and date_col != time_col:
        start = pd.to_datetime(frame[date_col].astype(str)+" "+frame[time_col].astype(str), utc=True, errors="coerce", format="mixed")
    elif date_col:
        start = pd.to_datetime(frame[date_col], utc=True, errors="coerce", format="mixed")
    else:
        start = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    out = pd.DataFrame(index=frame.index)
    out["event_start_utc"] = start
    out["source_case_id"] = frame[case_col].astype(str) if case_col else [f"sheet_{sheet_name}_{i}" for i in frame.index]
    out["research_mode"] = frame[mode_col].astype(str) if mode_col else ""
    out["source_sheet"] = sheet_name
    out["source_row"] = frame.index + 2
    out["narrative"] = frame.astype(str).agg(" | ".join, axis=1).str.slice(0, 2000)
    return out[out["event_start_utc"].notna()].copy()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/derived/psu_schneider_2024")
    parser.add_argument("--url", default=EXPORT_URL)
    args = parser.parse_args()
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    response = requests.get(args.url, timeout=60)
    response.raise_for_status()
    raw = response.content
    (root / "source_workbook.xlsx").write_bytes(raw)
    sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
    parts = []
    for name, frame in sheets.items():
        normalized = normalize_sheet(frame, name)
        if not normalized.empty:
            parts.append(normalized)
    if not parts:
        raise RuntimeError("No timestamp-bearing case rows were found in the public Penn State workbook")
    cases = pd.concat(parts, ignore_index=True)
    cases["event_start_utc"] = pd.to_datetime(cases["event_start_utc"], utc=True)
    cases["candidate_id"] = cases.apply(lambda r: f"PSUCS-{r.event_start_utc:%Y%m%d%H%M}-KCCX-{str(r.source_case_id)}", axis=1)
    cases["case_id"] = cases["candidate_id"]
    cases["candidate_source"] = "PSU_SCHNEIDER_2024"
    cases["verification_class"] = "research_documented_cs"
    cases["verification_status"] = "research_radar_algorithm_manual_review"
    cases["event_type"] = "convective snow research case"
    cases["state"] = "PA"
    cases["county"] = ""
    cases["lat"] = pd.NA
    cases["lon"] = pd.NA
    cases["source"] = "Schneider et al. 2024 / Penn State Data Commons"
    cases["evidence"] = "PSU_SCHNEIDER_2024_radar_algorithm_manual_review"
    cases["source_types"] = "PSU_SCHNEIDER_2024"
    cases["evidence_sources"] = "PSU_SCHNEIDER_2024"
    cases["ncei_explicit_snow_squall"] = False
    cases["lsr_count"] = 0
    cases["source_records"] = 1
    cases["warning_verified_by_iem"] = False
    cases["warning_status"] = ""
    cases["warning_wfo"] = "KCTP"
    cases["coordinate_source"] = "not_assigned_from_study_catalog"
    cases["coordinate_precision"] = "case_coordinate_pending"
    output = root / "psu_schneider_2024_case_catalog.csv"
    cases.to_csv(output, index=False)
    summary = root / "psu_schneider_2024_catalog_summary.json"
    summary.write_text(pd.Series({"source_rows": len(cases), "sheets": list(sheets), "source_url": args.url}).to_json(indent=2)+"\n", encoding="utf-8")
    print(f"Wrote {len(cases)} normalized Penn State research rows to {output}")
    print(cases[["candidate_id","event_start_utc","research_mode","source_sheet"]].head(20).to_string(index=False))

if __name__ == "__main__":
    main()