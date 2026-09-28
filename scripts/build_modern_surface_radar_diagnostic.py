"""Build a non-scoring surface-observation to radar-object timing diagnostic."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    lat_mid = math.radians((lat1 + lat2) / 2.0)
    return 111.2 * math.hypot(lat1 - lat2, (lon1 - lon2) * math.cos(lat_mid))


def load_radar_objects(replay_case: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(replay_case.glob("*.geojson")):
        if path.name == "replay_manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            p = feature.get("properties", {})
            if p.get("centroid_lat") is None or p.get("centroid_lon") is None:
                continue
            rows.append({
                "radar_time": pd.to_datetime(payload.get("metadata", {}).get("scan_time_utc"), utc=True),
                "track_id": p.get("track_id"),
                "lat": float(p["centroid_lat"]),
                "lon": float(p["centroid_lon"]),
                "max_reflectivity_dbz": p.get("max_reflectivity_dbz"),
                "area_km2": p.get("area_km2"),
                "motion_speed_kt": p.get("motion_speed_kt"),
            })
    return pd.DataFrame(rows)


def build(surface_file: Path, replay_case: Path, output_csv: Path) -> dict:
    surface = pd.read_csv(surface_file)
    surface["valid"] = pd.to_datetime(surface["valid"], utc=True, errors="coerce")
    surface = surface.dropna(subset=["valid"]).copy()
    radar = load_radar_objects(replay_case)
    if radar.empty:
        raise ValueError(f"No replay objects found in {replay_case}")

    rows = []
    for obs in surface.itertuples(index=False):
        candidates = radar[
            (radar["radar_time"] - obs.valid).abs() <= pd.Timedelta(minutes=10)
        ].copy()
        if candidates.empty:
            rows.append({
                "observation_time_utc": obs.valid.isoformat(),
                "visibility_mi": getattr(obs, "visibility_mi", None),
                "wind_gust_kt": getattr(obs, "wind_gust_kt", None),
                "wxcodes": getattr(obs, "wxcodes", None),
                "radar_match_status": "no_radar_object_within_10min",
            })
            continue

        candidates["distance_km"] = candidates.apply(
            lambda r: distance_km(obs.lat, obs.lon, r.lat, r.lon), axis=1
        )
        match = candidates.sort_values(["distance_km", "radar_time"]).iloc[0]
        rows.append({
            "observation_time_utc": obs.valid.isoformat(),
            "visibility_mi": getattr(obs, "visibility_mi", None),
            "wind_gust_kt": getattr(obs, "wind_gust_kt", None),
            "wxcodes": getattr(obs, "wxcodes", None),
            "radar_match_status": "matched",
            "radar_time_utc": match.radar_time.isoformat(),
            "radar_time_offset_minutes": (match.radar_time - obs.valid).total_seconds() / 60.0,
            "radar_track_id": match.track_id,
            "radar_distance_km": float(match.distance_km),
            "radar_max_reflectivity_dbz": match.max_reflectivity_dbz,
            "radar_area_km2": match.area_km2,
            "radar_motion_speed_kt": match.motion_speed_kt,
        })

    result = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False)

    valid_vis = result.dropna(subset=["visibility_mi"]).copy()
    summary = {
        "surface_observations": int(len(result)),
        "matched_surface_observations": int((result["radar_match_status"] == "matched").sum()),
        "scoring_status": "not_scored",
    }
    if not valid_vis.empty:
        ordered = valid_vis.sort_values("observation_time_utc")
        for threshold, label in [(0.5, "0p5"), (0.25, "0p25"), (0.125, "0p125")]:
            hit = ordered[ordered["visibility_mi"] <= threshold]
            if not hit.empty:
                row = hit.iloc[0]
                summary[f"first_visibility_le_{label}_utc"] = str(row["observation_time_utc"])
                summary[f"radar_distance_km_at_first_visibility_le_{label}"] = (
                    float(row["radar_distance_km"]) if pd.notna(row.get("radar_distance_km")) else None
                )
                summary[f"radar_max_reflectivity_at_first_visibility_le_{label}_dbz"] = (
                    float(row["radar_max_reflectivity_dbz"])
                    if pd.notna(row.get("radar_max_reflectivity_dbz")) else None
                )
        min_row = valid_vis.sort_values("visibility_mi").iloc[0]
        summary.update({
            "minimum_visibility_mi": float(min_row["visibility_mi"]),
            "minimum_visibility_time_utc": str(min_row["observation_time_utc"]),
            "radar_distance_km_at_min_visibility": float(min_row["radar_distance_km"]) if pd.notna(min_row.get("radar_distance_km")) else None,
            "radar_max_reflectivity_at_min_visibility_dbz": float(min_row["radar_max_reflectivity_dbz"]) if pd.notna(min_row.get("radar_max_reflectivity_dbz")) else None,
        })
    output_csv.with_suffix(".json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface", required=True)
    parser.add_argument("--replay-case", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.surface), Path(args.replay_case), Path(args.output))


if __name__ == "__main__":
    main()
