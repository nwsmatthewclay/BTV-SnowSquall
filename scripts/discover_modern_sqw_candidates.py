"""Discover BTV Snow Squall Warning events from the IEM VTEC archive.

This utility produces a candidate-review table only. It never promotes an event
into the independent-validation manifest automatically.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

URL = "https://mesonet.agron.iastate.edu/json/vtec_events_bywfo.py"


def discover(years: list[int], output: Path) -> pd.DataFrame:
    rows = []
    for year in years:
        params = {
            "wfo": "KBTV",
            "year": int(year),
            "phenomena": "SQ",
            "significance": "W",
        }
        response = requests.get(
            URL,
            params=params,
            headers={"User-Agent": "BTV-SnowSquall candidate discovery/1.0"},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        events = payload.get("events", payload if isinstance(payload, list) else [])
        for event in events:
            rows.append({
                "year": event.get("year", year),
                "wfo": event.get("wfo", "KBTV"),
                "event_id": event.get("eventid") or event.get("etn"),
                "phenomena": event.get("phenomena", "SQ"),
                "significance": event.get("significance", "W"),
                "issue": event.get("issue"),
                "expire": event.get("expire"),
                "states": event.get("states"),
                "event_url": event.get("uri"),
                "review_status": "candidate_review_required",
                "reconstruction_eligible": False,
            })

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["year", "wfo", "event_id", "phenomena", "significance"]
    )
    if not df.empty:
        df = df.sort_values(["year", "issue", "event_id"])
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(df.to_string(index=False))
    print(f"Discovered {len(df)} candidate events.")
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.end_year < args.start_year:
        raise SystemExit("--end-year must be >= --start-year")
    discover(list(range(args.start_year, args.end_year + 1)), Path(args.output))


if __name__ == "__main__":
    main()
