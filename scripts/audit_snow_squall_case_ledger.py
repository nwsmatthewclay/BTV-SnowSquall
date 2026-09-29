"""Audit the snow-squall discovery ledger before expensive radar acquisition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ALLOWED_SOURCES = {"NCEI_STORM_EVENTS", "NCEI_STORM_EVENTS_SCREENING", "SWDI_PLSR", "IEM_COW_SQW"}
ALLOWED_CLASSES = {
    "official_documented", "official_plus_independent_report", "official_plus_warning", "official_plus_study",
    "official_plus_warning_and_report", "official_plus_warning_verified", "official_study_warning_verified", "study_warning_verified", "study_verified", "warning_verified",
    "warning_only", "warning_plus_report", "unverified_report_only"
}


def audit(cases_path: Path, radar_path: Path, start_year: int, end_year: int):
    cases = pd.read_csv(cases_path)
    radar = pd.read_csv(radar_path)
    required = {"candidate_id", "event_start_utc", "verification_class", "candidate_source", "lat", "lon"}
    missing = required - set(cases.columns)
    if missing:
        raise ValueError(f"case ledger missing columns: {sorted(missing)}")
    parsed = pd.to_datetime(cases["event_start_utc"], utc=True, errors="coerce", format="mixed")
    bad_time = parsed.isna()
    year_bad = parsed.dt.year.notna() & ~parsed.dt.year.between(start_year, end_year)
    bad_id = cases["candidate_id"].astype(str).eq("") | cases["candidate_id"].duplicated()
    bad_source = ~cases["candidate_source"].isin(ALLOWED_SOURCES)
    bad_class = ~cases["verification_class"].isin(ALLOWED_CLASSES)
    lat = pd.to_numeric(cases["lat"], errors="coerce")
    lon = pd.to_numeric(cases["lon"], errors="coerce")
    bad_geo = lat.isna() | lon.isna() | ~lat.between(40, 48) | ~lon.between(-80, -67)
    if "event_end_utc" in cases.columns:
        end = pd.to_datetime(
            cases["event_end_utc"].astype("string"),
            utc=True,
            errors="coerce",
            format="mixed",
        )
    else:
        end = pd.Series(pd.NaT, index=cases.index, dtype="datetime64[ns, UTC]")
    parsed = pd.to_datetime(
        cases["event_start_utc"].astype("string"),
        utc=True,
        errors="coerce",
        format="mixed",
    )
    bad_interval = end.notna() & parsed.notna() & (end < parsed)
    if not radar.empty:
        if not set(radar["candidate_id"].astype(str)).issubset(set(cases["candidate_id"].astype(str))):
            raise ValueError("radar manifest contains unknown candidate IDs")
        if radar["candidate_id"].astype(str).duplicated().any():
            raise ValueError("radar manifest contains duplicate candidate IDs")
    errors = {
        "bad_time": int(bad_time.sum()),
        "out_of_range_year": int(year_bad.sum()),
        "bad_candidate_id": int(bad_id.sum()),
        "bad_source": int(bad_source.sum()),
        "bad_verification_class": int(bad_class.sum()),
        "bad_geo": int(bad_geo.sum()),
        "bad_event_interval": int(bad_interval.sum()),
    }
    errors["total_errors"] = sum(errors.values())
    if errors["total_errors"]:
        raise ValueError(json.dumps(errors, indent=2))
    return {
        "cases": int(len(cases)),
        "radar_manifest_rows": int(len(radar)),
        "verification_classes": cases["verification_class"].value_counts().to_dict(),
        "candidate_sources": cases["candidate_source"].value_counts().to_dict(),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--radar", required=True)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = audit(Path(args.cases), Path(args.radar), args.start_year, args.end_year)
    Path(args.output).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
