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
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://www.ncei.noaa.gov/swdiws/csv/plsr"
STATION_STATE = {
    "KBTV": "VT",
    "KMPV": "VT",
    "KMSS": "NY",
}
TIMEOUT_SECONDS = 60
RETRIES = 4


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


def acquire_case(case: pd.Series) -> tuple[pd.DataFrame, dict]:
    case_id = str(case["case_id"])
    station = str(case.get("observing_station", "") or "").upper().strip()
    state = STATION_STATE.get(station)
    expected = pd.Timestamp(case["event_start_utc"], tz="UTC")
    start = (expected - pd.Timedelta(days=1)).date().isoformat().replace("-", "")
    end = (expected + pd.Timedelta(days=1)).date().isoformat().replace("-", "")

    params = f"?state={state}" if state else ""
    url = f"{BASE_URL}/{start}:{end}{params}"

    status = {
        "case_id": case_id,
        "observing_station": station,
        "state": state,
        "url": url,
        "status": "unavailable",
        "record_count": 0,
        "error": None,
    }

    try:
        response = _request(url)
        text = response.text.strip()
        if not text:
            status["status"] = "available_empty"
            return pd.DataFrame(), status

        frame = pd.read_csv(io.StringIO(text))
        frame.insert(0, "case_id", case_id)
        frame.insert(1, "truth_source", "NCEI_SWDI_PLSR")
        frame.insert(2, "truth_status", "preliminary_local_storm_report")
        frame.insert(3, "observing_station", station)
        frame.insert(4, "query_expected_event_start_utc", expected.isoformat())
        frame.insert(5, "query_start_utc", (expected - pd.Timedelta(days=1)).isoformat())
        frame.insert(6, "query_end_utc", (expected + pd.Timedelta(days=1)).isoformat())
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
    args = parser.parse_args()

    cases = pd.read_csv(args.cases)
    frames = []
    statuses = []

    for _, case in cases.drop_duplicates("case_id").iterrows():
        frame, status = acquire_case(case)
        statuses.append(status)
        if not frame.empty:
            frames.append(frame)
        print(
            f"{status['case_id']}: {status['status']} "
            f"({status['record_count']} records)"
        )

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
