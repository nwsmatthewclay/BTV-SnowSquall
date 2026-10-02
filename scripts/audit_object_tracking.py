"""Audit historical object-track continuity, quality and radar-motion agreement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _count_true(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    return int(frame[column].fillna(False).astype(bool).sum())


def _fraction(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns or frame.empty:
        return None
    return float(frame[column].fillna(False).astype(bool).mean())


def audit(frame: pd.DataFrame) -> dict:
    d = frame.copy()
    if d.empty:
        return {"records": 0, "tracks": 0}

    required = {"scan_time_utc", "object_id", "radar_site"}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    d["scan_dt"] = pd.to_datetime(d["scan_time_utc"], utc=True, errors="coerce")
    d = d.dropna(subset=["scan_dt"]).copy()
    d = d.sort_values(
        ["radar_site", "object_id", "scan_dt"],
        kind="stable",
    )

    g = d.groupby(
        ["radar_site", "object_id"],
        dropna=False,
        sort=False,
    )
    dt = g["scan_dt"].diff().dt.total_seconds() / 60.0

    speed = pd.to_numeric(
        d.get("motion_speed_kt", pd.Series(np.nan, index=d.index)),
        errors="coerce",
    )
    radar_speed = pd.to_numeric(
        d.get("radar_motion_speed_kt", pd.Series(np.nan, index=d.index)),
        errors="coerce",
    )
    radar_conf = pd.to_numeric(
        d.get("radar_motion_confidence", pd.Series(np.nan, index=d.index)),
        errors="coerce",
    )
    radar_dir = pd.to_numeric(
        d.get(
            "radar_motion_direction_deg",
            pd.Series(np.nan, index=d.index),
        ),
        errors="coerce",
    )
    object_dir = pd.to_numeric(
        d.get(
            "motion_direction_deg",
            d.get("motion_dir_deg", pd.Series(np.nan, index=d.index)),
        ),
        errors="coerce",
    )
    direction_error = np.abs(
        (object_dir - radar_dir + 180.0) % 360.0 - 180.0
    )

    track_sizes = g.size()
    track_first = g["scan_dt"].min()
    track_last = g["scan_dt"].max()
    track_duration = (
        (track_last - track_first).dt.total_seconds() / 60.0
    )

    quality_tiers = (
        d["track_quality_tier"].fillna("unknown").astype(str).value_counts().to_dict()
        if "track_quality_tier" in d.columns
        else {}
    )
    quality_gate = (
        d["track_quality_gate"].fillna("unknown").astype(str).value_counts().to_dict()
        if "track_quality_gate" in d.columns
        else {}
    )
    association_status = (
        d["track_association_status"]
        .fillna("unknown")
        .astype(str)
        .value_counts()
        .to_dict()
        if "track_association_status" in d.columns
        else {}
    )

    out = {
        "records": int(len(d)),
        "tracks": int(g.ngroups),
        "multi_scan_tracks": int((track_sizes >= 2).sum()),
        "singleton_tracks": int((track_sizes == 1).sum()),
        "singleton_track_fraction": (
            float((track_sizes == 1).mean()) if len(track_sizes) else 0.0
        ),
        "median_track_scans": float(track_sizes.median()),
        "p90_track_scans": float(track_sizes.quantile(0.90)),
        "median_track_duration_min": (
            float(track_duration.median()) if len(track_duration) else 0.0
        ),
        "p90_track_duration_min": (
            float(track_duration.quantile(0.90)) if len(track_duration) else 0.0
        ),
        "gaps_gt_10min": int((dt > 10).sum()),
        "impossible_speed_over_90kt": int((speed > 90).sum()),
        "impossible_speed_over_100kt": int((speed > 100).sum()),
        "radar_motion_available": int(radar_speed.notna().sum()),
        "radar_motion_high_confidence": int(radar_conf.fillna(0).ge(0.5).sum()),
        "median_object_radar_motion_direction_error_deg": (
            float(direction_error.dropna().median())
            if direction_error.notna().any()
            else None
        ),
        "edge_touch_fraction": _fraction(d, "touches_grid_edge"),
        "association_ambiguous_scans": _count_true(
            d, "track_association_ambiguous"
        ),
        "association_ambiguous_fraction": _fraction(
            d, "track_association_ambiguous"
        ),
        "merge_candidate_scans": _count_true(d, "track_merge_candidate"),
        "split_candidate_scans": _count_true(d, "track_split_candidate"),
        "median_association_confidence": (
            float(
                pd.to_numeric(
                    d["track_association_confidence"],
                    errors="coerce",
                ).dropna().median()
            )
            if "track_association_confidence" in d.columns
            and pd.to_numeric(
                d["track_association_confidence"], errors="coerce"
            ).notna().any()
            else None
        ),
        "median_association_cost": (
            float(
                pd.to_numeric(
                    d["track_association_cost"],
                    errors="coerce",
                ).dropna().median()
            )
            if "track_association_cost" in d.columns
            and pd.to_numeric(
                d["track_association_cost"], errors="coerce"
            ).notna().any()
            else None
        ),
        "quality_tiers": quality_tiers,
        "quality_gate": quality_gate,
        "association_status": association_status,
    }

    # Track-level summaries make the audit directly actionable for reviewing
    # the objects the model would otherwise receive.
    if "track_quality_score" in d.columns:
        q = pd.to_numeric(d["track_quality_score"], errors="coerce")
        out["median_track_quality_score"] = (
            float(q.dropna().median()) if q.notna().any() else None
        )

    suspect = []
    if "track_id" in d.columns:
        id_column = "track_id"
    else:
        id_column = "object_id"

    for (radar, object_id), track in d.groupby(
        ["radar_site", id_column],
        dropna=False,
        sort=False,
    ):
        row = {
            "radar_site": str(radar),
            "track_id": str(object_id),
            "scan_count": int(len(track)),
        }
        for col, output_key in (
            ("track_quality_score", "quality_score"),
            ("track_association_confidence", "median_association_confidence"),
            ("track_association_cost", "median_association_cost"),
            ("motion_speed_kt", "max_motion_speed_kt"),
        ):
            if col in track.columns:
                values = pd.to_numeric(track[col], errors="coerce").dropna()
                if not values.empty:
                    row[output_key] = (
                        float(values.max())
                        if output_key == "max_motion_speed_kt"
                        else float(values.median())
                    )
        flags = []
        if "track_association_ambiguous" in track.columns and track[
            "track_association_ambiguous"
        ].fillna(False).astype(bool).any():
            flags.append("ambiguous_association")
        if "track_merge_candidate" in track.columns and track[
            "track_merge_candidate"
        ].fillna(False).astype(bool).any():
            flags.append("merge_candidate")
        if "track_split_candidate" in track.columns and track[
            "track_split_candidate"
        ].fillna(False).astype(bool).any():
            flags.append("split_candidate")
        if "track_quality_gate" in track.columns and (
            track["track_quality_gate"].fillna("unknown").astype(str) != "pass"
        ).any():
            flags.append("quality_gate_not_pass")
        if flags:
            row["flags"] = flags
            suspect.append(row)

    suspect.sort(
        key=lambda x: (
            0 if "quality_score" in x else 1,
            x.get("quality_score", 0.0),
            -x["scan_count"],
        )
    )
    out["suspect_track_count"] = int(len(suspect))
    out["suspect_tracks_top20"] = suspect[:20]

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    report = audit(pd.read_csv(args.input_csv))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
