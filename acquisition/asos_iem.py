"""Acquire and standardize historical ASOS/METAR observations from IEM.

The IEM archive provides routine and special ASOS/METAR reports and exposes
visibility, wind/gust, temperature/dewpoint, present-weather codes, and raw
METAR text. Downloads are restricted to exact case windows and retained as raw
CSV files for reproducibility.
"""
from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
KM_PER_MILE = 1.609344


def request_observations(
    station: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timeout: int = 60,
) -> pd.DataFrame:
    start = pd.to_datetime(start, utc=True)
    end = pd.to_datetime(end, utc=True)
    end_date = (end.normalize() + pd.Timedelta(days=1)).date()

    params = [
        ("station", station),
        ("data", "all"),
        ("year1", start.year),
        ("month1", start.month),
        ("day1", start.day),
        ("year2", end_date.year),
        ("month2", end_date.month),
        ("day2", end_date.day),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "yes"),
        ("elev", "yes"),
        ("missing", "M"),
        ("trace", "T"),
        ("direct", "no"),
        ("report_type", 3),  # routine/hourly
        ("report_type", 4),  # specials
    ]
    response = requests.get(BASE, params=params, timeout=timeout)
    response.raise_for_status()

    frame = pd.read_csv(StringIO(response.text), na_values=["M", "T", ""])
    if "valid" not in frame.columns:
        raise ValueError(f"IEM response for {station} lacks valid timestamp column")

    frame["valid"] = pd.to_datetime(frame["valid"], utc=True, errors="coerce")
    frame = frame[(frame["valid"] >= start) & (frame["valid"] <= end)].copy()
    return standardize(frame)


def _numeric(frame: pd.DataFrame, source: str, target: str):
    if source in frame.columns:
        frame[target] = pd.to_numeric(frame[source], errors="coerce")


def standardize(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    _numeric(out, "vsby", "visibility_mi")
    if "visibility_mi" in out:
        out["visibility_m"] = out["visibility_mi"] * KM_PER_MILE * 1000.0
        out["visibility_le_0p8km"] = out["visibility_m"] <= 800.0
        out["visibility_le_0p4km"] = out["visibility_m"] <= 400.0

    _numeric(out, "sknt", "wind_speed_kt")
    _numeric(out, "gust", "wind_gust_kt")
    _numeric(out, "peak_wind_gust", "peak_wind_gust_kt")
    _numeric(out, "drct", "wind_direction_deg")
    _numeric(out, "tmpf", "temperature_f")
    _numeric(out, "dwpf", "dewpoint_f")
    _numeric(out, "relh", "rh_pct")

    if "station" not in out.columns:
        raise ValueError("IEM response lacks station column")
    if "valid" not in out.columns:
        raise ValueError("IEM response lacks valid column")

    columns = [
        "station", "valid", "report_type",
        "visibility_mi", "visibility_m",
        "visibility_le_0p8km", "visibility_le_0p4km",
        "wind_direction_deg", "wind_speed_kt", "wind_gust_kt",
        "peak_wind_gust_kt", "temperature_f", "dewpoint_f", "rh_pct",
        "wxcodes", "metar", "lat", "lon", "elevation",
    ]
    keep = [c for c in columns if c in out.columns]
    return out[keep].sort_values("valid").reset_index(drop=True)


def download_cases(
    cases_csv: Path,
    output_root: Path,
    buffer_before_minutes: int = 120,
    buffer_after_minutes: int = 150,
):
    cases = pd.read_csv(cases_csv)
    required = {"case_id", "event_start_utc", "observing_station"}
    missing = required - set(cases.columns)
    if missing:
        raise ValueError(f"Case manifest missing required fields: {sorted(missing)}")

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for row in cases.drop_duplicates("case_id").itertuples(index=False):
        event_start = pd.to_datetime(row.event_start_utc, utc=True)
        start = event_start - pd.Timedelta(minutes=buffer_before_minutes)
        end = start + pd.Timedelta(minutes=buffer_before_minutes + buffer_after_minutes)
        # Correct the interval to be relative to the published event start.
        start = event_start - pd.Timedelta(minutes=buffer_before_minutes)
        end = event_start + pd.Timedelta(
            minutes=float(getattr(row, "vis_below_0p8_min", 60) or 60) + buffer_after_minutes
        )

        station = str(row.observing_station)
        data = request_observations(station, start, end)
        path = output_root / station / f"{row.case_id}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(path, index=False)

        manifest_rows.append(
            {
                "case_id": row.case_id,
                "station": station,
                "start_utc": start.isoformat().replace("+00:00", "Z"),
                "end_utc": end.isoformat().replace("+00:00", "Z"),
                "row_count": len(data),
                "output": str(path),
            }
        )
        print(f"{row.case_id} {station}: {len(data)} surface observations")

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(output_root / "surface_download_manifest.csv", index=False)
    print(f"Wrote {len(manifest)} surface observation case files")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--buffer-before", type=int, default=120)
    parser.add_argument("--buffer-after", type=int, default=150)
    args = parser.parse_args()

    download_cases(
        Path(args.cases),
        Path(args.output),
        buffer_before_minutes=args.buffer_before,
        buffer_after_minutes=args.buffer_after,
    )


if __name__ == "__main__":
    main()
