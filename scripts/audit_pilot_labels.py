"""Audit positive-label distribution by historical case for a completed pilot artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from math import asin, cos, radians, sin, sqrt

import pandas as pd

STATIONS = {
    "KBTV": (44.471955, -73.153276),
    "KMPV": (44.203489, -72.562096),
    "KMSS": (44.936241, -74.845120),
}

def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("labeled_csv")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    d = pd.read_csv(args.labeled_csv)
    cases = pd.read_csv(args.cases)
    case_lookup = (
        cases.drop_duplicates("case_id", keep="first")
        .set_index("case_id")
        .to_dict("index")
    )
    horizons = (15, 30, 45, 60)
    rows = []
    nearest_rows = []

    for case_id, g in d.groupby("case_id", dropna=False, sort=True):
        row = {
            "case_id": None if pd.isna(case_id) else str(case_id),
            "records": int(len(g)),
            "track_associated_records": int(g["track_event_associated"].fillna(False).sum()),
        }
        for h in horizons:
            target = f"squall_onset_within_{h}m"
            row[f"positive_{h}m"] = int(g[target].fillna(0).eq(1).sum())
        rows.append(row)

        case = case_lookup.get(case_id)
        station_value = case.get("observing_station") if case else None
        onset_value = case.get("event_start_utc") if case else None
        station = str(station_value) if pd.notna(station_value) else None
        onset_text = str(onset_value) if pd.notna(onset_value) else None
        if station in STATIONS and onset_text:
            onset = pd.to_datetime(onset_text, utc=True, errors="coerce")
            work = g.copy()
            work["scan_dt"] = pd.to_datetime(work["scan_time_utc"], utc=True, errors="coerce")
            work["onset_offset_min"] = (work["scan_dt"] - onset).abs().dt.total_seconds().div(60.0)
            work["station_distance_km"] = work.apply(
                lambda r: distance_km(
                    float(r["centroid_lat"]), float(r["centroid_lon"]),
                    STATIONS[station][0], STATIONS[station][1],
                ) if pd.notna(r["centroid_lat"]) and pd.notna(r["centroid_lon"]) else float("nan"),
                axis=1,
            )
            for radar_site, rg in work.groupby("radar_site", dropna=False):
                rg = rg.dropna(subset=["station_distance_km", "onset_offset_min"])
                if rg.empty:
                    continue
                best = rg.sort_values(["onset_offset_min", "station_distance_km"]).iloc[0]
                nearest_rows.append({
                    "case_id": None if pd.isna(case_id) else str(case_id),
                    "radar_site": None if pd.isna(radar_site) else str(radar_site),
                    "station": station,
                    "nearest_distance_km": round(float(rg["station_distance_km"].min()), 2),
                    "closest_onset_window_distance_km": round(float(
                        rg.loc[rg["onset_offset_min"] <= 18, "station_distance_km"].min()
                    ), 2) if (rg["onset_offset_min"] <= 18).any() else None,
                    "closest_onset_offset_min": round(float(best["onset_offset_min"]), 2),
                    "track_associated": bool(g.loc[g["radar_site"] == radar_site, "track_event_associated"].fillna(False).any()),
                })

    summary = {
        "records": int(len(d)),
        "unique_case_ids": int(d["case_id"].nunique(dropna=True)),
        "cases": rows,
        "nearest_case_radar_diagnostics": nearest_rows,
        "overall": {
            f"positive_{h}m": int(d[f"squall_onset_within_{h}m"].fillna(0).eq(1).sum())
            for h in horizons
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("Positive-label distribution by case")
    print(pd.DataFrame(rows).to_string(index=False))
    print("Nearest case/radar diagnostics")
    if nearest_rows:
        print(pd.DataFrame(nearest_rows).to_string(index=False))
    else:
        print("none")
    print("Overall:", json.dumps(summary["overall"], sort_keys=True))


if __name__ == "__main__":
    main()
