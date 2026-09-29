"""Acquire NCEI Storm Events records for snow-squall truth/QC.

Storm Events is treated as an authoritative validated event source, but NOT as
the sole verification source. Raw LSR evidence, radar/object timing, and
surface observations remain separate evidence streams.

The NCEI bulk archive publishes annual detail CSVs whose creation-date suffix
can change by year. We discover the exact annual URL from the public directory
listing rather than assuming one suffix.
"""

from __future__ import annotations

import argparse
import gzip
import io
import re
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
STATE_NAMES = {"VERMONT", "NEW YORK"}


def url_for_year(year: int, timeout: int = 60) -> str:
    index_url = BASE + "/"
    response = requests.get(index_url, timeout=timeout)
    response.raise_for_status()
    pattern = re.compile(
        rf'href="(StormEvents_details-ftp_v1\.0_d{year}_c\d{{8}}\.csv\.gz)"'
    )
    match = pattern.search(response.text)
    if not match:
        raise FileNotFoundError(
            f"No NCEI Storm Events detail archive found for {year}"
        )
    return f"{BASE}/{match.group(1)}"


def load_year(year: int, timeout: int = 180) -> pd.DataFrame:
    url = url_for_year(year)
    print(f"  archive: {url}")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as fh:
        return pd.read_csv(fh, low_memory=False)


def filter_candidates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    state = out.get("STATE", pd.Series("", index=out.index)).astype(str).str.upper().str.strip()
    event = out.get("EVENT_TYPE", pd.Series("", index=out.index)).astype(str).str.strip()
    out = out[state.isin(STATE_NAMES) & event.isin(EVENT_TYPES)].copy()

    keep = [
        "BEGIN_YEARMONTH", "BEGIN_DAY", "BEGIN_TIME", "END_YEARMONTH",
        "END_DAY", "END_TIME", "EVENT_ID", "STATE", "CZ_TYPE", "CZ_FIPS",
        "CZ_NAME", "EVENT_TYPE", "MAGNITUDE", "MAGNITUDE_TYPE",
        "BEGIN_LAT", "BEGIN_LON", "END_LAT", "END_LON",
        "SOURCE", "FLOOD_CAUSE", "EPISODE_ID", "EVENT_NARRATIVE",
        "EPISODE_NARRATIVE", "LAST_DATE_MODIFIED", "LAST_DATE_CERTIFIED",
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
            raise RuntimeError(
                f"NCEI Storm Events acquisition failed for {year}: {exc}"
            ) from exc
        print(f"  candidate records: {len(frame)}")
        frames.append(frame)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    print(f"Wrote {len(result)} NCEI Storm Events candidate records to {output}")


if __name__ == "__main__":
    main()
