"""Map every national SQW episode to nearby true NEXRAD Level-II sites."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.select_national_sqw_radar_cases import haversine_km, radar_locations


def build(episodes_csv: Path, output_dir: Path, max_radars: int = 2, max_range_km: float = 230.0):
    episodes = pd.read_csv(episodes_csv)
    required = {
        "episode_id",
        "episode_start_utc",
        "episode_end_utc",
        "wfo",
        "warning_count",
        "verified_warning_count",
        "verifying_lsr_count",
        "lat",
        "lon",
        "case_ids",
    }
    missing = required - set(episodes.columns)
    if missing:
        raise ValueError(f"Episode inventory missing columns: {sorted(missing)}")

    locations = radar_locations()
    rows = []
    for _, episode in episodes.iterrows():
        lat, lon = episode["lat"], episode["lon"]
        if pd.isna(lat) or pd.isna(lon):
            continue
        choices = []
        for site, (rlat, rlon, elev) in locations.items():
            dist = haversine_km(lat, lon, rlat, rlon)
            if dist is not None and dist <= max_range_km:
                choices.append((dist, site, rlat, rlon))
        choices.sort(key=lambda x: x[0])
        episode_class = (
            "warning_verified_episode"
            if int(episode["verified_warning_count"] or 0) > 0
            else "warning_only_episode"
        )
        for dist, site, rlat, rlon in choices[:max_radars]:
            start = pd.Timestamp(episode["episode_start_utc"], tz="UTC") - pd.Timedelta(minutes=90)
            end = pd.Timestamp(episode["episode_end_utc"], tz="UTC") + pd.Timedelta(minutes=60)
            rows.append({
                "episode_id": episode["episode_id"],
                "case_ids": episode["case_ids"],
                "radar_site": site,
                "episode_start_utc": episode["episode_start_utc"],
                "episode_end_utc": episode["episode_end_utc"],
                "window_start_utc": start.isoformat().replace("+00:00", "Z"),
                "window_end_utc": end.isoformat().replace("+00:00", "Z"),
                "episode_lat": float(lat),
                "episode_lon": float(lon),
                "radar_distance_km": round(float(dist), 1),
                "warning_wfo": episode["wfo"],
                "warning_count": int(episode["warning_count"]),
                "verified_warning_count": int(episode["verified_warning_count"]),
                "verifying_lsr_count": int(episode["verifying_lsr_count"]),
                "episode_verification_class": episode_class,
            })

    result = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_dir / "national_sqw_full_episode_radar_manifest.csv", index=False)

    summary = {
        "episodes_input": int(len(episodes)),
        "episodes_with_geolocation": int(episodes[["lat", "lon"]].notna().all(axis=1).sum()),
        "verified_episode_count": int((episodes["verified_warning_count"].fillna(0).astype(int) > 0).sum()),
        "warning_only_episode_count": int((episodes["verified_warning_count"].fillna(0).astype(int) == 0).sum()),
        "radar_manifest_rows": int(len(result)),
        "unique_radar_sites": int(result["radar_site"].nunique()) if not result.empty else 0,
        "policy": "Episode-level radar mapping is discovery infrastructure. IEM verification is evidence metadata, not physical-event truth.",
    }
    (output_dir / "national_sqw_full_episode_radar_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-radars", type=int, default=2)
    parser.add_argument("--max-range-km", type=float, default=230.0)
    args = parser.parse_args()
    build(
        Path(args.episodes),
        Path(args.output_dir),
        max_radars=args.max_radars,
        max_range_km=args.max_range_km,
    )


if __name__ == "__main__":
    main()
