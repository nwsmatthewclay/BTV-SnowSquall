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
RADAR_RECONSTRUCTION_START_YEAR = 2002

COUNTY_ROUTING_POINTS = {
    "ADDISON": (44.00, -73.10),
    "CALEDONIA": (44.46, -72.03),
    "CHITTENDEN": (44.46, -73.07),
    "ESSEX": (44.75, -71.72),
    "FRANKLIN": (44.84, -72.92),
    "GRAND ISLE": (44.79, -73.30),
    "LAMOILLE": (44.62, -72.63),
    "ORANGE": (44.01, -72.30),
    "ORLEANS": (44.81, -72.27),
    "RUTLAND": (43.58, -73.05),
    "WASHINGTON": (44.28, -72.55),
    "WINDSOR": (43.58, -72.46),
    "CLINTON": (44.69, -73.58),
    "ST LAWRENCE": (44.50, -75.08),
}

def routing_point(state, county):
    state = str(state or '').upper().strip()
    county = str(county or '').upper().strip()
    if state == 'VT':
        if any(x in county for x in ('BENNINGTON', 'WINDHAM')):
            return None
        for name, point in COUNTY_ROUTING_POINTS.items():
            if name in county:
                return point
    if state == 'NY':
        if 'SAINT LAWRENCE' in county:
            return COUNTY_ROUTING_POINTS['ST LAWRENCE']
        for name in ('CLINTON', 'ESSEX', 'FRANKLIN', 'ST LAWRENCE'):
            if name in county:
                return COUNTY_ROUTING_POINTS[name]
    return None

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

def stable_id(timestamp, lat, lon, identifier=""):
    raw = f"IEMCL|{timestamp.isoformat()}|{lat}|{lon}|{identifier}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"SSQ{timestamp:%Y%m%d%H%M}_{digest}"

def canonical_class(source_types, warning_verified=False):
    has_ncei = "NCEI_STORM_EVENTS" in source_types
    has_study = "BANACOS_STUDY_2014" in source_types
    has_report = bool({"IEM_LSR", "SWDI_PLSR"} & source_types)
    has_sqw = "IEM_COW_SQW" in source_types
    if has_ncei and has_study and has_sqw and warning_verified:
        return "official_study_warning_verified"
    if has_study and has_sqw and warning_verified:
        return "study_warning_verified"
    if has_ncei and has_study:
        return "official_plus_study"
    if has_ncei and has_report and has_sqw:
        return "official_plus_warning_and_report"
    if has_ncei and has_sqw and warning_verified:
        return "official_plus_warning_verified"
    if has_ncei and has_sqw:
        return "official_plus_warning"
    if has_ncei and has_report:
        return "official_plus_independent_report"
    if has_ncei:
        return "official_documented"
    if has_study:
        return "study_verified"
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

