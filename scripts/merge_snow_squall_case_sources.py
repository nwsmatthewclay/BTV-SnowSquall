"""Merge Snow Squall Warning discovery and IEM LSR evidence into one case ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

RADARS = {
    "KCXX": (44.511, -73.166),
    "KTYX": (43.756, -75.680),
}

STRONG_CLASSES = {
    "official_documented",
    "official_plus_independent_report",
    "official_plus_warning",
    "official_plus_warning_and_report",
    "official_plus_warning_verified",
    "official_study_warning_verified",
    "official_plus_study",
    "study_verified",
    "study_warning_verified",
    "warning_verified",
}

def distance_km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    if None in (lat1, lon1, lat2, lon2):
        return None
    p1 = radians(float(lat1))
    p2 = radians(float(lat2))
    dp = radians(float(lat2) - float(lat1))
    dl = radians(float(lon2) - float(lon1))
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371.0 * 2.0 * asin(min(1.0, sqrt(a)))

def stable_id(timestamp, lat, lon):
    raw = f"IEMCL|{timestamp.isoformat()}|{lat}|{lon}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"SSQ{timestamp:%Y%m%d%H%M}_{digest}"

def canonical_class(source_types, warning_verified=False):
    has_ncei = "NCEI_STORM_EVENTS" in source_types
    has_study = "BANACOS_STUDY_2014" in source_types
    has_report = bool({"IEM_LSR", "SWDI_PLSR"} & source_types)
    has_sqw = "IEM_COW_SQW" in source_types
    if has_ncei and has_study:
        return "official_plus_study"
    if has_study and has_sqw and warning_verified:
        return "study_warning_verified"
    if has_study:
        return "study_verified"
    if has_ncei and has_sqw and warning_verified:
        return "official_plus_warning_verified"
    if has_ncei and has_report and has_sqw:
        return "official_plus_warning_and_report"
    if has_ncei and has_sqw:
        return "official_plus_warning"
    if has_ncei and has_report:
        return "official_plus_independent_report"
    if has_ncei:
        return "official_documented"
    if has_sqw and warning_verified:
        return "warning_verified"
    if has_sqw and has_report:
        return "warning_plus_report"
    if has_sqw:
        return "warning_only"
    return "unverified_report_only"

def find_match(records, timestamp, lat, lon):
    best = None
    for index, record in enumerate(records):
        previous = pd.to_datetime(record["event_start_utc"], utc=True)
        gap = abs((timestamp - previous).total_seconds()) / 60.0
        if gap > 90:
            continue
        dist = distance_km(lat, lon, record.get("lat"), record.get("lon"))
        if dist is None or dist > 100:
            continue
        score = (gap, dist)
        if best is None or score < best[0]:
            best = (score, index)
    return best[1] if best else None

def build(discovery_path: Path, lsr_path: Path, output_dir: Path):
    discovery = pd.read_csv(discovery_path)
    lsr = pd.read_csv(lsr_path)
    discovery["event_dt"] = pd.to_datetime(
        discovery["event_start_utc"], utc=True, errors="coerce", format="mixed"
    )
    lsr["event_dt"] = pd.to_datetime(
        lsr["event_start_utc"], utc=True, errors="coerce", format="mixed"
    )
    discovery = discovery[discovery["event_dt"].notna()].copy().reset_index(drop=True)
    lsr = lsr[lsr["event_dt"].notna()].copy().reset_index(drop=True)

    records = []
    for _, row in discovery.iterrows():
        record = row.to_dict()
        record["source_types"] = set(
            x for x in str(record.get("source_types", "")).split(",") if x
        )
        record["evidence_sources"] = set(
            x for x in str(record.get("evidence_sources", "")).split(",") if x
        )
        record["source_records"] = int(pd.to_numeric(record.get("source_records", 1), errors="coerce") or 1)
        record["lsr_count"] = int(pd.to_numeric(record.get("lsr_count", 0), errors="coerce") or 0)
        records.append(record)

    matched_reports = 0
    for _, row in lsr.iterrows():
        index = find_match(records, row["event_dt"], row.get("lat"), row.get("lon"))
        report_count = int(pd.to_numeric(row.get("report_count", 1), errors="coerce") or 1)
        if index is not None:
            record = records[index]
            matched_reports += 1
            record["source_types"].add("IEM_LSR")
            record["evidence_sources"].add("IEM_LSR")
            record["source_records"] += report_count
            record["lsr_count"] += report_count
            record["verification_class"] = canonical_class(
                record["source_types"], bool(record.get("warning_verified_by_iem"))
            )
            if not record.get("narrative"):
                record["narrative"] = row.get("narratives", "")
        else:
            timestamp = row["event_dt"]
            records.append({
                "candidate_id": stable_id(timestamp, row.get("lat"), row.get("lon")),
                "candidate_source": "IEM_LSR",
                "verification_class": "unverified_report_only",
                "verification_status": "unverified_candidate",
                "event_start_utc": timestamp.isoformat(),
                "event_end_utc": row.get("event_end_utc"),
                "state": row.get("state"),
                "county": row.get("county"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "event_type": "Snow Squall / heavy snow impact report",
                "event_id": str(row.get("cluster_id", "")),
                "source": "IEM Local Storm Reports",
                "narrative": row.get("narratives", ""),
                "evidence": "iem_lsr_cluster",
                "ncei_explicit_snow_squall": False,
                "lsr_count": report_count,
                "source_records": report_count,
                "source_types": {"IEM_LSR"},
                "evidence_sources": {"IEM_LSR"},
                "warning_verified_by_iem": False,
                "warning_status": "",
                "warning_wfo": "",
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        timestamp = pd.to_datetime(record["event_start_utc"], utc=True)
        record["window_start_utc"] = (
            timestamp - timedelta(minutes=90)
        ).isoformat().replace("+00:00", "Z")
        record["window_end_utc"] = (
            timestamp + timedelta(minutes=90)
        ).isoformat().replace("+00:00", "Z")
        record["source_types"] = ",".join(sorted(record["source_types"]))
        record["evidence_sources"] = ",".join(sorted(record["evidence_sources"]))
        record.pop("event_dt", None)
        rows.append(record)

    ledger = pd.DataFrame(rows).sort_values("event_start_utc").reset_index(drop=True)
    radar_rows = []
    for _, record in ledger.iterrows():
        options = []
        for site, origin in RADARS.items():
            dist = distance_km(
                record.get("lat"), record.get("lon"), origin[0], origin[1]
            )
            if dist is None or dist <= 220:
                options.append((float("inf") if dist is None else dist, site))
        if not options:
            continue
        dist, site = min(options)
        radar_rows.append({
            "candidate_id": record["candidate_id"],
            "radar_site": site,
            "window_start_utc": record["window_start_utc"],
            "window_end_utc": record["window_end_utc"],
            "event_start_utc": record["event_start_utc"],
            "verification_class": record["verification_class"],
            "radar_distance_km": None if dist == float("inf") else round(dist, 1),
            "state": record.get("state"),
            "county": record.get("county"),
            "lat": record.get("lat"),
            "lon": record.get("lon"),
        })

    ledger.to_csv(output_dir / "snow_squall_case_ledger.csv", index=False)
    pd.DataFrame(radar_rows).to_csv(
        output_dir / "snow_squall_case_radar_manifest.csv", index=False
    )
    summary = {
        "discovery_candidates": int(len(discovery)),
        "iem_lsr_clusters": int(len(lsr)),
        "iem_lsr_matches_to_existing": int(matched_reports),
        "unmatched_iem_lsr_cases": int(len(lsr) - matched_reports),
        "unified_cases": int(len(ledger)),
        "radar_manifest_rows": int(len(radar_rows)),
        "verification_classes": ledger["verification_class"].value_counts().to_dict()
        if not ledger.empty else {},
    }
    (output_dir / "snow_squall_case_ledger_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--iem-lsr", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    build(Path(args.discovery), Path(args.iem_lsr), Path(args.output_dir))

if __name__ == "__main__":
    main()
