"""Select a reproducible expanded snow-squall case pool from discovery output."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

STATIONS = {
    "KBTV": (44.471955, -73.153276),
    "KMPV": (44.203489, -72.562096),
    "KMSS": (44.936241, -74.845120),
}

def distance_km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    if None in (lat1, lon1, lat2, lon2):
        return None
    p1, p2 = radians(float(lat1)), radians(float(lat2))
    dp = radians(float(lat2) - float(lat1))
    dl = radians(float(lon2) - float(lon1))
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371.0 * 2.0 * asin(min(1.0, sqrt(a)))

def nearest_station(lat, lon):
    choices = []
    for station, (slat, slon) in STATIONS.items():
        d = distance_km(lat, lon, slat, slon)
        if d is not None:
            choices.append((d, station))
    return min(choices)[1] if choices else "KBTV"

def choose_diverse(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    if df.empty or limit <= 0:
        return df.iloc[0:0].copy()

    work = df.copy()
    work["year"] = pd.to_datetime(work["event_start_utc"], utc=True, errors="coerce").dt.year
    work["year"] = work["year"].fillna(0).astype(int)

    ranked = []
    for year, group in work.groupby("year", sort=True):
        group = group.sort_values(
            ["lsr_count", "ncei_explicit_snow_squall", "event_start_utc"],
            ascending=[False, False, True],
            kind="stable",
        )
        ranked.append(group)

    # Round-robin by year to avoid spending the whole first batch in one season.
    selected = []
    cursors = {i: 0 for i in range(len(ranked))}
    while len(selected) < min(limit, len(work)):
        progressed = False
        for i, group in enumerate(ranked):
            idx = cursors[i]
            if idx >= len(group):
                continue
            selected.append(group.iloc[idx])
            cursors[i] += 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return pd.DataFrame(selected)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--radar-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-official", type=int, default=50)
    parser.add_argument("--max-unverified", type=int, default=50)
    parser.add_argument("--offset-official", type=int, default=0)
    parser.add_argument("--offset-unverified", type=int, default=0)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_csv(args.input)
    radar = pd.read_csv(args.radar_manifest)
    if candidates.empty:
        raise ValueError("Discovery produced no candidates.")

    official = candidates[
        candidates["verification_class"].isin(
            ["official_documented", "official_plus_independent_report", "official_plus_warning", "official_plus_warning_and_report", "official_plus_warning_verified", "official_study_warning_verified", "official_plus_study", "study_verified", "study_warning_verified", "warning_verified"]
        )
    ].copy()
    unverified = candidates[
        candidates["verification_class"].isin([
            "unverified_report_only",
            "warning_only",
            "warning_plus_report",
            "official_screening_candidate",
        ])
    ].copy()

    official = choose_diverse(official, args.offset_official + args.max_official).iloc[args.offset_official:].copy()
    unverified = choose_diverse(unverified, args.offset_unverified + args.max_unverified).iloc[args.offset_unverified:].copy()

    selected = pd.concat([official, unverified], ignore_index=True)
    selected["case_id"] = selected["candidate_id"]
    selected["source_study"] = "expanded_ncei_iem_case_discovery"
    selected["observing_station"] = [
        nearest_station(lat, lon)
        for lat, lon in zip(selected["lat"], selected["lon"])
    ]
    selected["hybrid_case"] = False
    selected["peak_wind_kt"] = pd.NA
    selected["min_visibility_km"] = pd.NA

    selected.to_csv(out / "snow_squall_expansion_cases.csv", index=False)

    chosen_ids = set(selected["candidate_id"].astype(str))
    selected_radar = radar[radar["candidate_id"].astype(str).isin(chosen_ids)].copy()
    selected_radar = selected_radar.merge(
        selected[["candidate_id", "case_id", "source_study", "observing_station"]],
        on="candidate_id",
        how="left",
    )
    selected_radar.to_csv(out / "snow_squall_expansion_radar_manifest.csv", index=False)

    summary = {
        "official_selected": int(len(official)),
        "unverified_selected": int(len(unverified)),
        "total_selected": int(len(selected)),
        "radar_manifest_rows": int(len(selected_radar)),
        "official_case_ids": sorted(official["candidate_id"].astype(str).tolist()),
        "unverified_case_ids": sorted(unverified["candidate_id"].astype(str).tolist()),
        "training_policy": "Official NCEI cases and IEM warning_verified cases may enter the first expanded positive-label research training pass. warning_only, warning_plus_report, screening, and report-only candidates remain a review/feature-population pool.",
    }
    import json
    (out / "snow_squall_expansion_selection.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
