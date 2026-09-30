"""Select a reproducible expanded snow-squall case pool from discovery output."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.assign_truth_tier import assign as assign_truth_tier

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
    for (year, evidence), group in work.groupby(["year", "verification_class"], sort=True):
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
    parser.add_argument("--exclude-modern-validation", default=None, help="Modern validation manifest whose analysis windows must remain out of training.")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_csv(args.input)
    radar = pd.read_csv(args.radar_manifest)
    if candidates.empty:
        raise ValueError("Discovery produced no candidates.")
    radar_ids = set(radar["candidate_id"].astype(str)) if "candidate_id" in radar.columns else set()
    if args.exclude_modern_validation:
        holdout = pd.read_csv(args.exclude_modern_validation)
        holdout_ids = set(holdout.get("case_id", pd.Series(dtype="object")).dropna().astype(str))
        if "candidate_id" in holdout.columns:
            holdout_ids.update(holdout["candidate_id"].dropna().astype(str))
        candidates = candidates[~candidates["candidate_id"].astype(str).isin(holdout_ids)].copy()
    candidates = candidates[candidates["candidate_id"].astype(str).isin(radar_ids)].copy()
    if candidates.empty:
        raise ValueError("No candidates have usable radar coverage.")

    if args.exclude_modern_validation:
        modern = pd.read_csv(args.exclude_modern_validation)
        event_time = pd.to_datetime(candidates["event_start_utc"], utc=True, errors="coerce")
        masks = []
        for _, row in modern.iterrows():
            start = pd.to_datetime(row.get("analysis_window_start_utc"), utc=True, errors="coerce")
            end = pd.to_datetime(row.get("analysis_window_end_utc"), utc=True, errors="coerce")
            if pd.notna(start) and pd.notna(end):
                masks.append(event_time.between(start, end, inclusive="both"))
        if masks:
            exclude_mask = pd.concat(masks, axis=1).any(axis=1)
            print("Excluding modern validation-window candidates:", int(exclude_mask.sum()))
            candidates = candidates.loc[~exclude_mask].copy()

    radar_candidate_ids = set(radar["candidate_id"].dropna().astype(str)) if not radar.empty else set()
    before_radar_filter = len(candidates)
    candidates = candidates[candidates["candidate_id"].astype(str).isin(radar_candidate_ids)].copy()
    if candidates.empty:
        raise ValueError("No discovery candidates have a radar acquisition path.")

    official = candidates[
        candidates["verification_class"].isin(
            ["official_documented", "official_plus_independent_report", "official_plus_warning", "official_plus_warning_and_report", "official_plus_warning_verified", "official_study_warning_verified", "official_plus_study", "study_verified", "study_warning_verified"]
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
    selected = assign_truth_tier(selected)
    selected["case_id"] = selected["candidate_id"]
    selected["source_study"] = "expanded_ncei_iem_case_discovery"
    tier_map = {
        "official_documented": ("B", 0.70),
        "official_plus_independent_report": ("A-", 0.90),
        "official_plus_warning": ("B+", 0.85),
        "official_plus_warning_and_report": ("A-", 0.90),
        "official_plus_warning_verified": ("B+", 0.85),
        "official_study_warning_verified": ("A+", 1.00),
        "official_plus_study": ("A+", 1.00),
        "study_verified": ("A", 1.00),
        "study_warning_verified": ("A+", 1.00),
        "warning_verified": ("B+", 0.85),
        "warning_only": ("C", 0.45),
        "warning_plus_report": ("C+", 0.55),
        "unverified_report_only": ("D", 0.25),
        "official_screening_candidate": ("D", 0.20),
    }
    selected["truth_tier"] = selected["verification_class"].map(lambda x: tier_map.get(x, ("D", 0.10))[0])
    selected["evidence_weight"] = selected["verification_class"].map(lambda x: tier_map.get(x, ("D", 0.10))[1])

    selected["observing_station"] = [
        nearest_station(lat, lon)
        for lat, lon in zip(selected["lat"], selected["lon"])
    ]
    selected["case_lat"] = pd.to_numeric(selected["lat"], errors="coerce")
    selected["case_lon"] = pd.to_numeric(selected["lon"], errors="coerce")
    selected["case_coordinate_precision"] = selected.get("coordinate_precision", pd.Series("", index=selected.index)).fillna("")
    selected["case_event_end_utc"] = selected.get("event_end_utc", pd.Series(pd.NA, index=selected.index))
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
        "discovery_candidates_before_radar_filter": int(before_radar_filter),
        "discovery_candidates_with_radar_path": int(len(candidates)),
        "official_selected": int(len(official)),
        "unverified_selected": int(len(unverified)),
        "total_selected": int(len(selected)),
        "radar_manifest_rows": int(len(selected_radar)),
        "official_case_ids": sorted(official["candidate_id"].astype(str).tolist()),
        "unverified_case_ids": sorted(unverified["candidate_id"].astype(str).tolist()),
        "training_policy": "Explicit NCEI/study-documented cases and multi-source official/study cases may enter the first expanded positive-label research training pass. warning_verified-only, warning_only, warning_plus_report, screening, and report-only candidates remain a weak/review feature-population pool until onset timing is independently verified.",
    }
    import json
    (out / "snow_squall_expansion_selection.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
