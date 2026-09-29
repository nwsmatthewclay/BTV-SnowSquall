"""Build fixed-network surface-to-radar diagnostics for modern candidates."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from scripts.build_modern_surface_radar_diagnostic import load_radar_objects, distance_km


def diagnose(surface_file: Path, replay_case: Path, case_id: str, station: str, radar_site: str):
    surface = pd.read_csv(surface_file)
    surface["valid"] = pd.to_datetime(surface["valid"], utc=True, errors="coerce")
    surface = surface.dropna(subset=["valid"]).copy()
    radar = load_radar_objects(replay_case)
    if radar.empty:
        return [{
            "case_id": case_id, "station": station, "radar_site": radar_site,
            "observation_time_utc": None, "visibility_mi": None,
            "status": "no_radar_objects"
        }]

    rows = []
    for obs in surface.itertuples(index=False):
        near = radar[
            (radar["radar_time"] - obs.valid).abs() <= pd.Timedelta(minutes=10)
        ].copy()
        row = {
            "case_id": case_id,
            "station": station,
            "radar_site": radar_site,
            "observation_time_utc": obs.valid.isoformat(),
            "visibility_mi": getattr(obs, "visibility_mi", None),
            "wind_gust_kt": getattr(obs, "wind_gust_kt", None),
        }
        if near.empty:
            row["match_status"] = "no_object_within_10min"
            rows.append(row)
            continue

        near["distance_km"] = near.apply(
            lambda r: distance_km(obs.lat, obs.lon, r.lat, r.lon),
            axis=1,
        )
        match = near.sort_values(["distance_km", "radar_time"]).iloc[0]
        row.update({
            "match_status": "matched",
            "radar_time_utc": match.radar_time.isoformat(),
            "radar_time_offset_minutes": (match.radar_time - obs.valid).total_seconds() / 60.0,
            "radar_track_id": match.track_id,
            "radar_distance_km": float(match.distance_km),
            "radar_max_reflectivity_dbz": match.max_reflectivity_dbz,
            "radar_area_km2": match.area_km2,
        })
        rows.append(row)
    return rows


def build(manifest_path: Path, surface_root: Path, replay_root: Path, output_csv: Path, summary_json: Path):
    manifest = pd.read_csv(manifest_path)
    rows = []
    for case_id in sorted(manifest["case_id"].astype(str).unique()):
        for radar_site in ("KCXX", "KTYX"):
            replay_case = replay_root / case_id / radar_site
            for surface_file in sorted(surface_root.glob(f"*/{case_id}.csv")):
                station = surface_file.parent.name
                if replay_case.exists():
                    rows.extend(diagnose(surface_file, replay_case, case_id, station, radar_site))

    df = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    summary = {
        "records": int(len(df)),
        "matched": int((df.get("match_status", pd.Series(dtype=str)) == "matched").sum()),
        "stations": sorted(df["station"].astype(str).unique().tolist()) if not df.empty else [],
        "radars": sorted(df["radar_site"].astype(str).unique().tolist()) if not df.empty else [],
        "cases": sorted(df["case_id"].astype(str).unique().tolist()) if not df.empty else [],
        "scoring_status": "not_scored",
    }
    if not df.empty and "visibility_mi" in df:
        vis = df.dropna(subset=["visibility_mi"]).sort_values("observation_time_utc")
        if not vis.empty:
            row = vis.iloc[0]
            summary["minimum_visibility_mi"] = float(row["visibility_mi"])
            summary["minimum_visibility_case_id"] = str(row["case_id"])
            summary["minimum_visibility_station"] = str(row["station"])
            summary["minimum_visibility_radar_site"] = str(row["radar_site"])
            summary["minimum_visibility_time_utc"] = str(row["observation_time_utc"])
            if pd.notna(row.get("radar_distance_km")):
                summary["radar_distance_km_at_global_min_visibility"] = float(row["radar_distance_km"])
    summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--surface-root", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    build(
        Path(args.manifest),
        Path(args.surface_root),
        Path(args.replay_root),
        Path(args.output),
        Path(args.summary),
    )


if __name__ == "__main__":
    main()
