"""Acquire NCEI Storm Events records for snow-squall truth/QC.

Storm Events is treated as an authoritative validated event source, but NOT as
the sole verification source. Raw LSR evidence, radar/object timing, and
surface observations remain separate evidence streams.

The NCEI bulk archive publishes annual detail CSVs. We download only requested
years, filter to VT/NY, and retain candidate high-wind/heavy-snow/snow-squall
records plus provenance. This intentionally does not convert every record into
a positive label.
"""

from __future__ import annotations

import argparse
import gzip
import io
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles"
EVENT_TYPES = {
    "Snow Squall",
    "Thunderstorm Wind",
    "High Wind",
    "Strong Wind",
    "Heavy Snow",
    "Blizzard",
    "Winter Storm",
    "Winter Weather",
}
STATES = {"VT", "NY"}


def url_for_year(year: int) -> str:
    return f"{BASE}/StormEvents_details-ftp_v1.0_d{year}_c20260323.csv.gz"


def load_year(year: int, timeout: int = 120) -> pd.DataFrame:
    response = requests.get(url_for_year(year), timeout=timeout)
    response.raise_for_status()
    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as fh:
        return pd.read_csv(fh, low_memory=False)


def filter_candidates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    state = out.get("STATE", pd.Series("", index=out.index)).astype(str).str.upper()
    event = out.get("EVENT_TYPE", pd.Series("", index=out.index)).astype(str).str.strip()
    out = out[state.isin(STATES) & event.isin(EVENT_TYPES)].copy()
    keep = [
        "BEGIN_YEARMONTH", "BEGIN_DAY", "BEGIN_TIME", "END_YEARMONTH",
        "END_DAY", "END_TIME", "EVENT_ID", "STATE", "CZ_TYPE", "CZ_FIPS",
        "CZ_NAME", "EVENT_TYPE", "MAGNITUDE", "MAGNITUDE_TYPE",
        "BEGIN_LAT", "BEGIN_LON", "END_LAT", "END_LON",
        "SOURCE", "FLOOD_CAUSE", "EPISODE_ID", "EVENT_NARRATIVE",
        "EPISODE_NARRATIVE",
    ]
    keep = [c for c in keep if c in out.columns]
    out = out[keep]
    out.insert(0, "truth_source", "NCEI_STORM_EVENTS")
    out.insert(1, "truth_status", "official_storm_event_record")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.end_year < args.start_year:
        raise SystemExit("end year must be >= start year")

    frames = []
    for year in range(args.start_year, args.end_year + 1):
        print(f"Downloading NCEI Storm Events {year}...")
        try:
            frame = filter_candidates(load_year(year))
        except requests.HTTPError as exc:
            # Preserve an explicit acquisition failure rather than silently
            # treating a missing archive year as zero events.
            raise RuntimeError(f"NCEI Storm Events acquisition failed for {year}: {exc}") from exc
        print(f"  candidate records: {len(frame)}")
        frames.append(frame)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    print(f"Wrote {len(result)} NCEI Storm Events candidate records to {output}")


if __name__ == "__main__":
    main()
