"""Audit NCEI Storm Events against expected case timing/location without relabeling.

A record can be official/validated and still be unsuitable for object-level
training if its timing or location does not agree with the radar case. Such
records are retained as evidence but flagged as timing/site mismatches.
"""

from __future__ import annotations

import argparse
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd

CASE_RADIUS_KM = 100.0
TIMING_TOLERANCE_MIN = 30.0


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def audit(events: pd.DataFrame, cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for case in cases.itertuples(index=False):
        expected = pd.Timestamp(case.event_start_utc, tz="UTC")
        case_lat = getattr(case, "observing_lat", None)
        case_lon = getattr(case, "observing_lon", None)

        subset = events[
            events["EVENT_TYPE"].astype(str).str.strip().isin(
                ["Snow Squall", "Winter Weather", "Heavy Snow", "Blizzard", "Winter Storm"]
            )
        ].copy()

        begin = pd.to_datetime(
            subset.get("BEGIN_YEARMONTH", pd.Series(dtype="float")),
            format="%Y%m",
            errors="coerce",
        )
        if begin.empty:
            continue

        # Reconstruct local event timestamp as best available from NCEI fields.
        day = pd.to_numeric(subset.get("BEGIN_DAY"), errors="coerce")
        hour = pd.to_numeric(subset.get("BEGIN_TIME"), errors="coerce").fillna(0)
        subset["_begin_date"] = begin + pd.to_timedelta(day - 1, unit="D")
        subset["_begin_hour"] = (hour // 100).astype("Int64")
        subset["_begin_minute"] = (hour % 100).astype("Int64")
        subset["_begin_utc_approx"] = pd.to_datetime(
            subset["_begin_date"].dt.strftime("%Y-%m-%d")
            + " "
            + subset["_begin_hour"].astype(str)
            + ":"
            + subset["_begin_minute"].astype(str),
            errors="coerce",
            utc=True,
        )

        window = subset[
            subset["_begin_utc_approx"].between(
                expected - pd.Timedelta(hours=6),
                expected + pd.Timedelta(hours=6),
            )
        ].copy()

        for row in window.itertuples(index=False):
            offset = (
                (row._begin_utc_approx - expected).total_seconds() / 60.0
                if pd.notna(row._begin_utc_approx) else None
            )
            distance = None
            if (
                case_lat is not None and case_lon is not None
                and pd.notna(getattr(row, "BEGIN_LAT", None))
                and pd.notna(getattr(row, "BEGIN_LON", None))
            ):
                distance = distance_km(
                    float(row.BEGIN_LAT), float(row.BEGIN_LON),
                    float(case_lat), float(case_lon),
                )

            rows.append({
                "case_id": case.case_id,
                "event_id": getattr(row, "EVENT_ID", None),
                "event_type": getattr(row, "EVENT_TYPE", None),
                "event_state": getattr(row, "STATE", None),
                "event_source": getattr(row, "SOURCE", None),
                "event_start_utc_approx": (
                    row._begin_utc_approx.isoformat()
                    if pd.notna(row._begin_utc_approx) else None
                ),
                "expected_event_start_utc": expected.isoformat(),
                "timing_offset_min": offset,
                "site_distance_km": distance,
                "timing_consistent": (
                    offset is not None and abs(offset) <= TIMING_TOLERANCE_MIN
                ),
                "site_consistent": (
                    distance is not None and distance <= CASE_RADIUS_KM
                ) if distance is not None else None,
                "training_truth_eligible": bool(
                    offset is not None and abs(offset) <= TIMING_TOLERANCE_MIN
                    and (distance is None or distance <= CASE_RADIUS_KM)
                ),
            })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    events = pd.read_csv(args.events)
    cases = pd.read_csv(args.cases)
    result = audit(events, cases)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)

    summary = {
        "candidate_matches": int(len(result)),
        "timing_consistent": int(result["timing_consistent"].fillna(False).sum()) if not result.empty else 0,
        "site_consistent": int(result["site_consistent"].fillna(False).sum()) if not result.empty else 0,
        "training_truth_eligible": int(result["training_truth_eligible"].fillna(False).sum()) if not result.empty else 0,
        "timing_mismatch": int((~result["timing_consistent"].fillna(False)).sum()) if not result.empty else 0,
        "site_mismatch": int((~result["site_consistent"].fillna(False)).sum()) if not result.empty else 0,
        "policy": (
            "Official NCEI records are retained as evidence. Timing/site mismatches "
            "are not converted into negatives or positives automatically."
        ),
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
