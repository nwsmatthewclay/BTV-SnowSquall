"""Compare historical research objects with the scan-by-scan live replay.

The comparator is diagnostic: the two pipelines are allowed to differ. It
quantifies object-count agreement and geographic proximity without declaring
either processor correct solely from the comparison.
"""
from __future__ import annotations

import argparse
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371.0088 * 2.0 * asin(sqrt(a))


def load_research(path: Path):
    d = pd.read_csv(path)
    d["scan_time_utc"] = pd.to_datetime(d["scan_time_utc"], utc=True, errors="coerce")
    return d.dropna(subset=["scan_time_utc", "centroid_lat", "centroid_lon"]).copy()


def load_replay(path: Path):
    rows = []
    for geojson_path in sorted(path.glob("*.geojson")):
        try:
            payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        timestamp = payload.get("metadata", {}).get("scan_time_utc")
        if timestamp is None:
            continue
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            lat = props.get("centroid_lat")
            lon = props.get("centroid_lon")
            if lat is None or lon is None:
                continue
            rows.append({
                "scan_time_utc": pd.to_datetime(timestamp, utc=True),
                "track_id": str(props.get("track_id", "")),
                "centroid_lat": float(lat),
                "centroid_lon": float(lon),
            })
    return pd.DataFrame(rows)


def compare(research: pd.DataFrame, replay: pd.DataFrame, match_radius_km: float = 15.0):
    research = research.copy()
    replay = replay.copy()
    research["scan_time_utc"] = pd.to_datetime(research["scan_time_utc"], utc=True, errors="coerce")
    replay["scan_time_utc"] = pd.to_datetime(replay["scan_time_utc"], utc=True, errors="coerce")
    research = research.dropna(subset=["scan_time_utc"])
    replay = replay.dropna(subset=["scan_time_utc"])
    research_by_time = {t: g for t, g in research.groupby("scan_time_utc")}
    replay_by_time = {t: g for t, g in replay.groupby("scan_time_utc")}
    times = sorted(set(research_by_time) | set(replay_by_time))

    scan_rows = []
    matched_distances = []

    for timestamp in times:
        rg = research_by_time.get(timestamp, research.iloc[0:0])
        og = replay_by_time.get(timestamp, replay.iloc[0:0])
        candidates = []
        for ri, r in rg.iterrows():
            for oi, o in og.iterrows():
                distance = distance_km(
                    float(r["centroid_lat"]), float(r["centroid_lon"]),
                    float(o["centroid_lat"]), float(o["centroid_lon"]),
                )
                candidates.append((distance, ri, oi))
        candidates.sort()

        used_r, used_o = set(), set()
        matches = []
        for distance, ri, oi in candidates:
            if distance > match_radius_km or ri in used_r or oi in used_o:
                continue
            used_r.add(ri)
            used_o.add(oi)
            matches.append(distance)
        matched_distances.extend(matches)

        scan_rows.append({
            "scan_time_utc": timestamp.isoformat(),
            "research_objects": int(len(rg)),
            "replay_objects": int(len(og)),
            "matched_objects": int(len(matches)),
            "research_unmatched": int(len(rg) - len(matches)),
            "replay_unmatched": int(len(og) - len(matches)),
            "median_match_distance_km": float(pd.Series(matches).median()) if matches else None,
        })

    scans = pd.DataFrame(scan_rows)
    paired_scans = scans[(scans["research_objects"] > 0) | (scans["replay_objects"] > 0)]
    exact_count_scans = int(
        (paired_scans["research_objects"] == paired_scans["replay_objects"]).sum()
    )
    return {
        "comparison_version": "research_operational_replay_v1",
        "interpretation": "diagnostic_only",
        "match_radius_km": match_radius_km,
        "scans_compared": int(len(paired_scans)),
        "scans_with_equal_object_counts": exact_count_scans,
        "scan_count_agreement_fraction": (
            float(exact_count_scans / len(paired_scans)) if len(paired_scans) else None
        ),
        "research_objects": int(paired_scans["research_objects"].sum()) if len(paired_scans) else 0,
        "replay_objects": int(paired_scans["replay_objects"].sum()) if len(paired_scans) else 0,
        "matched_objects": int(paired_scans["matched_objects"].sum()) if len(paired_scans) else 0,
        "match_fraction_research": (
            float(paired_scans["matched_objects"].sum() / paired_scans["research_objects"].sum())
            if paired_scans["research_objects"].sum() else None
        ),
        "median_match_distance_km": (
            float(pd.Series(matched_distances).median()) if matched_distances else None
        ),
        "scan_diagnostics": scan_rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--replay-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--match-radius-km", type=float, default=15.0)
    args = parser.parse_args()

    report = compare(
        load_research(args.research),
        load_replay(args.replay_dir),
        match_radius_km=args.match_radius_km,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "scans_compared": report["scans_compared"],
        "match_fraction_research": report["match_fraction_research"],
        "median_match_distance_km": report["median_match_distance_km"],
    }, indent=2))


if __name__ == "__main__":
    main()
