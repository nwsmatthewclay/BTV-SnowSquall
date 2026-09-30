"""Discover a broad BTV-domain snow-squall case population.

Two evidence streams are intentionally kept separate:
  * NCEI Storm Events: official/documented event records.
  * IEM Local Storm Reports: preliminary/unverified evidence.

The output is a reviewable case funnel, not a truth-label generator. Cases from
both streams are reconciled by time/space, and a radar acquisition manifest is
created for KCXX/KTYX coverage.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from scripts.acquire_swdi_plsr import _bulk_year

NCEI_BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles"
IEM_LSR_BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/lsr.py"
LOCAL_STANDARD_TZ = timezone(timedelta(hours=-5))

NCEI_EVENT_TYPES = {
    "Snow Squall",
    "Winter Weather",
    "Heavy Snow",
    "Blizzard",
    "Winter Storm",
    "Strong Wind",
    "High Wind",
    "Thunderstorm Wind",
}
SNOW_RE = re.compile(r"\bsnow\s+squall(?:s)?\b", re.I)
SCREEN_RE = re.compile(
    r"(?:\bwhite[- ]?out\b|\bnear[- ]?zero\s+visibility\b|"
    r"\bnear[- ]?zero\s+vis\b|\bblinding\s+snow\b|\bflash\s+freeze\b)",
    re.I,
)
UNVERIFIED_RE = re.compile(
    r"(?:\bsnow\s+squall(?:s)?\b|\bwhite[- ]?out\b|\bnear[- ]?zero\s+visibility\b|"
    r"\bnear[- ]?zero\s+vis\b|\bblinding\s+snow\b)",
    re.I,
)
IEM_COW_BASE = "https://mesonet.agron.iastate.edu/api/1/cow.json"
NCEI_INDEX_CACHE = None

def request(url: str, **kwargs) -> requests.Response:
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            if attempt < 3:
                import time
                time.sleep(2 ** attempt)
    raise RuntimeError(str(last))

def ncei_url(year: int) -> str:
    global NCEI_INDEX_CACHE
    if NCEI_INDEX_CACHE is None:
        NCEI_INDEX_CACHE = request(NCEI_BASE + "/").text
    index = NCEI_INDEX_CACHE
    pattern = re.compile(
        rf'href="(StormEvents_details-ftp_v1\.0_d{year}_c\d{{8}}\.csv\.gz)"'
    )
    match = pattern.search(index)
    if not match:
        raise FileNotFoundError(f"No NCEI Storm Events detail archive for {year}")
    return f"{NCEI_BASE}/{match.group(1)}"

def ncei_year(year: int) -> pd.DataFrame:
    response = request(ncei_url(year))
    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as fh:
        return pd.read_csv(fh, low_memory=False)

def norm_county(value) -> str:
    text = str(value or "").upper().strip()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\b(COUNTY|PARISH|BOROUGH|CENSUS AREA)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()

def normalize_state(value) -> str:
    state = str(value or "").upper().strip()
    return {"VERMONT": "VT", "NEW YORK": "NY"}.get(state, state)

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

def routing_point(state: str, county: str):
    state = normalize_state(state)
    county = norm_county(county)
    if state == "VT":
        if any(excluded in county for excluded in cfg_excluded_counties_for_routing):
            return None
        for name, point in COUNTY_ROUTING_POINTS.items():
            if name in county:
                return point
    if state == "NY":
        if "ST LAWRENCE" in county or "SAINT LAWRENCE" in county:
            return COUNTY_ROUTING_POINTS["ST LAWRENCE"]
        for name in ("CLINTON", "ESSEX", "FRANKLIN"):
            if name in county:
                return COUNTY_ROUTING_POINTS.get(name)
    return None

cfg_excluded_counties_for_routing = ("BENNINGTON", "WINDHAM")

def in_primary_cwa(row: pd.Series, cfg: dict) -> bool:
    state = normalize_state(row.get("STATE", ""))
    county = norm_county(row.get("CZ_NAME", ""))
    if state == "VT":
        return not any(excluded in county for excluded in cfg["vt_excluded_counties"])
    if state == "NY":
        return county in set(cfg["ny_cwa_counties"])
    return False

def event_start_utc(row: pd.Series) -> datetime | None:
    try:
        ym = int(row["BEGIN_YEARMONTH"])
        day = int(row["BEGIN_DAY"])
        hm = int(row.get("BEGIN_TIME", 0) or 0)
        naive = datetime(
            ym // 100,
            ym % 100,
            day,
            hm // 100,
            hm % 100,
        )
        return naive.replace(tzinfo=LOCAL_STANDARD_TZ).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

def event_end_utc(row: pd.Series) -> datetime | None:
    try:
        ym = int(row["END_YEARMONTH"])
        day = int(row["END_DAY"])
        hm = int(row.get("END_TIME", 0) or 0)
        naive = datetime(ym // 100, ym % 100, day, hm // 100, hm % 100)
        return naive.replace(tzinfo=LOCAL_STANDARD_TZ).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
def finite_float(value):
    try:
        v = float(value)
        return v if pd.notna(v) else None
    except (TypeError, ValueError):
        return None

def case_key(prefix: str, timestamp: datetime, lat, lon, identifier: str) -> str:
    raw = f"{prefix}|{timestamp.isoformat()}|{lat}|{lon}|{identifier}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"SSQ{timestamp:%Y%m%d%H%M}_{digest}"

def gather_ncei(cfg: dict) -> list[dict]:
    rows = []
    for year in range(int(cfg["start_year"]), int(cfg["end_year"]) + 1):
        print(f"NCEI {year}")
        df = ncei_year(year)
        state_raw = df.get("STATE", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
        state = state_raw.replace({"VERMONT": "VT", "NEW YORK": "NY"})
        event_type = df.get("EVENT_TYPE", pd.Series("", index=df.index)).astype(str).str.strip()
        state_mask = state.isin(set(cfg["primary_states"]))

        narratives = (
            df.get("EVENT_NARRATIVE", pd.Series("", index=df.index)).fillna("").astype(str)
            + " "
            + df.get("EPISODE_NARRATIVE", pd.Series("", index=df.index)).fillna("").astype(str)
        )
        narrative_mask = narratives.str.contains(SNOW_RE, na=False)
        candidate = df[state_mask & (narrative_mask | event_type.eq("Snow Squall") | narratives.str.contains(SCREEN_RE, na=False))].copy()

        for _, row in candidate.iterrows():
            if not in_primary_cwa(row, cfg):
                continue
            start = event_start_utc(row)
            if start is None:
                continue
            lat = finite_float(row.get("BEGIN_LAT"))
            lon = finite_float(row.get("BEGIN_LON"))
            coordinate_source = "ncei_event_point" if lat is not None and lon is not None else None
            coordinate_precision = "event" if coordinate_source else None
            if lat is None or lon is None:
                coarse = routing_point(normalize_state(row.get("STATE", "")), norm_county(row.get("CZ_NAME", "")))
                if coarse is not None:
                    lat, lon = coarse
                    coordinate_source = "county_routing_centroid"
                    coordinate_precision = "routing_only"
            end = event_end_utc(row)
            narrative = narratives.loc[row.name]
            explicit = bool(SNOW_RE.search(str(narrative))) or str(row.get("EVENT_TYPE", "")).strip() == "Snow Squall"
            source_name = "NCEI_STORM_EVENTS" if explicit else "NCEI_STORM_EVENTS_SCREENING"
            rows.append({
                "candidate_id": case_key("NCEI", start, lat, lon, str(row.get("EVENT_ID", ""))),
                "candidate_source": source_name,
                "verification_class": "official_documented" if explicit else "official_screening_candidate",
                "verification_status": "documented_candidate",
                "event_start_utc": start.isoformat(),
                "event_end_utc": end.isoformat() if end else None,
                "state": normalize_state(row.get("STATE", "")),
                "county": norm_county(row.get("CZ_NAME", "")),
                "lat": lat,
                "lon": lon,
                "event_type": str(row.get("EVENT_TYPE", "")).strip(),
                "event_id": str(row.get("EVENT_ID", "") or ""),
                "source": str(row.get("SOURCE", "") or ""),
                "narrative": str(narrative).strip(),
                "evidence": ("event_type:snow_squall" if str(row.get("EVENT_TYPE", "")).strip() == "Snow Squall" else ("narrative:snow_squall" if bool(SNOW_RE.search(str(narrative))) else "screening:snow-impact-language")),
                "ncei_explicit_snow_squall": explicit,
                "coordinate_source": coordinate_source,
                "coordinate_precision": coordinate_precision,
                "lsr_count": 0,
            })
    return rows

def iem_lsr_year(year: int, state: str) -> pd.DataFrame:
    start = f"{year}-01-01T00:00Z"
    end = f"{year}-12-31T23:59Z"
    params = {"state": state, "sts": start, "ets": end, "fmt": "csv"}
    response = request(IEM_LSR_BASE, params=params)
    if not response.text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(response.text))

def in_primary_lsr(row: pd.Series, cfg: dict) -> bool:
    state = normalize_state(row.get("STATE", ""))
    county = norm_county(row.get("COUNTY", ""))
    if state == "VT":
        return not any(excluded in county for excluded in cfg["vt_excluded_counties"])
    if state == "NY":
        return county in set(cfg["ny_cwa_counties"])
    return False

def gather_cow_sqw(cfg: dict) -> list[dict]:
    rows = []
    start_year = max(int(cfg["start_year"]), int(cfg.get("warning_start_year", 2018)))
    for year in range(start_year, int(cfg["end_year"]) + 1):
        params = {
            "phenomena": "SQ",
            "begints": f"{year}-01-01T00:00Z",
            "endts": f"{year}-12-31T23:59Z",
,
            "lsrtype": "SQ"
        }
        for wfo in cfg.get("warning_wfos", ["BTV"]):
            params["wfo"] = wfo
            print(f"IEM COW SQW {year} {wfo}")
            try:
                payload = request(IEM_COW_BASE, params=params).json()
            except Exception as exc:
                print(f"  unavailable: {exc}")
                continue
            features = (payload.get("events") or {}).get("features") or []
            for feature in features:
                props = feature.get("properties") or {}
                issue = pd.to_datetime(props.get("issue"), utc=True, errors="coerce")
                if pd.isna(issue):
                    continue
                lat = finite_float(props.get("lat0"))
                lon = finite_float(props.get("lon0"))
                report_ids = str(props.get("stormreports_all") or "").strip()
                lsr_count = len([item for item in report_ids.split(",") if item.strip()])
                iem_verified = bool(props.get("verify"))
                lead_min = finite_float(props.get("lead0"))
                anchor = issue
                anchor_type = "warning_issue"
                if iem_verified and lead_min is not None and lead_min >= 0:
                    anchor = issue + pd.Timedelta(minutes=lead_min)
                    anchor_type = "first_verifying_lsr"
                rows.append({
                    "candidate_id": case_key("SQW", issue.to_pydatetime(), lat, lon, f"{wfo}|{props.get('eventid', '')}"),
                    "candidate_source": "IEM_COW_SQW",
                    "verification_class": "warning_verified" if iem_verified else "warning_only",
                    "verification_status": "warning_issued",
                    "event_start_utc": anchor.isoformat(),
                    "event_end_utc": props.get("expire"),
                    "state": None,
                    "county": None,
                    "lat": lat,
                    "lon": lon,
                    "event_type": "Snow Squall Warning",
                    "event_id": str(props.get("eventid") or ""),
                    "source": f"NWS WFO {wfo}",
                    "narrative": "",
                    "evidence": "iem_cow_sqw",
                    "event_anchor_type": anchor_type,
                    "warning_issue_utc": issue.isoformat(),
                    "warning_leadtime_to_first_verifying_lsr_min": lead_min,
                    "ncei_explicit_snow_squall": False,
                    "coordinate_source": "iem_warning_point",
                    "coordinate_precision": "warning_reference",
                    "lsr_count": lsr_count,
                    "warning_verified_by_iem": bool(props.get("verify")),
                    "warning_status": str(props.get("status") or ""),
                    "warning_wfo": str(props.get("wfo") or wfo),
                })
    return rows
def gather_swdi_plsr(cfg: dict) -> list[dict]:
    rows = []
    for year in range(max(int(cfg["start_year"]), 2005), int(cfg["end_year"]) + 1):
        print(f"SWDI PLSR {year}")
        try:
            frame = _bulk_year(
                year,
                pd.Timestamp(f"{year}-01-01", tz="UTC"),
                pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC"),
                "",
            )
        except Exception as exc:
            print(f"  unavailable: {exc}")
            continue
        if frame.empty:
            continue
        normalized = {str(col).strip().upper(): col for col in frame.columns}
        state_col = next((normalized.get(x) for x in ("STATE", "STATE_ABBR", "STATE_CODE") if normalized.get(x)), None)
        time_col = next((normalized.get(x) for x in ("ZTIME", "VALID", "VALID_TIME", "UTC_TIME", "DATE_TIME", "DATETIME") if normalized.get(x)), None)
        if state_col is None or time_col is None:
            continue
        states = frame[state_col].astype(str).str.upper().str.strip()
        frame = frame[states.isin(set(cfg["primary_states"]))].copy()
        if frame.empty:
            continue
        remarks = frame.get("REMARK", pd.Series("", index=frame.index)).fillna("").astype(str)
        typetext = frame.get("TYPETEXT", pd.Series("", index=frame.index)).fillna("").astype(str)
        mask = (remarks + " " + typetext).str.contains(UNVERIFIED_RE, na=False)
        for _, row in frame[mask].iterrows():
            valid = pd.to_datetime(row.get(time_col), utc=True, errors="coerce")
            if pd.isna(valid):
                continue
            state = str(row.get(state_col, "")).upper().strip()
            county = norm_county(row.get("COUNTY", ""))
            if state == "VT" and any(excluded in county for excluded in cfg["vt_excluded_counties"]):
                continue
            if state == "NY" and county not in set(cfg["ny_cwa_counties"]):
                continue
            lat = finite_float(row.get("LAT"))
            lon = finite_float(row.get("LON"))
            rows.append({
                "candidate_id": case_key("SWDI", valid.to_pydatetime(), lat, lon, f"{row.get('WFO', '')}|{row.get('CITY', '')}|{row.get('TYPECODE', '')}"),
                "candidate_source": "SWDI_PLSR",
                "verification_class": "unverified_report_only",
                "verification_status": "unverified_candidate",
                "event_start_utc": valid.isoformat(),
                "event_end_utc": None,
                "state": state,
                "county": county,
                "lat": lat,
                "lon": lon,
                "event_type": str(row.get("TYPETEXT", "") or ""),
                "event_id": "",
                "source": str(row.get("SOURCE", "") or ""),
                "narrative": str(row.get("REMARK", "") or "").strip(),
                "evidence": "swdi_plsr_text",
                "ncei_explicit_snow_squall": False,
                "lsr_count": 1,
            })
    return rows
def gather_banacos_seed(cfg: dict) -> list[dict]:
    seed_path = Path("data/manifests/banacos_historical_36.csv")
    if not seed_path.exists():
        return []
    station_meta = {
        "KBTV": (44.471955, -73.153276),
        "KMPV": (44.203489, -72.562096),
        "KMSS": (44.936241, -74.845120),
    }
    frame = pd.read_csv(seed_path)
    rows = []
    for _, row in frame.iterrows():
        try:
            local_date = pd.Timestamp(str(row["date_local"])).date()
            hh, mm = [int(x) for x in str(row["start_time_utc"]).split(":")[:2]]
            start = datetime(local_date.year, local_date.month, local_date.day, hh, mm, tzinfo=timezone.utc)
        except (TypeError, ValueError, IndexError):
            continue
        station = str(row["observing_station"]).upper().strip()
        lat, lon = station_meta.get(station, (None, None))
        duration = finite_float(row.get("vis_lt_08_min"))
        end = start + timedelta(minutes=duration) if duration is not None else None
        rows.append({
            "candidate_id": str(row["case_id"]),
            "candidate_source": "BANACOS_STUDY_2014",
            "verification_class": "study_verified",
            "verification_status": "historical_manual_radar_surface_verification",
            "event_start_utc": start.isoformat(),
            "event_end_utc": end.isoformat() if end else None,
            "state": "VT" if station in {"KBTV", "KMPV"} else "NY",
            "county": None,
            "lat": lat,
            "lon": lon,
            "event_type": "Snow Squall",
            "event_id": str(row["case_id"]),
            "source": "Banacos et al. 2014 NWA JOM Table 2",
            "narrative": "Historically identified snow squall case; manually checked against ASOS and 2-km radar mosaic in the published study.",
            "evidence": "banacos_2014_table2",
            "ncei_explicit_snow_squall": True,
            "lsr_count": 0,
            "source_records": 1,
            "source_types": {"BANACOS_STUDY_2014"},
            "evidence_sources": {"BANACOS_STUDY_2014"},
            "peak_wind_kt": finite_float(row.get("peak_gust_kt")),
            "min_visibility_km": finite_float(row.get("min_visibility_km")),
            "hybrid_case": bool(row.get("hybrid_case", False)),
        })
    return rows

def distance_km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    p1, p2 = radians(float(lat1)), radians(float(lat2))
    dp = radians(float(lat2) - float(lat1))
    dl = radians(float(lon2) - float(lon1))
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(min(1.0, sqrt(a)))

def merged_verification_class(source_types: set[str], warning_verified: bool = False) -> str:
    has_ncei = "NCEI_STORM_EVENTS" in source_types
    has_study = "BANACOS_STUDY_2014" in source_types
    has_lsr = "IEM_LSR" in source_types
    has_plsr = "SWDI_PLSR" in source_types
    has_sqw = "IEM_COW_SQW" in source_types
    has_report = has_lsr or has_plsr
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

def merge_candidates(records: list[dict], cfg: dict) -> list[dict]:
    ordered = sorted(records, key=lambda r: r["event_start_utc"])
    merged = []
    for rec in ordered:
        dt = datetime.fromisoformat(rec["event_start_utc"].replace("Z", "+00:00"))
        match = None
        for prior in reversed(merged[-50:]):
            pdt = datetime.fromisoformat(prior["event_start_utc"].replace("Z", "+00:00"))
            gap_min = (dt - pdt).total_seconds() / 60.0
            if gap_min > max(int(cfg["ncei_match_minutes"]), int(cfg["lsr_cluster_minutes"])):
                break
            # Do not collapse independent records produced by the same
            # authoritative source. Cross-source reconciliation remains allowed.
            if rec["candidate_source"] == prior["candidate_source"] in {"NCEI_STORM_EVENTS", "IEM_COW_SQW"}:
                continue
            dist = distance_km(rec.get("lat"), rec.get("lon"), prior.get("lat"), prior.get("lon"))
            radius = (
                float(cfg["lsr_cluster_radius_km"])
                if rec["candidate_source"] == prior["candidate_source"] == "IEM_LSR"
                else float(cfg["ncei_match_radius_km"])
            )
            minutes = (
                int(cfg["lsr_cluster_minutes"])
                if rec["candidate_source"] == prior["candidate_source"] == "IEM_LSR"
                else int(cfg["ncei_match_minutes"])
            )
            if gap_min <= minutes and dist is not None and dist <= radius:
                match = prior
                break
        if match is None:
            merged.append({
                **rec,
                "source_records": 1,
                "source_types": {rec["candidate_source"]},
                "evidence_sources": {rec["candidate_source"]},
            })
            continue

        match["source_records"] += 1
        match["source_types"].add(rec["candidate_source"])
        match["evidence_sources"].add(rec["candidate_source"])
        if not match.get("narrative"):
            match["narrative"] = rec.get("narrative", "")
        if match.get("event_type") in ("", None):
            match["event_type"] = rec.get("event_type", "")
        if rec.get("warning_verified_by_iem"):
            match["warning_verified_by_iem"] = True
        if rec.get("warning_status"):
            match["warning_status"] = rec.get("warning_status")
        if rec.get("warning_wfo"):
            match["warning_wfo"] = rec.get("warning_wfo")
        match["lsr_count"] = int(match.get("lsr_count", 0)) + int(rec.get("lsr_count", 0))
        match["verification_class"] = merged_verification_class(
            set(match["source_types"]),
            warning_verified=bool(match.get("warning_verified_by_iem")),
        )
        if match["verification_class"].startswith("official"):
            match["verification_status"] = "documented_with_independent_evidence"
        elif "warning" in match["verification_class"]:
            match["verification_status"] = "warning_candidate"

    for rec in merged:
        rec["source_types"] = ",".join(sorted(rec["source_types"]))
        rec["evidence_sources"] = ",".join(sorted(rec["evidence_sources"]))
        rec["event_start_utc"] = rec["event_start_utc"]
        rec["window_start_utc"] = (
            datetime.fromisoformat(rec["event_start_utc"].replace("Z", "+00:00"))
            - timedelta(minutes=int(cfg["candidate_buffer_minutes"]))
        ).isoformat().replace("+00:00", "Z")
        rec["window_end_utc"] = (
            datetime.fromisoformat(rec["event_start_utc"].replace("Z", "+00:00"))
            + timedelta(minutes=int(cfg["candidate_buffer_minutes"]))
        ).isoformat().replace("+00:00", "Z")
    return merged

def radar_manifest(candidates: list[dict], cfg: dict) -> list[dict]:
    out = []
    for case in candidates:
        available = []
        # Retain ungeolocated cases in the ledger, but never generate a
        # radar acquisition row without finite coordinates.
        if case.get("lat") is None or case.get("lon") is None:
            continue
        for radar, origin in cfg["radars"].items():
            d = distance_km(case.get("lat"), case.get("lon"), origin[0], origin[1])
            if d is not None and d <= float(cfg["radar_max_range_km"]):
                available.append((radar, d))
        if not available:
            continue
        # Prefer the nearest plausible radar to control expansion volume.
        available = sorted(available, key=lambda item: float("inf") if item[1] is None else item[1])
        available = available[: int(cfg.get("max_radars_per_case", len(available)))]
        for radar, d in available:
            out.append({
                "candidate_id": case["candidate_id"],
                "radar_site": radar,
                "window_start_utc": case["window_start_utc"],
                "window_end_utc": case["window_end_utc"],
                "event_start_utc": case["event_start_utc"],
                "verification_class": case["verification_class"],
                "radar_distance_km": round(d, 1) if d is not None else None,
                "state": case.get("state"),
                "county": case.get("county"),
                "lat": case.get("lat"),
                "lon": case.get("lon"),
            })
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/snow_squall_discovery.json")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))

    ncei = gather_ncei(cfg)
    plsr = gather_swdi_plsr(cfg)
    cow = gather_cow_sqw(cfg)
    seed = gather_banacos_seed(cfg)
    merged = merge_candidates(ncei + plsr + cow + seed, cfg)
    radar = radar_manifest(merged, cfg)

    columns = [
        "candidate_id","candidate_source","verification_class","verification_status",
        "event_start_utc","window_start_utc","window_end_utc","state","county",
        "lat","lon","event_type","event_id","source","narrative","evidence",
        "ncei_explicit_snow_squall","coordinate_source","coordinate_precision","lsr_count","source_records","source_types","evidence_sources","warning_verified_by_iem","warning_status","warning_wfo",
    ]
    pd.DataFrame(merged).reindex(columns=columns).to_csv(out / "snow_squall_candidates.csv", index=False)
    pd.DataFrame(radar).to_csv(out / "snow_squall_radar_manifest.csv", index=False)

    summary = {
        "start_year": cfg["start_year"],
        "end_year": cfg["end_year"],
        "raw_ncei_records": len(ncei),
        "raw_swdi_plsr_records": len(plsr),
        "raw_iem_sqw_records": len(cow),
        "raw_banacos_seed_records": len(seed),
        "merged_candidates": len(merged),
        "official_documented_candidates": sum(r["verification_class"] in {"official_documented","official_plus_independent_report","official_plus_warning","official_plus_warning_and_report","official_study_warning_verified","official_plus_study"} for r in merged),
        "study_verified_candidates": sum(r["verification_class"] in {"study_verified","official_plus_study","study_warning_verified","official_study_warning_verified"} for r in merged),
        "ncei_screening_candidates": sum("NCEI_STORM_EVENTS_SCREENING" in str(r.get("source_types", "")) for r in merged),
        "screening_candidates": sum(r["verification_class"] == "official_screening_candidate" for r in merged),
        "warning_verified_candidates": sum(r["verification_class"] == "warning_verified" for r in merged),
        "warning_only_candidates": sum(r["verification_class"] == "warning_only" for r in merged),
        "warning_plus_report_candidates": sum(r["verification_class"] == "warning_plus_report" for r in merged),
        "unverified_report_only_candidates": sum(r["verification_class"] == "unverified_report_only" for r in merged),
        "radar_manifest_rows": len(radar),
        "policy": (
            "NCEI records are official/documented evidence; IEM LSR-only records are "
            "unverified candidates. Neither absence of an NCEI record nor absence of an "
            "IEM LSR is converted into a negative label."
        ),
        "ncei_source": NCEI_BASE,
        "swdi_plsr_source": "https://www.ncei.noaa.gov/swdiws/csv/plsr",
    }
    (out / "snow_squall_discovery_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("Top candidate cases:")
    for row in merged[:25]:
        print(
            row["candidate_id"], row["verification_class"],
            row["event_start_utc"], row.get("state"), row.get("county"),
            "LSRs=", row.get("lsr_count", 0),
        )

if __name__ == "__main__":
    main()
