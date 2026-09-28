"""Derive object-track quality and organization metadata."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def build_track_catalog(path: Path):
    df = pd.read_csv(path)
    df["scan_dt"] = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["scan_dt", "object_id"]).copy()

    group_cols = [c for c in ("population", "radar_site", "object_id") if c in df.columns]
    if "radar_site" not in group_cols:
        group_cols.insert(0, "radar_site")
    if "object_id" not in group_cols:
        group_cols.append("object_id")

    df = df.sort_values(group_cols + ["scan_dt"])
    groups = []
    for key_values, g in df.groupby(group_cols, sort=True, dropna=False):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        key_map = dict(zip(group_cols, key_values))

        duration_min = (
            (g["scan_dt"].iloc[-1] - g["scan_dt"].iloc[0]).total_seconds() / 60.0
            if len(g) > 1 else 0.0
        )
        max_z = pd.to_numeric(g.get("max_reflectivity_dbz"), errors="coerce").max()
        mean_z = pd.to_numeric(g.get("mean_reflectivity_dbz"), errors="coerce").mean()
        area = pd.to_numeric(g.get("area_km2"), errors="coerce")
        aspect = (
            pd.to_numeric(g["aspect_ratio"], errors="coerce")
            if "aspect_ratio" in g.columns else pd.Series(dtype="float64")
        )
        intervals = g["scan_dt"].diff().dt.total_seconds().div(60.0).dropna()
        max_gap = float(intervals.max()) if not intervals.empty else 0.0
        median_area = float(area.median()) if not area.dropna().empty else np.nan
        max_area = float(area.max()) if not area.dropna().empty else np.nan
        motion = pd.to_numeric(g["motion_speed_kt"], errors="coerce") if "motion_speed_kt" in g.columns else pd.Series(dtype="float64")
        max_motion = float(motion.max()) if not motion.dropna().empty else np.nan
        median_motion = float(motion.median()) if not motion.dropna().empty else np.nan
        duplicate_scan_times = int(g["scan_dt"].duplicated().sum())

        flags = []
        if g["geometry_wkt"].isna().any() if "geometry_wkt" in g.columns else True:
            flags.append("missing_geometry")
        if max_gap > 15:
            flags.append("temporal_gap_gt_15m")
        if max_area > 5000:
            flags.append("very_large_object")
        if np.isfinite(median_area) and median_area > 0 and max_area / median_area > 20:
            flags.append("rapid_area_jump")
        if aspect.dropna().empty:
            flags.append("missing_aspect_ratio")
        if "touches_grid_edge" in g.columns and g["touches_grid_edge"].fillna(False).any():
            flags.append("touches_grid_edge")
        if duplicate_scan_times:
            flags.append("duplicate_scan_time")
        if np.isfinite(max_motion) and max_motion > 100:
            flags.append("implausible_motion_gt_100kt")

        groups.append({
            **key_map,
            "first_scan_utc": g["scan_dt"].iloc[0].isoformat(),
            "last_scan_utc": g["scan_dt"].iloc[-1].isoformat(),
            "scan_count": len(g),
            "duration_min": duration_min,
            "max_gap_min": max_gap,
            "max_reflectivity_dbz": max_z,
            "mean_reflectivity_dbz": mean_z,
            "max_area_km2": max_area,
            "median_area_km2": median_area,
            "max_aspect_ratio": float(aspect.max()) if not aspect.empty else np.nan,
            "median_aspect_ratio": float(aspect.median()) if not aspect.empty else np.nan,
            "max_motion_speed_kt": max_motion,
            "median_motion_speed_kt": median_motion,
            "duplicate_scan_times": duplicate_scan_times,
            "track_quality": (
                "short" if len(g) < 3 else
                "moderate" if len(g) < 6 else
                "persistent"
            ),
            "qc_status": "review" if flags else "pass",
            "qc_flags": ";".join(flags),
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
    print("QC status:")
    print(result["qc_status"].value_counts().to_string())
    flagged = result[result["qc_status"] == "review"]
    if not flagged.empty:
        print("QC flags:")
        print(flagged["qc_flags"].value_counts().to_string())


if __name__ == "__main__":
    main()
