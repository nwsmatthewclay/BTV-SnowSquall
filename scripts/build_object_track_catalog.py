"""Build track-level continuity, ambiguity and physical-quality diagnostics."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _numeric(g: pd.DataFrame, column: str) -> pd.Series:
    if column not in g.columns:
        return pd.Series(np.nan, index=g.index, dtype=float)
    return pd.to_numeric(g[column], errors="coerce")


def _fraction_true(g: pd.DataFrame, column: str) -> float:
    if column not in g.columns or len(g) == 0:
        return 0.0
    return float(
        g[column].fillna(False).astype(bool).mean()
    )


def _max_consecutive_area_ratio(area: pd.Series) -> float:
    values = area.dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return 1.0
    prev = np.maximum(values[:-1], 1e-6)
    curr = np.maximum(values[1:], 1e-6)
    return float(np.max(np.maximum(curr / prev, prev / curr)))


def _path_metrics(g: pd.DataFrame):
    if not {"centroid_lat", "centroid_lon"}.issubset(g.columns):
        return np.nan, np.nan

    lat = _numeric(g, "centroid_lat").to_numpy()
    lon = _numeric(g, "centroid_lon").to_numpy()
    valid = np.isfinite(lat) & np.isfinite(lon)
    lat, lon = lat[valid], lon[valid]
    if len(lat) < 2:
        return np.nan, np.nan

    r = 6371.0088
    lat1 = np.radians(lat[:-1])
    lat2 = np.radians(lat[1:])
    dlat = lat2 - lat1
    dlon = np.radians(lon[1:] - lon[:-1])
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    )
    segment = 2.0 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    path_km = float(np.nansum(segment))
    net_km = float(
        2.0
        * r
        * np.arcsin(
            np.sqrt(
                np.clip(
                    (
                        np.sin((np.radians(lat[-1]) - np.radians(lat[0])) / 2.0) ** 2
                        + np.cos(np.radians(lat[0]))
                        * np.cos(np.radians(lat[-1]))
                        * np.sin(
                            (np.radians(lon[-1]) - np.radians(lon[0])) / 2.0
                        ) ** 2
                    ),
                    0.0,
                    1.0,
                )
            )
        )
    )
    straightness = net_km / path_km if path_km > 0 else np.nan
    return path_km, straightness


def _quality_score(
    *,
    scan_count,
    duration_min,
    continuity_fraction,
    duplicate_scan_times,
    max_gap,
    max_motion,
    max_area_jump_ratio,
    geometry_fraction,
    edge_fraction,
    ambiguity_fraction,
    competition_fraction,
    median_cost,
    median_normalized_distance,
    radar_direction_error,
):
    score = 100.0
    flags = []

    if scan_count < 3:
        score -= 35
        flags.append("fewer_than_3_scans")
    if duration_min < 8:
        score -= 20
        flags.append("duration_lt_8m")
    if continuity_fraction < 0.90:
        score -= 20
        flags.append("continuity_lt_90pct")
    if duplicate_scan_times:
        score -= 40
        flags.append("duplicate_scan_time")
    if max_gap > 10:
        score -= 50
        flags.append("gap_gt_10m")
    if np.isfinite(max_motion) and max_motion > 90:
        score -= 40
        flags.append("implausible_motion_gt_90kt")
    if np.isfinite(max_area_jump_ratio) and max_area_jump_ratio > 20:
        score -= 25
        flags.append("rapid_area_jump_gt_20x")
    if geometry_fraction < 1.0:
        score -= 10
        flags.append("incomplete_geometry")
    if edge_fraction > 0.50:
        score -= 10
        flags.append("edge_dominated")
    if ambiguity_fraction > 0.25:
        score -= 15
        flags.append("association_ambiguity_gt_25pct")
    if competition_fraction > 0.25:
        score -= 10
        flags.append("merge_split_competition_gt_25pct")
    if np.isfinite(median_cost) and median_cost > 0.55:
        score -= 15
        flags.append("high_median_association_cost")
    if np.isfinite(median_normalized_distance) and median_normalized_distance > 0.55:
        score -= 10
        flags.append("large_normalized_association_distance")
    if np.isfinite(radar_direction_error) and radar_direction_error > 60:
        score -= 5
        flags.append("radar_motion_direction_disagreement_gt_60deg")

    score = float(np.clip(score, 0.0, 100.0))

    hard_reject = (
        scan_count < 2
        or duplicate_scan_times > 0
        or max_gap > 10
        or (np.isfinite(max_motion) and max_motion > 100)
        or (np.isfinite(max_area_jump_ratio) and max_area_jump_ratio > 30)
        or geometry_fraction <= 0.0
    )

    if hard_reject:
        tier = "reject"
    elif (
        score >= 75.0
        and scan_count >= 3
        and duration_min >= 8.0
        and continuity_fraction >= 0.90
    ):
        tier = "pass"
    else:
        tier = "review"

    return score, tier, flags


def build_track_catalog(path: Path):
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame()

    if "scan_time_utc" not in df.columns or "object_id" not in df.columns:
        raise ValueError("scan_time_utc and object_id are required")

    df["scan_dt"] = pd.to_datetime(
        df["scan_time_utc"], utc=True, errors="coerce"
    )
    df = df.dropna(subset=["scan_dt", "object_id"]).copy()

    group_cols = [
        c
        for c in (
            "population",
            "episode_id",
            "case_id",
            "null_id",
            "window_id",
            "radar_site",
            "object_id",
        )
        if c in df.columns
    ]
    if "radar_site" not in group_cols:
        group_cols.insert(0, "radar_site")
    if "object_id" not in group_cols:
        group_cols.append("object_id")

    df = df.sort_values(group_cols + ["scan_dt"], kind="stable")
    groups = []

    for key_values, g in df.groupby(
        group_cols, sort=True, dropna=False
    ):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        key_map = dict(zip(group_cols, key_values))

        intervals = (
            g["scan_dt"].diff().dt.total_seconds().div(60.0).dropna()
        )
        duration_min = (
            (g["scan_dt"].iloc[-1] - g["scan_dt"].iloc[0]).total_seconds()
            / 60.0
            if len(g) > 1
            else 0.0
        )
        max_gap = float(intervals.max()) if not intervals.empty else 0.0
        continuity_fraction = (
            float(intervals.between(0, 10, inclusive="both").mean())
            if not intervals.empty
            else 1.0
        )

        max_z = _numeric(g, "max_reflectivity_dbz").max()
        mean_z = _numeric(g, "mean_reflectivity_dbz").mean()
        area = _numeric(g, "area_km2")
        aspect = _numeric(g, "aspect_ratio")
        motion = _numeric(g, "motion_speed_kt")
        radar_motion = _numeric(g, "radar_motion_speed_kt")
        radar_conf = _numeric(g, "radar_motion_confidence")
        radar_dir = _numeric(g, "radar_motion_direction_deg")

        if "motion_direction_deg" in g.columns:
            object_dir = _numeric(g, "motion_direction_deg")
        else:
            object_dir = _numeric(g, "motion_dir_deg")
        direction_error = (
            np.abs((object_dir - radar_dir + 180.0) % 360.0 - 180.0)
            if radar_dir.notna().any()
            else pd.Series(np.nan, index=g.index)
        )

        status = (
            g["track_association_status"].astype(str)
            if "track_association_status" in g.columns
            else pd.Series("unknown", index=g.index)
        )
        associated = status.isin(["matched", "recovered_after_gap"])
        eligible_associations = max(len(g) - 1, 1)
        matched_fraction = float(associated.sum() / eligible_associations)

        normalized_distance = _numeric(
            g, "track_association_normalized_distance"
        )
        association_cost = _numeric(g, "track_association_cost")
        ambiguity = (
            g["track_association_ambiguous"].fillna(False).astype(bool)
            if "track_association_ambiguous" in g.columns
            else pd.Series(False, index=g.index)
        )
        merge_candidates = (
            g["track_merge_candidate"].fillna(False).astype(bool)
            if "track_merge_candidate" in g.columns
            else pd.Series(False, index=g.index)
        )
        split_candidates = (
            g["track_split_candidate"].fillna(False).astype(bool)
            if "track_split_candidate" in g.columns
            else pd.Series(False, index=g.index)
        )

        geometry_fraction = (
            float(g["geometry_wkt"].notna().mean())
            if "geometry_wkt" in g.columns
            else 0.0
        )
        edge_fraction = _fraction_true(g, "touches_grid_edge")
        duplicate_scan_times = int(g["scan_dt"].duplicated().sum())

        max_area_jump_ratio = _max_consecutive_area_ratio(area)
        path_km, straightness = _path_metrics(g)
        score, quality_tier, quality_flags = _quality_score(
            scan_count=len(g),
            duration_min=duration_min,
            continuity_fraction=continuity_fraction,
            duplicate_scan_times=duplicate_scan_times,
            max_gap=max_gap,
            max_motion=float(motion.max()) if motion.notna().any() else np.nan,
            max_area_jump_ratio=max_area_jump_ratio,
            geometry_fraction=geometry_fraction,
            edge_fraction=edge_fraction,
            ambiguity_fraction=float(ambiguity.mean()),
            competition_fraction=float(
                np.logical_or(merge_candidates, split_candidates).mean()
            ),
            median_cost=(
                float(association_cost.dropna().median())
                if association_cost.notna().any()
                else np.nan
            ),
            median_normalized_distance=(
                float(normalized_distance.dropna().median())
                if normalized_distance.notna().any()
                else np.nan
            ),
            radar_direction_error=(
                float(direction_error.dropna().median())
                if direction_error.notna().any()
                else np.nan
            ),
        )

        if "geometry_wkt" in g.columns and g["geometry_wkt"].isna().any():
            quality_flags.append("missing_geometry")
        if np.isfinite(float(motion.max())) and float(motion.max()) > 100:
            quality_flags.append("implausible_motion_gt_100kt")

        groups.append(
            {
                **key_map,
                "first_scan_utc": g["scan_dt"].iloc[0].isoformat(),
                "last_scan_utc": g["scan_dt"].iloc[-1].isoformat(),
                "scan_count": int(len(g)),
                "duration_min": float(duration_min),
                "max_gap_min": float(max_gap),
                "continuity_fraction": float(continuity_fraction),
                "matched_fraction": float(matched_fraction),
                "max_reflectivity_dbz": float(max_z)
                if np.isfinite(max_z)
                else np.nan,
                "mean_reflectivity_dbz": float(mean_z)
                if np.isfinite(mean_z)
                else np.nan,
                "max_area_km2": float(area.max())
                if area.notna().any()
                else np.nan,
                "median_area_km2": float(area.median())
                if area.notna().any()
                else np.nan,
                "max_consecutive_area_ratio": float(max_area_jump_ratio),
                "max_aspect_ratio": float(aspect.max())
                if aspect.notna().any()
                else np.nan,
                "median_aspect_ratio": float(aspect.median())
                if aspect.notna().any()
                else np.nan,
                "max_motion_speed_kt": float(motion.max())
                if motion.notna().any()
                else np.nan,
                "median_motion_speed_kt": float(motion.median())
                if motion.notna().any()
                else np.nan,
                "max_radar_motion_speed_kt": float(radar_motion.max())
                if radar_motion.notna().any()
                else np.nan,
                "median_radar_motion_confidence": float(radar_conf.median())
                if radar_conf.notna().any()
                else np.nan,
                "median_object_radar_direction_error_deg": float(
                    direction_error.median()
                )
                if direction_error.notna().any()
                else np.nan,
                "median_association_cost": float(association_cost.median())
                if association_cost.notna().any()
                else np.nan,
                "median_association_normalized_distance": float(
                    normalized_distance.median()
                )
                if normalized_distance.notna().any()
                else np.nan,
                "ambiguous_association_fraction": float(ambiguity.mean()),
                "merge_candidate_fraction": float(merge_candidates.mean()),
                "split_candidate_fraction": float(split_candidates.mean()),
                "geometry_fraction": float(geometry_fraction),
                "edge_fraction": float(edge_fraction),
                "path_length_km": path_km,
                "path_straightness": straightness,
                "duplicate_scan_times": int(duplicate_scan_times),
                "track_quality": (
                    "short"
                    if len(g) < 3
                    else "moderate"
                    if len(g) < 6
                    else "persistent"
                ),
                "quality_score": float(score),
                "quality_tier": quality_tier,
                "qc_status": (
                    "pass" if quality_tier == "pass" else
                    "reject" if quality_tier == "reject" else
                    "review"
                ),
                "qc_flags": ";".join(dict.fromkeys(quality_flags)),
                "organization_label": "unlabeled",
                "impact_label": "unlabeled",
            }
        )

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
    if result.empty:
        return

    print("Track quality:")
    print(result["track_quality"].value_counts().to_string())
    print("Quality tier:")
    print(result["quality_tier"].value_counts().to_string())
    print("QC status:")
    print(result["qc_status"].value_counts().to_string())
    flagged = result[result["qc_status"] != "pass"]
    if not flagged.empty:
        print("QC flags:")
        print(flagged["qc_flags"].value_counts().to_string())


if __name__ == "__main__":
    main()
