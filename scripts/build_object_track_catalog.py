"""Derive object-track quality and organization metadata.

This does not assign a snow-squall label. It summarizes each tracked object's
observed history so later manual/modeled organization labels can be attached
without changing the underlying observations.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def build_track_catalog(path: Path):
    df = pd.read_csv(path)
    df["scan_dt"] = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["scan_dt", "object_id"]).copy()
    df = df.sort_values(["object_id", "scan_dt"])

    groups = []
    for object_id, g in df.groupby("object_id", sort=True):
        duration_min = (
            (g["scan_dt"].iloc[-1] - g["scan_dt"].iloc[0]).total_seconds() / 60.0
            if len(g) > 1 else 0.0
        )
        max_z = pd.to_numeric(g.get("max_reflectivity_dbz"), errors="coerce").max()
        mean_z = pd.to_numeric(g.get("mean_reflectivity_dbz"), errors="coerce").mean()
        area = pd.to_numeric(g.get("area_km2"), errors="coerce")
        aspect = pd.to_numeric(g["aspect_ratio"], errors="coerce") if "aspect_ratio" in g.columns else pd.Series(dtype="float64")

        groups.append({
            "object_id": object_id,
            "radar_site": g["radar_site"].iloc[0] if "radar_site" in g else None,
            "first_scan_utc": g["scan_dt"].iloc[0].isoformat(),
            "last_scan_utc": g["scan_dt"].iloc[-1].isoformat(),
            "scan_count": len(g),
            "duration_min": duration_min,
            "max_reflectivity_dbz": max_z,
            "mean_reflectivity_dbz": mean_z,
            "max_area_km2": area.max(),
            "median_area_km2": area.median(),
            "max_aspect_ratio": float(aspect.max()) if not aspect.empty else np.nan,
            "median_aspect_ratio": float(aspect.median()) if not aspect.empty else np.nan,
            "track_quality": (
                "short"
                if len(g) < 3 else
                "moderate"
                if len(g) < 6 else
                "persistent"
            ),
            "organization_label": "unlabeled",
            "impact_label": "unlabeled",
        })

    return pd.DataFrame(groups)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = build_track_catalog(Path(args.input_csv))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)

    print(f"Wrote {len(result)} track summaries to {args.output}")
    print("Track quality:")
    print(result["track_quality"].value_counts().to_string())


if __name__ == "__main__":
    main()
