"""Create leakage-safe future-outcome labels for reconstructed object scans."""
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
PRE_EVENT_ASSOCIATION_MIN = 90
POST_EVENT_ASSOCIATION_MIN = 30
ASSOCIATION_ONSET_WINDOW_MIN = 18
ASSOCIATION_FALLBACK_WINDOW_MIN = 45


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
    start = parse_time(getattr(case, "event_start_utc", None))
    duration = getattr(case, "vis_below_0p8_min", None)
    if start is None or duration is None or pd.isna(duration):
        return None
    return start + timedelta(minutes=float(duration))


def _track_key(case_id, radar_site, object_id):
    return (case_id, radar_site, object_id)


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
    out["track_event_distance_km"] = pd.NA
    out["track_event_associated"] = False
    out["association_method"] = "track_station_event_corridor"

    association = {}
    for case_id, case in case_rows.items():
        station = getattr(case, "observing_station", None)
        if station not in STATIONS:
            continue
        start = parse_time(case.event_start_utc)
        if start is None:
            continue
        end = event_end(case) or (start + timedelta(minutes=60))
        corridor_start = start - timedelta(minutes=PRE_EVENT_ASSOCIATION_MIN)
        corridor_end = end + timedelta(minutes=POST_EVENT_ASSOCIATION_MIN)

        case_mask = (
            (out["case_id"] == case_id)
            & (out["scan_dt"] >= corridor_start)
            & (out["scan_dt"] <= corridor_end)
            & out["centroid_lat"].notna()
            & out["centroid_lon"].notna()
        )
        candidate = out.loc[case_mask]
        group_cols = [c for c in ("radar_site", "object_id") if c in candidate.columns]
        if not group_cols:
            continue
        # Select only the single radar track that comes closest to the
        # observing station during the onset-centered corridor for each radar.
        # This prevents multiple unrelated cells from inheriting the same event
        # label merely because they passed through a broad association radius.
        track_candidates = []
        for key_values, track in candidate.groupby(group_cols, dropna=False):
            if not isinstance(key_values, tuple):
                key_values = (key_values,)
            if "radar_site" in group_cols:
                radar_site, object_id = key_values
            else:
                radar_site, object_id = None, key_values[0]

            track = track.copy()
            track["_abs_minutes_from_onset"] = (
                (track["scan_dt"] - start).abs().dt.total_seconds().div(60.0)
            )
            track["_distance_km"] = track.apply(
                lambda r: distance_km(
                    float(r["centroid_lat"]), float(r["centroid_lon"]),
                    STATIONS[station][0], STATIONS[station][1],
                ),
                axis=1,
            )

            # Prefer tracks that are actually observed near the documented
            # onset time. A closest approach 30–90 minutes away can belong to
            # an unrelated cell that merely crosses the same station corridor.
            onset_window = track[
                track["_abs_minutes_from_onset"] <= ASSOCIATION_ONSET_WINDOW_MIN
            ]
            fallback_window = track[
                track["_abs_minutes_from_onset"] <= ASSOCIATION_FALLBACK_WINDOW_MIN
            ]
            if not onset_window.empty:
                scored = onset_window
                window_rank = 0
            elif not fallback_window.empty:
                scored = fallback_window
                window_rank = 1
            else:
                scored = track
                window_rank = 2

            best = scored.sort_values(
                ["_distance_km", "_abs_minutes_from_onset"]
            ).iloc[0]
            track_candidates.append(
                (
                    window_rank,
                    float(best["_distance_km"]),
                    float(best["_abs_minutes_from_onset"]),
                    radar_site,
                    object_id,
                )
            )

        by_radar = {}
        for window_rank, min_distance, onset_offset, radar_site, object_id in track_candidates:
            current = by_radar.get(radar_site)
            candidate_key = (window_rank, min_distance, onset_offset)
            if current is None or candidate_key < current[0]:
                by_radar[radar_site] = (
                    candidate_key,
                    min_distance,
                    object_id,
                )

        for radar_site, (_, min_distance, object_id) in by_radar.items():
            if min_distance <= ASSOCIATION_RADIUS_KM:
                association[_track_key(case_id, radar_site, object_id)] = min_distance

    for idx, row in out.iterrows():
        case_id = row.get("case_id")
        radar_site = row.get("radar_site")
        object_id = row.get("object_id")
        if pd.isna(case_id) or case_id not in case_rows:
            continue

        case = case_rows[case_id]
        station = getattr(case, "observing_station", None)
        if (
            station not in STATIONS
            or pd.isna(row.get("centroid_lat"))
            or pd.isna(row.get("centroid_lon"))
        ):
            continue

        distance = distance_km(
            float(row["centroid_lat"]), float(row["centroid_lon"]),
            STATIONS[station][0], STATIONS[station][1],
        )
        out.at[idx, "case_station_distance_km"] = distance

        track_distance = association.get(_track_key(case_id, radar_site, object_id))
        if track_distance is None:
            out.at[idx, "label_status"] = "unassociated_object"
            out.at[idx, "label_reason"] = "track_never_entered_event_association_corridor"
            continue

        out.at[idx, "track_event_distance_km"] = track_distance
        out.at[idx, "track_event_associated"] = track_distance <= ASSOCIATION_RADIUS_KM

        if track_distance > ASSOCIATION_RADIUS_KM:
            out.at[idx, "label_status"] = "unassociated_object"
            out.at[idx, "label_reason"] = "track_outside_event_association_radius"
            continue

        scan = row["scan_dt"].to_pydatetime().astimezone(timezone.utc)
        start = parse_time(case.event_start_utc)
        end = event_end(case)

        for horizon in HORIZONS:
            future_end = scan + timedelta(minutes=horizon)
            if start is not None and scan < start <= future_end:
                out.at[idx, f"squall_onset_within_{horizon}m"] = 1
                out.at[idx, f"label_confidence_{horizon}m"] = "verified_onset"

            if end is not None and scan < end and start <= scan:
                out.at[idx, f"squall_ongoing_within_{horizon}m"] = 1
                out.at[idx, f"label_confidence_{horizon}m"] = "verified_visibility_interval"

        if start is not None and scan >= start and (end is None or scan < end):
            out.at[idx, "label_status"] = "verified_event_interval"
            out.at[idx, "label_reason"] = "track_associated_with_verified_event_interval"
        elif start is not None and scan < start and any(
            out.at[idx, f"squall_onset_within_{h}m"] for h in HORIZONS
        ):
            out.at[idx, "label_status"] = "prospective_positive"
            out.at[idx, "label_reason"] = "associated_track_before_verified_onset"
        else:
            out.at[idx, "label_status"] = "case_associated_nonimpact"
            out.at[idx, "label_reason"] = "associated_track_outside_verified_onset_or_visibility_interval"

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
        print(f"{horizon}m prospective positives:", int(result[f"squall_onset_within_{horizon}m"].sum()))
    print("Track-associated object records:", int(result["track_event_associated"].sum()))

    assoc = (
        result.loc[result["track_event_associated"]]
        .groupby(["case_id", "radar_site"], dropna=False)
        .size()
        .reset_index(name="associated_object_timesteps")
    )
    if assoc.empty:
        print("Associated object timesteps by case/radar: none")
    else:
        print("Associated object timesteps by case/radar:")
        print(assoc.to_string(index=False))
        positive_by_case = (
            result.groupby("case_id", dropna=False)[
                [f"squall_onset_within_{h}m" for h in HORIZONS]
            ].sum()
        )
        positive_by_case = positive_by_case.loc[
            positive_by_case.sum(axis=1) > 0
        ]
        print("Positive onset labels by case:")
        print(
            positive_by_case.to_string()
            if not positive_by_case.empty else "none"
        )


if __name__ == "__main__":
    main()
