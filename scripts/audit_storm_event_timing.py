"""Audit NCEI Storm Events against expected case timing/location without relabeling.

NCEI Storm Events begin/end times are reported in local event time. For the
BTV domain (VT/NY), this audit converts them through America/New_York before
comparing to each case's expected UTC event time.

A record can be official/validated and still be unsuitable for object-level
training if its timing or location does not agree with the observing site.
Such records are retained as evidence and flagged as timing/site mismatches.
A timing/site mismatch is never silently converted into a positive.
"""

from __future__ import annotations

import argparse
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

CASE_RADIUS_KM = 100.0
TIMING_TOLERANCE_MIN = 30.0
DOMAIN_TZ = ZoneInfo("America/New_York")


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _event_times(subset: pd.DataFrame) -> pd.Series:
    begin = pd.to_datetime(
        subset["BEGIN_YEARMONTH"].astype("Int64").astype(str),
        format="%Y%m",
        errors="coerce",
    )
    day = pd.to_numeric(subset["BEGIN_DAY"], errors="coerce")
    raw_time = pd.to_numeric(subset["BEGIN_TIME"], errors="coerce").fillna(0)
    local_naive = (
        begin
        + pd.to_timedelta(day - 1, unit="D")
        + pd.to_timedelta((raw_time // 100), unit="h")
        + pd.to_timedelta((raw_time % 100), unit="m")
    )
    return local_naive.dt.tz_localize(
        DOMAIN_TZ, ambiguous="NaT", nonexistent="NaT"
    ).dt.tz_convert("UTC")


def _load_station_locations(path: str | None) -> dict[str, tuple[float, float]]:
    if not path:
        return {}
    stations = pd.read_csv(path)
    required = {"station", "lat", "lon"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(
            f"Station location file is missing required columns: {sorted(missing)}"
        )
    return {
        str(row.station).strip().upper(): (float(row.lat), float(row.lon))
        for row in stations.itertuples(index=False)
        if pd.notna(row.lat) and pd.notna(row.lon)
    }


def audit(
    events: pd.DataFrame,
    cases: pd.DataFrame,
    station_locations: dict[str, tuple[float, float]] | None = None,
) -> pd.DataFrame:
    rows = []
    station_locations = station_locations or {}

    # Keep the event classes acquired by the truth-candidate collector. The
    # timing/site audit is deliberately broader than a final snow-squall label:
    # it is an evidence reconciliation layer, not the final outcome labeler.
    eligible_types = {
        "Snow Squall",
        "Thunderstorm Wind",
        "High Wind",
        "Strong Wind",
        "Winter Weather",
        "Heavy Snow",
        "Blizzard",
        "Winter Storm",
    }

    subset = events[
        events["EVENT_TYPE"].astype(str).str.strip().isin(eligible_types)
    ].copy()
    subset["_begin_utc"] = _event_times(subset)

    for case in cases.itertuples(index=False):
        expected = pd.Timestamp(case.event_start_utc, tz="UTC")
        station = str(getattr(case, "observing_station", "") or "").strip().upper()
        site_lat, site_lon = station_locations.get(station, (None, None))

        window = subset[
            subset["_begin_utc"].between(
                expected - pd.Timedelta(hours=6),
                expected + pd.Timedelta(hours=6),
            )
        ].copy()

        for _, event in window.iterrows():
            begin_utc = event["_begin_utc"]
            offset = (
                (begin_utc - expected).total_seconds() / 60.0
                if pd.notna(begin_utc)
                else None
            )

            event_lat = pd.to_numeric(
                pd.Series([event.get("BEGIN_LAT")]), errors="coerce"
            ).iloc[0]
            event_lon = pd.to_numeric(
                pd.Series([event.get("BEGIN_LON")]), errors="coerce"
            ).iloc[0]

            distance = None
            if (
                site_lat is not None
                and site_lon is not None
                and pd.notna(event_lat)
                and pd.notna(event_lon)
            ):
                distance = distance_km(
                    float(event_lat),
                    float(event_lon),
                    float(site_lat),
                    float(site_lon),
                )

            timing_ok = (
                offset is not None and abs(offset) <= TIMING_TOLERANCE_MIN
            )
            site_ok = (
                distance is not None and distance <= CASE_RADIUS_KM
                if distance is not None
                else None
            )

            if timing_ok and site_ok is True:
                evidence_status = "timing_and_site_consistent"
            elif timing_ok and site_ok is False:
                evidence_status = "verified_but_site_mismatch"
            elif not timing_ok and site_ok is True:
                evidence_status = "verified_but_timing_mismatch"
            elif not timing_ok and site_ok is False:
                evidence_status = "timing_and_site_mismatch"
            else:
                evidence_status = "timing_or_site_unresolved"

            rows.append(
                {
                    "case_id": case.case_id,
                    "observing_station": station,
                    "event_id": event.get("EVENT_ID"),
                    "event_type": event.get("EVENT_TYPE"),
                    "event_state": event.get("STATE"),
                    "event_source": event.get("SOURCE"),
                    "event_start_utc": (
                        begin_utc.isoformat() if pd.notna(begin_utc) else None
                    ),
                    "expected_event_start_utc": expected.isoformat(),
                    "timing_offset_min": offset,
                    "event_lat": event_lat,
                    "event_lon": event_lon,
                    "site_lat": site_lat,
                    "site_lon": site_lon,
                    "site_distance_km": distance,
                    "timing_consistent": timing_ok,
                    "site_consistent": site_ok,
                    "evidence_status": evidence_status,
                    "training_truth_eligible": bool(
                        timing_ok and site_ok is True
                    ),
                }
            )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--stations")
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    events = pd.read_csv(args.events)
    cases = pd.read_csv(args.cases)
    stations = _load_station_locations(args.stations)
    result = audit(events, cases, stations)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)

    if result.empty:
        status_counts = {}
    else:
        status_counts = {
            str(k): int(v)
            for k, v in result["evidence_status"].value_counts(dropna=False).items()
        }

    summary = {
        "candidate_matches": int(len(result)),
        "timing_consistent": int(result["timing_consistent"].fillna(False).sum())
        if not result.empty
        else 0,
        "site_consistent": int(result["site_consistent"].fillna(False).sum())
        if not result.empty
        else 0,
        "training_truth_eligible": int(
            result["training_truth_eligible"].fillna(False).sum()
        )
        if not result.empty
        else 0,
        "timing_mismatch": int(
            (~result["timing_consistent"].fillna(False)).sum()
        )
        if not result.empty
        else 0,
        "site_mismatch": int(
            (~result["site_consistent"].fillna(False)).sum()
        )
        if not result.empty
        else 0,
        "evidence_status_counts": status_counts,
        "station_locations_loaded": len(stations),
        "policy": (
            "Official NCEI records are retained as evidence. A timing or site "
            "mismatch is not converted into a positive or negative automatically; "
            "site-specific verification requires agreement with the expected "
            "observing site and event window."
        ),
    }
    Path(args.summary).write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
