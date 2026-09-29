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

NCEI_BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles"
IEM_LSR_BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/lsr.py"
LOCAL_TZ = ZoneInfo("America/New_York")

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
UNVERIFIED_RE = re.compile(
    r"(?:\bsnow\s+squall(?:s)?\b|\bwhite[- ]?out\b|\bnear[- ]?zero\s+visibility\b)",
    re.I,
)

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
    index = request(NCEI_BASE + "/").text
    pattern = re.compile(
        rf'href="(StormEvents_details-ftp_v1\\.0_d{year}_c\\d{{8}}\\.csv\\.gz)"'
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
    text = re.sub(r"\\b(COUNTY|PARISH|BOROUGH|CENSUS AREA)\\b", "", text)
    return re.sub(r"\\s+", " ", text).strip()

def in_primary_cwa(row: pd.Series, cfg: dict) -> bool:
    state = str(row.get("STATE", "")).upper().strip()
    county = norm_county(row.get("CZ_NAME", ""))
    if state == "VT":
        return county not in set(cfg["vt_excluded_counties"])
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
        return naive.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)
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
        state = df.get("STATE", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
        event_type = df.get("EVENT_TYPE", pd.Series("", index=df.index)).astype(str).str.strip()
        state_mask = state.isin(set(cfg["primary_states"]))
        type_mask = event_type.isin(NCEI_EVENT_TYPES)

        narratives = (
            df.get("EVENT_NARRATIVE", pd.Series("", index=df.index)).fillna("").astype(str)
            + " "
            + df.get("EPISODE_NARRATIVE", pd.Series("", index=df.index)).fillna("").astype(str)
        )
        narrative_mask = narratives.str.contains(SNOW_RE, na=False)
        candidate = df[state_mask & type_mask & (narrative_mask | event_type.eq("Snow Squall"))].copy()

        for _, row in candidate.iterrows():
            if not in_primary_cwa(row, cfg):
                continue
            start = event_start_utc(row)
            if start is None:
                continue
            lat = finite_float(row.get("BEGIN_LAT"))
            lon = finite_float(row.get("BEGIN_LON"))
            narrative = narratives.loc[row.name]
            explicit = bool(SNOW_RE.search(str(narrative))) or str(row.get("EVENT_TYPE", "")).strip() == "Snow Squall"
            rows.append({
                "candidate_id": case_key("NCEI", start, lat, lon, str(row.get("EVENT_ID", ""))),
                "candidate_source": "NCEI_STORM_EVENTS",
                "verification_class": "official_documented",
                "verification_status": "documented_candidate",
                "event_start_utc": start.isoformat(),
                "event_end_utc": None,
                "state": str(row.get("STATE", "")).strip().upper(),
                "county": norm_county(row.get("CZ_NAME", "")),
                "lat": lat,
                "lon": lon,
                "event_type": str(row.get("EVENT_TYPE", "")).strip(),
                "event_id": str(row.get("EVENT_ID", "") or ""),
                "source": str(row.get("SOURCE", "") or ""),
                "narrative": str(narrative).strip(),
                "evidence": "event_type:snow_squall" if str(row.get("EVENT_TYPE", "")).strip() == "Snow Squall" else "narrative:snow_squall",
                "ncei_explicit_snow_squall": explicit,
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
    state = str(row.get("STATE", "")).upper().strip()
    county = norm_county(row.get("COUNTY", ""))
    if state == "VT":
        return county not in set(cfg["vt_excluded_counties"])
    if state == "NY":
        return county in set(cfg["ny_cwa_counties"])
    return False

def gather_lsr(cfg: dict) -> list[dict]:
    rows = []
    for year in range(int(cfg["start_year"]), int(cfg["end_year"]) + 1):
        for state in cfg["primary_states"]:
            print(f"IEM LSR {year} {state}")
            try:
                df = iem_lsr_year(year, state)
            except Exception as exc:
                print(f"  unavailable: {exc}")
                continue
            if df.empty:
                continue
            remarks = df.get("REMARK", pd.Series("", index=df.index)).fillna("").astype(str)
            typetext = df.get("TYPETEXT", pd.Series("", index=df.index)).fillna("").astype(str)
            text = remarks + " " + typetext
            mask = text.str.contains(UNVERIFIED_RE, na=False)
            candidate = df[mask].copy()
            for _, row in candidate.iterrows():
                if not in_primary_lsr(row, cfg):
                    continue
                valid = pd.to_datetime(row.get("VALID"), utc=True, errors="coerce")
                if pd.isna(valid):
                    continue
                rows.append({
                    "candidate_id": case_key("IEM", valid.to_pydatetime(), finite_float(row.get("LAT")), finite_float(row.get("LON")), str(row.get("WFO", "")) + "|" + str(row.get("CITY", ""))),
                    "candidate_source": "IEM_LSR",
                    "verification_class": "unverified_report_only",
                    "verification_status": "unverified_candidate",
                    "event_start_utc": valid.isoformat(),
                    "event_end_utc": None,
                    "state": str(row.get("STATE", "")).strip().upper(),
                    "county": norm_county(row.get("COUNTY", "")),
                    "lat": finite_float(row.get("LAT")),
                    "lon": finite_float(row.get("LON")),
                    "event_type": str(row.get("TYPETEXT", "") or ""),
                    "event_id": "",
                    "source": str(row.get("SOURCE", "") or ""),
                    "narrative": str(row.get("REMARK", "") or "").strip(),
                    "evidence": "iem_lsr_text",
                    "ncei_explicit_snow_squall": False,
                    "lsr_count": 1,
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

def merge_candidates(records: list[dict], cfg: dict) -> list[dict]:
    ordered = sorted(records, key=lambda r: r["event_start_utc"])
    merged = []
    for rec in ordered:
        dt = datetime.fromisoformat(rec["event_start_utc"].replace("Z", "+00:00"))
        match = None
        for prior in reversed(merged[-50:]):
            pdt = datetime.fromisoformat(prior["event_start_utc"].replace("Z", "+00:00"))
            if (dt - pdt).total_seconds() > int(cfg["ncei_match_minutes"]) * 60:
                break
            dist = distance_km(rec.get("lat"), rec.get("lon"), prior.get("lat"), prior.get("lon"))
            if dist is not None and dist <= float(cfg["ncei_match_radius_km"]):
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
        if rec["candidate_source"] == "NCEI_STORM_EVENTS":
            match["verification_class"] = "official_plus_independent_report"
            match["verification_status"] = "documented_with_lsr_support"
            if not match.get("narrative"):
                match["narrative"] = rec.get("narrative", "")
            if match.get("event_type") == "" or match.get("event_type") is None:
                match["event_type"] = rec.get("event_type", "")
        match["lsr_count"] = int(match.get("lsr_count", 0)) + int(rec.get("lsr_count", 0))

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
        for radar, origin in cfg["radars"].items():
            d = distance_km(case.get("lat"), case.get("lon"), origin[0], origin[1])
            if d is None or d <= float(cfg["radar_max_range_km"]):
                available.append((radar, d))
        if not available:
            continue
        # Keep all plausible BTV-domain radars. The data builder can later
        # prioritize the nearest radar without losing alternate coverage.
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
    lsr = gather_lsr(cfg)
    merged = merge_candidates(ncei + lsr, cfg)
    radar = radar_manifest(merged, cfg)

    columns = [
        "candidate_id","candidate_source","verification_class","verification_status",
        "event_start_utc","window_start_utc","window_end_utc","state","county",
        "lat","lon","event_type","event_id","source","narrative","evidence",
        "ncei_explicit_snow_squall","lsr_count","source_records","source_types","evidence_sources",
    ]
    pd.DataFrame(merged).reindex(columns=columns).to_csv(out / "snow_squall_candidates.csv", index=False)
    pd.DataFrame(radar).to_csv(out / "snow_squall_radar_manifest.csv", index=False)

    summary = {
        "start_year": cfg["start_year"],
        "end_year": cfg["end_year"],
        "raw_ncei_records": len(ncei),
        "raw_iem_lsr_records": len(lsr),
        "merged_candidates": len(merged),
        "official_documented_candidates": sum(r["verification_class"] in {"official_documented","official_plus_independent_report"} for r in merged),
        "unverified_report_only_candidates": sum(r["verification_class"] == "unverified_report_only" for r in merged),
        "radar_manifest_rows": len(radar),
        "policy": (
            "NCEI records are official/documented evidence; IEM LSR-only records are "
            "unverified candidates. Neither absence of an NCEI record nor absence of an "
            "IEM LSR is converted into a negative label."
        ),
        "ncei_source": NCEI_BASE,
        "iem_lsr_source": IEM_LSR_BASE,
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
