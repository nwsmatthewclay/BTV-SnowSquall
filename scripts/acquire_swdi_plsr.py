"""Acquire NOAA SWDI Preliminary Local Storm Reports as a separate evidence stream.

SWDI explicitly includes Preliminary Local Storm Reports (PLSR). These reports
are intentionally NOT treated as authoritative truth: SWDI states that it adds
no additional QC and that absence of a SWDI report does not imply no severe
weather occurred.

The acquisition is fail-soft. If the service is unavailable for a case, the
status is recorded and the workflow does not manufacture a negative label.
"""

from __future__ import annotations

import argparse
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

BASE_URLS = (
    "https://www.ncei.noaa.gov/swdiws/csv/plsr",
    "https://www.ncdc.noaa.gov/swdiws/csv/plsr",
)
BULK_BASE_URL = "https://www.ncei.noaa.gov/pub/data/swdi/database-csv/v2"
BTV_BBOX = "-80,40,-67,48"
STATION_STATE = {
    "KBTV": "VT",
    "KMPV": "VT",
    "KMSS": "NY",
}
TIMEOUT_SECONDS = 60
RETRIES = 4
BULK_START_YEAR = 2005


def _request(url: str) -> requests.Response:
    last = None
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError(str(last))


def _find_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    normalized = {str(col).strip().upper(): col for col in frame.columns}
    for name in names:
        if name in normalized:
            return normalized[name]
    return None


def _rest_year(year: int, start: pd.Timestamp, end: pd.Timestamp, state: str) -> pd.DataFrame:
    # SWDI's documented service uses calendar dates with an exclusive end.
    start_text = pd.Timestamp(start).tz_convert('UTC').strftime('%Y%m%d')
    end_text = pd.Timestamp(end).tz_convert('UTC').strftime('%Y%m%d')
    for base in BASE_URLS:
        url = f'{base}/{start_text}:{end_text}/10000000'
        try:
            response = _request(url + f'?bbox={BTV_BBOX}')
            if not response.text.strip():
                continue
            frame = pd.read_csv(io.StringIO(response.text), comment='#', low_memory=False)
            if frame.empty:
                continue
            return frame
        except Exception as exc:
            print(f'SWDI REST endpoint {base} unavailable for {year}: {type(exc).__name__}: {exc}')
    return pd.DataFrame()

def _bulk_year(year: int, start: pd.Timestamp, end: pd.Timestamp, state: str, columns: list[str] | None = None) -> pd.DataFrame:
    # Prefer the live SWDI REST service. Keep the annual bulk archive as a
    # fallback for older archive quirks.
    try:
        frame = _rest_year(year, start, end, state)
        if not frame.empty:
            normalized = {str(col).strip().upper(): col for col in frame.columns}
            time_col = next((normalized.get(x) for x in ('ZTIME', 'VALID', 'VALID_TIME', 'UTC_TIME', 'DATE_TIME', 'DATETIME') if normalized.get(x)), None)
            state_col = next((normalized.get(x) for x in ('STATE', 'STATE_ABBR', 'STATE_CODE') if normalized.get(x)), None)
            if time_col is not None:
                times = pd.to_datetime(frame[time_col], utc=True, errors='coerce')
                mask = times.between(start, end, inclusive='both')
                if state_col and state:
                    mask &= frame[state_col].astype(str).str.upper().eq(state)
                return frame.loc[mask].copy()
    except Exception as exc:
        print(f'SWDI REST fallback to annual bulk for {year}: {type(exc).__name__}: {exc}')

    if year < BULK_START_YEAR:
        return pd.DataFrame()
    url = f"{BULK_BASE_URL}/plsr-{year}.csv.gz"
    response = _request(url)
    header = pd.read_csv(io.BytesIO(response.content), compression='gzip', nrows=0, comment='#')
    time_col = _find_column(header, ('VALID', 'VALID_TIME', 'UTC_TIME', 'DATE_TIME', 'DATETIME', 'ZTIME'))
    state_col = _find_column(header, ('STATE', 'STATE_ABBR', 'STATE_CODE'))
    if time_col is None:
        raise RuntimeError(f'PLSR bulk file {year} has no recognized time column')
    usecols = list(header.columns)
    if columns:
        normalized = {str(col).strip().upper(): col for col in header.columns}
        resolved = [normalized[name.strip().upper()] for name in columns if name.strip().upper() in normalized]
        if time_col and time_col not in resolved:
            resolved.append(time_col)
        if state_col and state_col not in resolved:
            resolved.append(state_col)
        usecols = list(dict.fromkeys(resolved))
    frame = pd.read_csv(io.BytesIO(response.content), compression='gzip', usecols=usecols, low_memory=False, comment='#')
    times = pd.to_datetime(frame[time_col], utc=True, errors='coerce')
    mask = times.between(start, end, inclusive='both')
    if state_col and state:
        mask &= frame[state_col].astype(str).str.upper().eq(state)
    return frame.loc[mask].copy()