def _text_candidate_record(row, index):
    timestamp = pd.to_datetime(row.get("issued_utc"), utc=True, errors="coerce", format="mixed")
    if pd.isna(timestamp):
        return None
    text = str(row.get("text", "") or "")
    county_hits = [
        name for name in COUNTY_ROUTING_POINTS
        if name.replace("ST ", "SAINT ") in text.upper() or name in text.upper()
    ]
    county_hits = sorted(set(county_hits))
    lat = lon = None
    county = county_hits[0] if len(county_hits) == 1 else None
    if county is not None:
        lat, lon = COUNTY_ROUTING_POINTS[county]
    vt_counties = {"ADDISON","CALEDONIA","CHITTENDEN","GRAND ISLE","LAMOILLE","ORANGE","ORLEANS","RUTLAND","WASHINGTON","WINDSOR"}
    ny_counties = {"CLINTON","ST LAWRENCE"}
    explicit_vt = ("VERMONT" in text.upper() or "[VT" in text.upper())
    explicit_ny = ("NEW YORK" in text.upper() or "[NY" in text.upper())
    if county in {"ESSEX", "FRANKLIN"} and not (explicit_vt ^ explicit_ny):
        state = None
        county = None
        lat = lon = None
    else:
        state = "VT" if (county in vt_counties or (county in {"ESSEX","FRANKLIN"} and explicit_vt)) else ("NY" if (county in ny_counties or (county in {"ESSEX","FRANKLIN"} and explicit_ny)) else None)
    digest = hashlib.sha1(f"NWS_TEXT|{timestamp.isoformat()}|{row.get('pil')}|{index}".encode("utf-8")).hexdigest()[:10]
    return {
        "candidate_id": f"SSQ{timestamp:%Y%m%d%H%M}_{digest}",
        "candidate_source": "REGIONAL_NWS_TEXT",
        "verification_class": "unverified_report_only",
        "verification_status": "text_review_candidate",
        "event_start_utc": timestamp.isoformat(),
        "event_end_utc": None,
        "state": state,
        "county": county,
        "lat": lat,
        "lon": lon,
        "event_type": "NWS text snow-impact narrative",
        "event_id": "",
        "source": "IEM archived NWS BTV text",
        "narrative": text,
        "evidence": "regional_nws_text",
        "ncei_explicit_snow_squall": False,
        "lsr_count": 0,
        "source_records": 1,
        "source_types": {"REGIONAL_NWS_TEXT"},
        "evidence_sources": {"REGIONAL_NWS_TEXT"},
        "warning_verified_by_iem": False,
        "warning_status": "",
        "warning_wfo": "BTV",
        "text_pil": str(row.get("pil", "")),
        "text_matched_terms": str(row.get("matched_terms", "")),
        "coordinate_source": "county_routing_centroid" if county else None,
        "coordinate_precision": "routing_only" if county else None,
    }

def attach_nws_text_records(records, text_path):
    if text_path is None or not Path(text_path).exists():
        return records, 0, 0
    text = pd.read_csv(text_path)
    added = matched = 0
    for idx, row in text.iterrows():
        rec = _text_candidate_record(row, idx)
        if rec is None:
            continue
        dt = pd.to_datetime(rec["event_start_utc"], utc=True)
        match = None
        for existing_index, existing in enumerate(records):
            if existing.get("lat") is None or rec.get("lat") is None:
                continue
            previous = pd.to_datetime(existing["event_start_utc"], utc=True)
            gap = abs((dt - previous).total_seconds()) / 60.0
            if gap > 90:
                continue
            dist = distance_km(rec["lat"], rec["lon"], existing.get("lat"), existing.get("lon"))
            if dist is not None and dist <= 100:
                match = existing_index
                break
        if match is not None:
            existing = records[match]
            existing["source_types"].add("REGIONAL_NWS_TEXT")
            existing["evidence_sources"].add("REGIONAL_NWS_TEXT")
            existing["source_records"] += 1
            existing["nws_text_evidence_count"] = int(existing.get("nws_text_evidence_count", 0)) + 1
            existing["verification_class"] = canonical_class(
                existing["source_types"], bool(existing.get("warning_verified_by_iem"))
            )
            if not existing.get("narrative"):
                existing["narrative"] = rec["narrative"]
            matched += 1
        else:
            records.append(rec)
            added += 1
    return records, matched, added
