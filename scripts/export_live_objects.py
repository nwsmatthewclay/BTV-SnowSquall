"""Export the latest tracked radar objects as live-style GeoJSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output", default="data/derived/live_objects.geojson")
    p.add_argument("--probability", type=float, default=None)
    args = p.parse_args()

    df = pd.read_csv(args.input)
    df["scan_time_utc"] = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["scan_time_utc"]).sort_values("scan_time_utc")
    if df.empty:
        raise SystemExit("No object records found.")

    latest_time = df["scan_time_utc"].max()
    latest = df[df["scan_time_utc"] == latest_time].copy()
    features = []

    for _, row in latest.iterrows():
        geom_text = row.get("geometry_wkt")
        if not isinstance(geom_text, str) or not geom_text:
            continue
        try:
            geom = wkt.loads(geom_text)
            if geom.geom_type != "Polygon":
                polygons = [part for part in getattr(geom, "geoms", ()) if part.geom_type == "Polygon"]
                if polygons:
                    geom = max(polygons, key=lambda part: part.area)
                else:
                    continue
        except Exception:
            continue

        props = {
            "track_id": int(row["object_id"]),
            "timestamp": row["scan_time_utc"].isoformat(),
            "radar_site": row.get("radar_site"),
            "probability_30min": args.probability,
            "probability_trend": "unknown",
            "max_reflectivity_dbz": row.get("max_reflectivity_dbz"),
            "mean_reflectivity_dbz": row.get("mean_reflectivity_dbz"),
            "area_km2": row.get("area_km2"),
            "length_km": row.get("length_km"),
            "width_km": row.get("width_km"),
            "data_quality": "pilot",
            "model_version": "object-reconstruction-pilot",
        }
        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": props,
        })

    result = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "latest_scan_utc": latest_time.isoformat(),
            "source": "BTV-SnowSquall historical radar reconstruction",
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {len(features)} live-style objects to {out}")


if __name__ == "__main__":
    main()
