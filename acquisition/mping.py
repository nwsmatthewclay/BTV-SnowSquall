"""Acquire historical mPING reports as independent precipitation-type evidence.

The current mPING API supports authenticated report queries filtered by UTC
observation time and spatial bounding box. Reports are preserved verbatim at
the useful field level and summarized into conservative precipitation-type
buckets for surface/ptype QC. mPING evidence never becomes an automatic
snow-squall label.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://mping.ou.edu/mping/api/v2/reports"
STATIONS = {
    "KBTV": (44.471955, -73.153276),
    "KMPV": (44.203489, -72.562096),
    "KMSS": (44.936241, -74.845120),
}
EARTH_RADIUS_KM = 6371.0
DEFAULT_RADIUS_KM = 75.0
TIMEOUT_SECONDS = 60
MAX_PAGES = 200


def ptype_bucket(category: object, description: object) -> str:
    text = f"{category or ''} {description or ''}".strip().lower()
    if any(token in text for token in ("freezing rain", "freezing drizzle", "ice storm")):
        return "freezing_rain"
    if any(token in text for token in ("mixed", "sleet", "ice pellets", "snow pellets")):
        return "mixed"
    if "snow" in text:
        return "snow"
    if "rain" in text or "drizzle" in text:
        return "rain"
    return "other"


def bbox_for_point(lat: float, lon: float, radius_km: float = DEFAULT_RADIUS_KM) -> str:
    lat_delta = radius_km / 111.32
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    lon_delta = radius_km / (111.32 * cos_lat)
    return ",".join(
        f"{value:.5f}"
        for value in (lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta)
    )


def _parse_point(case: pd.Series) -> tuple[float, float] | None:
    lat = pd.to_numeric(case.get("lat"), errors="coerce")
    lon = pd.to_numeric(case.get("lon"), errors="coerce")
    if pd.notna(lat) and pd.notna(lon):
        return float(lat), float(lon)
    station = str(case.get("observing_station", "") or "").upper().strip()
    return STATIONS.get(station)


def _query_case(
    case: pd.Series,
    api_key: str,
    radius_km: float,
    buffer_before: int,
    buffer_after: int,
) -> tuple[pd.DataFrame, dict]:
    case_id = str(case["case_id"])
    start = pd.to_datetime(case["event_start_utc"], utc=True) - pd.Timedelta(minutes=buffer_before)
    documented_end = pd.to_datetime(case.get("event_end_utc"), utc=True, errors="coerce")
    if pd.isna(documented_end):
        duration = pd.to_numeric(case.get("vis_below_0p8_min"), errors="coerce")
        documented_end = (
            pd.to_datetime(case["event_start_utc"], utc=True) + pd.Timedelta(minutes=float(duration))
            if pd.notna(duration)
            else pd.to_datetime(case["event_start_utc"], utc=True) + pd.Timedelta(minutes=60)
        )
    end = documented_end + pd.Timedelta(minutes=buffer_after)

    point = _parse_point(case)
    status = {
        "case_id": case_id,
        "status": "unavailable",
        "record_count": 0,
        "query_start_utc": start.isoformat().replace("+00:00", "Z"),
        "query_end_utc": end.isoformat().replace("+00:00", "Z"),
        "radius_km": radius_km,
        "bbox": None,
        "error": None,
    }
    if point is None:
        status["status"] = "missing_case_location"
        status["error"] = "No case or observing-station coordinates available."
        return pd.DataFrame(), status

    bbox = bbox_for_point(point[0], point[1], radius_km)
    status["bbox"] = bbox
    headers = {
        "Accept": "application/json",
        "Authorization": f"Token {api_key}",
        "User-Agent": "BTV-SnowSquall research dataset builder/1.0",
    }
    params = {
        "obtime_gte": start.strftime("%Y-%m-%d %H:%M:%S"),
        "obtime_lte": end.strftime("%Y-%m-%d %H:%M:%S"),
        "in_bbox": bbox,
    }

    rows: list[dict] = []
    url = BASE_URL
    page_params = params
    try:
        for _ in range(MAX_PAGES):
            response = requests.get(url, params=page_params, headers=headers, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("results") or []
            rows.extend(batch)
            next_url = payload.get("next")
            if not next_url:
                break
            url = next_url
            page_params = None
        else:
            raise RuntimeError(f"mPING pagination exceeded {MAX_PAGES} pages for {case_id}")
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
        return pd.DataFrame(), status

    normalized = []
    for item in rows:
        geom = item.get("geom") or {}
        coords = geom.get("coordinates") or []
        lon = coords[0] if len(coords) >= 2 else None
        lat = coords[1] if len(coords) >= 2 else None
        normalized.append({
            "case_id": case_id,
            "mping_id": item.get("id"),
            "obtime": item.get("obtime"),
            "category": item.get("category"),
            "description": item.get("description"),
            "description_id": item.get("description_id"),
            "lon": lon,
            "lat": lat,
            "ptype_bucket": ptype_bucket(item.get("category"), item.get("description")),
            "truth_source": "mPING",
            "truth_status": "independent_surface_ptype_evidence",
        })

    frame = pd.DataFrame(normalized)
    if not frame.empty:
        frame["obtime"] = pd.to_datetime(frame["obtime"], utc=True, errors="coerce")
        frame = frame[(frame["obtime"] >= start) & (frame["obtime"] <= end)].copy()
        frame["obtime"] = frame["obtime"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    status["record_count"] = int(len(frame))
    status["status"] = "available" if not frame.empty else "available_empty"
    return frame, status


def acquire_cases(
    cases_csv: Path,
    output: Path,
    status_output: Path,
    api_key: str | None = None,
    workers: int = 6,
    radius_km: float = DEFAULT_RADIUS_KM,
    buffer_before: int = 120,
    buffer_after: int = 150,
) -> dict:
    cases = pd.read_csv(cases_csv)
    required = {"case_id", "event_start_utc"}
    missing = required - set(cases.columns)
    if missing:
        raise ValueError(f"Case manifest missing required fields: {sorted(missing)}")

    key = api_key or os.environ.get("MPING_API_KEY")
    if not key:
        summary = {
            "status": "disabled_no_api_key",
            "cases_requested": int(cases["case_id"].nunique()),
            "cases_with_data": 0,
            "cases_empty": 0,
            "cases_unavailable": int(cases["case_id"].nunique()),
            "records": 0,
            "policy": "mPING is independent precipitation-type evidence only; no automatic truth labels.",
            "cases": [],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(output, index=False)
        status_output.parent.mkdir(parents=True, exist_ok=True)
        status_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return summary

    unique = list(cases.drop_duplicates("case_id").iterrows())
    frames = []
    statuses = []
    workers = max(1, min(int(workers), 12))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _query_case,
                row,
                key,
                radius_km,
                buffer_before,
                buffer_after,
            ): str(row["case_id"])
            for _, row in unique
        }
        for future in as_completed(futures):
            frame, status = future.result()
            statuses.append(status)
            if not frame.empty:
                frames.append(frame)
            print(f"mPING {status['case_id']}: {status['status']} ({status['record_count']} reports)")

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    if not result.empty:
        result = result.drop_duplicates(["case_id", "mping_id"]).sort_values(["case_id", "obtime"]).reset_index(drop=True)

    summary = {
        "status": "complete",
        "cases_requested": int(cases["case_id"].nunique()),
        "cases_with_data": int(sum(s["status"] == "available" for s in statuses)),
        "cases_empty": int(sum(s["status"] == "available_empty" for s in statuses)),
        "cases_unavailable": int(sum(s["status"] not in {"available", "available_empty"} for s in statuses)),
        "records": int(len(result)),
        "ptype_counts": result["ptype_bucket"].value_counts().to_dict() if not result.empty else {},
        "policy": "mPING is independent precipitation-type evidence only; it is not an automatic snow-squall truth label.",
        "api_endpoint": BASE_URL,
        "cases": sorted(statuses, key=lambda x: x["case_id"]),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    status_output.parent.mkdir(parents=True, exist_ok=True)
    status_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--radius-km", type=float, default=DEFAULT_RADIUS_KM)
    parser.add_argument("--buffer-before", type=int, default=120)
    parser.add_argument("--buffer-after", type=int, default=150)
    args = parser.parse_args()
    acquire_cases(
        Path(args.cases),
        Path(args.output),
        Path(args.status),
        workers=args.workers,
        radius_km=args.radius_km,
        buffer_before=args.buffer_before,
        buffer_after=args.buffer_after,
    )


if __name__ == "__main__":
    main()