def acquire_case(case: pd.Series) -> tuple[pd.DataFrame, dict]:
    case_id = str(case["case_id"])
    station = str(case.get("observing_station", "") or "").upper().strip()
    state = STATION_STATE.get(station)
    expected = pd.Timestamp(case["event_start_utc"], tz="UTC")
    start = expected - pd.Timedelta(days=1)
    end = expected + pd.Timedelta(days=1)
    year = int(expected.year)

    status = {
        "case_id": case_id,
        "observing_station": station,
        "state": state,
        "query_expected_event_start_utc": expected.isoformat(),
        "query_start_utc": start.isoformat(),
        "query_end_utc": end.isoformat(),
        "source": "SWDI_PLSR_BULK",
        "status": "unavailable",
        "record_count": 0,
        "error": None,
    }

    if year < BULK_START_YEAR:
        status["status"] = "archive_not_available"
        status["error"] = f"SWDI bulk PLSR archive begins in {BULK_START_YEAR}; no annual file for {year}"
        return pd.DataFrame(), status

    try:
        frame = _bulk_year(year, start, end, state or "")
        if frame.empty:
            status["status"] = "available_empty"
            return pd.DataFrame(), status
        frame.insert(0, "case_id", case_id)
        frame.insert(1, "truth_source", "NCEI_SWDI_PLSR")
        frame.insert(2, "truth_status", "preliminary_local_storm_report")
        frame.insert(3, "observing_station", station)
        frame.insert(4, "query_expected_event_start_utc", expected.isoformat())
        frame.insert(5, "query_start_utc", start.isoformat())
        frame.insert(6, "query_end_utc", end.isoformat())
        status["status"] = "available"
        status["record_count"] = int(len(frame))
        return frame, status
    except Exception as exc:
        status["error"] = str(exc)
        return pd.DataFrame(), status

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    cases = pd.read_csv(args.cases).drop_duplicates("case_id")
    frames = []
    statuses = []
    workers = max(1, min(int(args.workers), 12))

    # PLSR requests are independent by case. Run them concurrently while
    # keeping a bounded worker count so SWDI is not hammered by the batch.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(acquire_case, row): str(row["case_id"]) for _, row in cases.iterrows()}
        results = []
        for future in as_completed(futures):
            results.append(futures[future],)
        for case_result in results:
            frame, status = case_result.result()
            statuses.append(status)
            if not frame.empty:
                frames.append(frame)
            print(
                f"{status['case_id']}: {status['status']} "
                f"({status['record_count']} records)"
            )
    statuses.sort(key=lambda s: s['case_id'])

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    status_path = Path(args.status)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "cases_requested": int(cases["case_id"].nunique()),
        "cases_with_data": int(sum(s["status"] == "available" for s in statuses)),
        "cases_empty": int(sum(s["status"] == "available_empty" for s in statuses)),
        "cases_unavailable": int(sum(s["status"] == "unavailable" for s in statuses)),
        "records": int(len(result)),
        "policy": (
            "PLSR records are preliminary evidence only. SWDI availability or "
            "absence is never converted directly into a positive or negative truth label."
        ),
        "cases": statuses,
    }
    status_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
