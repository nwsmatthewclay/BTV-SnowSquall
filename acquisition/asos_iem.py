"""Download historical ASOS/METAR observations from the Iowa Environmental Mesonet."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

def download(stations, start, end, output):
    params = {
        "station": ",".join(stations),
        "data": "all",
        "year1": start.year, "month1": start.month, "day1": start.day,
        "year2": end.year, "month2": end.month, "day2": end.day,
        "tz": "Etc/UTC", "format": "onlycomma",
        "latlon": "yes", "elev": "yes", "missing": "M",
        "trace": "T", "direct": "no",
        "report_type": "3,4",
    }
    df = pd.read_csv(BASE, params=params, na_values=["M", "T", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    return df

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stations", nargs="+", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    df = download(args.stations, start, end, Path(args.output))
    print(f"Wrote {len(df):,} observations")

if __name__ == "__main__":
    main()
