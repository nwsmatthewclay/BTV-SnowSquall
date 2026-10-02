"""Summarize real historical tracker behavior for case-by-case review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def summarize(objects: pd.DataFrame, tracks: pd.DataFrame) -> dict:
    out = {
        "object_scans": int(len(objects)),
        "tracks": int(len(tracks)),
        "case_count": int(
            objects["case_id"].dropna().astype(str).nunique()
        )
        if "case_id" in objects.columns
        else 0,
    }

    if "quality_tier" in tracks.columns:
        out["track_quality_tiers"] = (
            tracks["quality_tier"].fillna("unknown").astype(str).value_counts().to_dict()
        )
    if "qc_status" in tracks.columns:
        out["qc_status"] = (
            tracks["qc_status"].fillna("unknown").astype(str).value_counts().to_dict()
        )

    for source, name in (
        ("track_quality_score", "object_scan_quality_score"),
        ("track_association_confidence", "association_confidence"),
        ("track_association_cost", "association_cost"),
    ):
        if source in objects.columns:
            values = pd.to_numeric(objects[source], errors="coerce").dropna()
            if not values.empty:
                out[name] = {
                    "median": float(values.median()),
                    "p10": float(values.quantile(0.10)),
                    "p90": float(values.quantile(0.90)),
                }

    if "case_id" in objects.columns and "quality_tier" in tracks.columns:
        key_cols = [c for c in ("case_id", "radar_site", "object_id") if c in objects.columns]
        object_counts = (
            objects.groupby(key_cols, dropna=False).size().reset_index(name="object_scans")
        )

        track_keys = (
            tracks[key_cols + ["quality_tier", "quality_score", "qc_flags"]]
            if set(key_cols + ["quality_tier", "quality_score", "qc_flags"]).issubset(tracks.columns)
            else tracks
        )
        joined = object_counts.merge(
            track_keys,
            on=key_cols,
            how="left",
        )

        case_summary = (
            joined.groupby("case_id", dropna=False)
            .agg(
                tracks=("object_id", "count"),
                object_scans=("object_scans", "sum"),
                pass_tracks=("quality_tier", lambda s: int((s == "pass").sum())),
                review_tracks=("quality_tier", lambda s: int((s == "review").sum())),
                reject_tracks=("quality_tier", lambda s: int((s == "reject").sum())),
                median_quality_score=("quality_score", "median"),
            )
            .reset_index()
            .sort_values("case_id", kind="stable")
        )
        out["case_summary"] = case_summary.to_dict("records")

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objects", required=True)
    ap.add_argument("--tracks", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    objects = pd.read_csv(args.objects)
    tracks = pd.read_csv(args.tracks)
    report = summarize(objects, tracks)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
