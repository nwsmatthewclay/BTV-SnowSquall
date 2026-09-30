"""Select a geographically and seasonally diverse national SQW radar pool."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def haversine_km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    if any(v is None for v in (lat1, lon1, lat2, lon2)):
        return None
    p1, p2 = radians(float(lat1)), radians(float(lat2))
    dp = radians(float(lat2) - float(lat1))
    dl = radians(float(lon2) - float(lon1))
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371.0 * 2.0 * asin(min(1.0, sqrt(a)))


def radar_locations():
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS
    except Exception as exc:
        raise RuntimeError(f"Py-ART NEXRAD location table unavailable: {exc}") from exc
    return {
        site: (float(meta["lat"]), float(meta["lon"]), float(meta["elev"]))
        for site, meta in NEXRAD_LOCATIONS.items()
        if site.upper().startswith("K")
        and len(site) == 4
        and isinstance(meta, dict)
        and meta.get("lat") is not None
        and meta.get("lon") is not None
    }


def choose_diverse(frame: pd.DataFrame, limit: int, offset: int = 0) -> pd.DataFrame:
    if frame.empty or limit <= 0:
        return frame.iloc[0:0].copy()
    d = frame.copy()
    d["dt"] = pd.to_datetime(d["warning_issue_utc"], utc=True, errors="coerce")
    d = d.dropna(subset=["dt", "lat", "lon"]).copy()
    d["year"] = d["dt"].dt.year
    d["month"] = d["dt"].dt.month
    d = d[d["lat"].between(30, 55) & d["lon"].between(-130, -60)]
    d = d[d["month"].isin([10, 11, 12, 1, 2, 3, 4])]
    groups = []
    for (_, _), group in d.groupby(["year", "wfo"], sort=True):
        group = group.sort_values(
            ["iem_verified", "verifying_lsr_count", "warning_issue_utc"],
            ascending=[False, False, True],
            kind="stable",
        )
        groups.append(group)
    ordered = []
    cursors = {i: 0 for i in range(len(groups))}
    while True:
        progressed = False
        for i, group in enumerate(groups):
            idx = cursors[i]
            if idx >= len(group):
                continue
            ordered.append(group.iloc[idx])
            cursors[i] += 1
            progressed = True
            if len(ordered) >= offset + limit:
                break
        if not progressed or len(ordered) >= offset + limit:
            break
    return pd.DataFrame(ordered).iloc[offset:offset + limit].copy()


def attach_radars(frame, locations, max_radars: int, max_range_km: float):
    rows = []
    for _, row in frame.iterrows():
        choices = []
        for site, (lat, lon, elev) in locations.items():
            dist = haversine_km(row["lat"], row["lon"], lat, lon)
            if dist is not None and dist <= max_range_km:
                choices.append((dist, site, lat, lon, elev))
        choices.sort(key=lambda item: item[0])
        for dist, site, rlat, rlon, _ in choices[:max_radars]:
            warning_time = pd.Timestamp(row["warning_issue_utc"], tz="UTC")
            rows.append({
                "case_id": row["case_id"],
                "radar_site": site,
                "event_start_utc": row["warning_issue_utc"],
                "event_end_utc": row.get("warning_expire_utc"),
                "warning_issue_utc": row["warning_issue_utc"],
                "lat": float(row["lat"]) if pd.notna(row.get("lat")) else None,
                "lon": float(row["lon"]) if pd.notna(row.get("lon")) else None,
                "window_start_utc": (warning_time - pd.Timedelta(minutes=90)).isoformat().replace("+00:00", "Z"),
                "window_end_utc": (warning_time + pd.Timedelta(minutes=150)).isoformat().replace("+00:00", "Z"),
                "radar_distance_km": round(float(dist), 1),
                "radar_lat": rlat,
                "radar_lon": rlon,
                "warning_wfo": row.get("wfo"),
                "iem_verified": bool(row.get("iem_verified", False)),
                "verifying_lsr_count": int(row.get("verifying_lsr_count", 0) or 0),
                "supervision_class": row.get("supervision_class"),
            })
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--episodes", default=None, help="Optional national SQW episode table for leakage-safe episode grouping.")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-verified", type=int, default=60)
    p.add_argument("--max-unverified", type=int, default=30)
    p.add_argument("--verified-offset", type=int, default=0)
    p.add_argument("--unverified-offset", type=int, default=0)
    p.add_argument("--max-radars", type=int, default=2)
    p.add_argument("--max-range-km", type=float, default=230.0)
    a = p.parse_args()
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    d = pd.read_csv(a.input)
    if a.episodes:
        episodes = pd.read_csv(a.episodes)
        episode_map = {}
        for _, episode in episodes.iterrows():
            for case_id in str(episode.get("case_ids", "")).split(";"):
                if case_id and case_id != "nan":
                    episode_map[case_id] = episode.get("episode_id")
        d["episode_id"] = d["case_id"].map(episode_map)
    else:
        d["episode_id"] = d["case_id"]
    verified = d[d["iem_verified"].fillna(False)].copy()
    review = d[~d["iem_verified"].fillna(False)].copy()

    verified = choose_diverse(verified, a.max_verified, a.verified_offset)
    review = choose_diverse(review, a.max_unverified, a.unverified_offset)
    selected = pd.concat([verified, review], ignore_index=True)

    radars = attach_radars(selected, radar_locations(), a.max_radars, a.max_range_km)

    verified.to_csv(out / "national_sqw_verified_selection.csv", index=False)
    review.to_csv(out / "national_sqw_review_selection.csv", index=False)
    radars.to_csv(out / "national_sqw_radar_manifest.csv", index=False)

    summary = {
        "verified_selected": int(len(verified)),
        "review_selected": int(len(review)),
        "radar_manifest_rows": int(len(radars)),
        "radar_sites": sorted(radars["radar_site"].dropna().unique().tolist()) if not radars.empty else [],
        "season_policy": "October-April; continental-CONUS-oriented geographic bounds for snow-focused pretraining.",
        "training_policy": "IEM-verified warnings are weak supervision until radar/surface review confirms physical event truth; warning-only cases remain review-only.",
    }
    (out / "national_sqw_radar_selection_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

# trigger: episode-aware national sampling
