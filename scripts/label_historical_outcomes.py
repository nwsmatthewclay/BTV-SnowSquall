"""Create leakage-safe future-outcome labels for reconstructed object scans.

Labels are attached only when an object is temporally and spatially relevant to
a verified Banacos event. Event metadata provide onset plus the documented
minimum duration below the 0.8-km visibility threshold; records outside that
verified interval remain negative/unknown rather than being assumed positive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd

STATIONS = {
    "KBTV": (44.471955, -73.153276),
    "KMPV": (44.203489, -72.562096),
    "KMSS": (44.936241, -74.845120),
}

HORIZONS = (15, 30, 45, 60)
ASSOCIATION_RADIUS_KM = 75.0


def parse_time(value):
    if not value or pd.isna(value):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def event_end(case):
    # Cases are namedtuples from itertuples(), not dictionaries.
    start = parse_time(getattr(case, "event_start_utc", None))
    duration = getattr(case, "vis_below_0p8_min", None)
    if start is None or duration is None or pd.isna(duration):
        return None
    return start + timedelta(minutes=float(duration))


def build_labels(df: pd.DataFrame, cases_csv: Path):
    cases = pd.read_csv(cases_csv)
    case_rows = {row.case_id: row for row in cases.itertuples(index=False)}

    out = df.copy()
    out["scan_dt"] = pd.to_datetime(out["scan_time_utc"], utc=True, errors="coerce")

    for horizon in HORIZONS:
        out[f"squall_onset_within_{horizon}m"] = 0
        out[f"squall_ongoing_within_{horizon}m"] = 0
        out[f"label_confidence_{horizon}m"] = "unknown"

    out["label_status"] = "unknown"
    out["label_reason"] = "no_verified_event_association"

    for idx, row in out.iterrows():
        case_id = row.get("case_id")
        if pd.isna(case_id) or case_id not in case_rows:
            continue

        case = case_rows[case_id]
        station = getattr(case, "observing_station", None)
        if station not in STATIONS or pd.isna(row.get("centroid_lat")) or pd.isna(row.get("centroid_lon")):
            continue

        station_lat, station_lon = STATIONS[station]
        distance = distance_km(
            float(row["centroid_lat"]),
            float(row["centroid_lon"]),
            station_lat,
            station_lon,
        )
        out.at[idx, "case_station_distance_km"] = distance

        if distance > ASSOCIATION_RADIUS_KM:
            out.at[idx, "label_status"] = "unassociated_object"
            out.at[idx, "label_reason"] = "outside_station_association_radius"
            continue

        scan = row["scan_dt"].to_pydatetime().astimezone(timezone.utc)
        start = parse_time(case.event_start_utc)
        end = event_end(case)

        # Onset labels are prospective: only the future is allowed.
        for horizon in HORIZONS:
            future_end = scan + timedelta(minutes=horizon)
            if start is not None and scan < start <= future_end:
                out.at[idx, f"squall_onset_within_{horizon}m"] = 1
                out.at[idx, f"label_confidence_{horizon}m"] = "verified_onset"

            # Ongoing-event label requires a documented visibility interval.
            if end is not None and scan < end and end > scan:
                if start <= scan:
                    out.at[idx, f"squall_ongoing_within_{horizon}m"] = 1
                    out.at[idx, f"label_confidence_{horizon}m"] = "verified_visibility_interval"

        if start is not None and scan >= start and (end is None or scan < end):
            out.at[idx, "label_status"] = "verified_event_interval"
            out.at[idx, "label_reason"] = "object_near_observing_station_during_verified_event_interval"
        elif start is not None and scan < start and any(
            out.at[idx, f"squall_onset_within_{h}m"] for h in HORIZONS
        ):
            out.at[idx, "label_status"] = "prospective_positive"
            out.at[idx, "label_reason"] = "object_near_observing_station_before_verified_onset"
        else:
            out.at[idx, "label_status"] = "case_associated_nonimpact"
            out.at[idx, "label_reason"] = "outside_verified_onset_or_visibility_interval"

    out.drop(columns=["scan_dt"], inplace=True)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", default="data/manifests/banacos_2014_cases.csv")
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)
    result = build_labels(df, Path(args.cases))
    result.to_csv(args.output, index=False)

    print(f"Wrote {len(result)} labeled object-timestep records to {args.output}")
    for horizon in HORIZONS:
        print(
            f"{horizon}m prospective positives:",
            int(result[f"squall_onset_within_{horizon}m"].sum()),
        )


if __name__ == "__main__":
    main()