def assign_episode_ids(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        ledger["episode_id"] = pd.Series(dtype="object")
        return ledger
    work = ledger.copy()
    work["event_dt"] = pd.to_datetime(work["event_start_utc"], utc=True, errors="coerce", format="mixed")
    work = work.sort_values(["event_dt", "candidate_id"], kind="stable").reset_index()
    parent = list(range(len(work)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(work)):
        left_time = work.loc[i, "event_dt"]
        if pd.isna(left_time):
            continue
        for j in range(i - 1, max(-1, i - 80), -1):
            right_time = work.loc[j, "event_dt"]
            if pd.isna(right_time):
                continue
            gap = (left_time - right_time).total_seconds() / 60.0
            if gap > 180:
                break
            same_source = str(work.loc[i, "candidate_source"]) == str(work.loc[j, "candidate_source"])
            time_limit = 180 if same_source else 90
            radius_limit = 125 if same_source else 100
            if gap > time_limit:
                continue
            distance = distance_km(work.loc[i, "lat"], work.loc[i, "lon"], work.loc[j, "lat"], work.loc[j, "lon"])
            if distance is None or distance > radius_limit:
                continue
            union(i, j)

    roots = {}
    for i in range(len(work)):
        roots.setdefault(find(i), []).append(i)

    episode_lookup = {}
    for members in roots.values():
        member_times = [work.loc[i, "event_dt"] for i in members if pd.notna(work.loc[i, "event_dt"])]
        anchor = min(member_times) if member_times else pd.Timestamp("1900-01-01", tz="UTC")
        digest_input = "|".join(sorted(str(work.loc[i, "candidate_id"]) for i in members))
        digest = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:10]
        episode_id = f"EP{anchor:%Y%m%d%H%M}_{digest}"
        for i in members:
            episode_lookup[i] = episode_id

    work["episode_id"] = [episode_lookup[i] for i in range(len(work))]
    work = work.drop(columns=["event_dt", "index"], errors="ignore")
    return work.sort_values("event_start_utc", kind="stable").reset_index(drop=True)

def build(discovery_path: Path, lsr_path: Path, output_dir: Path, nws_text_path: Path | None = None):
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
        # Defense against stale discovery artifacts: screening-language
        # NCEI records are never allowed to masquerade as official truth.
        if str(record.get("evidence", "")).startswith("screening:") or str(record.get("candidate_source", "")) == "NCEI_STORM_EVENTS_SCREENING":
            record["verification_class"] = "official_screening_candidate"
        if (pd.isna(record.get("lat")) or pd.isna(record.get("lon"))):
            coarse = routing_point(record.get("state"), record.get("county"))
            if coarse is not None:
                record["lat"], record["lon"] = coarse
                record["coordinate_source"] = "county_routing_centroid"
                record["coordinate_precision"] = "routing_only"
        records.append(record)

    matched_reports = 0
    records, matched_text, added_text = attach_nws_text_records(records, nws_text_path)
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
                "candidate_id": stable_id(timestamp, row.get("lat"), row.get("lon"), row.get("cluster_id")),
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
    ledger = assign_episode_ids(ledger)
    radar_rows = []
    for _, record in ledger.iterrows():
        event_dt = pd.to_datetime(record.get("event_start_utc"), utc=True, errors="coerce", format="mixed")
        if pd.isna(event_dt) or int(event_dt.year) < RADAR_RECONSTRUCTION_START_YEAR:
            continue
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
            "coordinate_source": record.get("coordinate_source"),
            "coordinate_precision": record.get("coordinate_precision"),
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
        "iem_nws_text_matches_to_existing": int(matched_text),
        "unmatched_iem_nws_text_candidates": int(added_text),
        "unified_cases": int(len(ledger)),
        "radar_manifest_rows": int(len(radar_rows)),
        "radar_reconstruction_start_year": RADAR_RECONSTRUCTION_START_YEAR,
        "verification_classes": ledger["verification_class"].value_counts().to_dict()
        if not ledger.empty else {},
        "physical_episode_count": int(ledger["episode_id"].nunique()) if not ledger.empty else 0,
        "episodes_with_multiple_case_records": int((ledger.groupby("episode_id").size() > 1).sum()) if not ledger.empty else 0,
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
    parser.add_argument("--nws-text", default=None)
    args = parser.parse_args()
    build(Path(args.discovery), Path(args.iem_lsr), Path(args.output_dir), Path(args.nws_text) if args.nws_text else None)

if __name__ == "__main__":
    main()
