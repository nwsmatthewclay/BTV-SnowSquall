"""Summarize snow-squall radar object-detection quality for a reconstructed batch.

This is a diagnostic report, not a truth label and not a model score. It is
intended to reveal object-count/shape/evidence changes between detector
revisions while keeping event supervision downstream.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

import pandas as pd


def _evidence(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return [str(x) for x in parsed]
    except (ValueError, SyntaxError):
        pass
    return [item.strip() for item in text.split(",") if item.strip()]


def audit(source: Path, output: Path) -> dict:
    df = pd.read_csv(source)
    if "context_only" in df.columns:
        detected = df[pd.to_numeric(df["context_only"], errors="coerce").fillna(0).eq(0)].copy()
    else:
        detected = df.copy()

    numeric_fields = [
        "pixel_count", "max_reflectivity_dbz", "mean_reflectivity_dbz",
        "reflectivity_gradient_p90_dbkm", "reflectivity_contrast_db",
        "velocity_contrast_kt", "velocity_gradient_p90_ktkm",
        "bbox_aspect_ratio", "candidate_rank_score",
    ]
    for col in numeric_fields:
        if col in detected.columns:
            detected[col] = pd.to_numeric(detected[col], errors="coerce")

    evidence_counts: dict[str, int] = {}
    if "detection_evidence" in detected.columns:
        for value in detected["detection_evidence"]:
            for item in _evidence(value):
                evidence_counts[item] = evidence_counts.get(item, 0) + 1

    rank = detected["candidate_rank_score"].dropna() if "candidate_rank_score" in detected.columns else pd.Series(dtype=float)
    aspect = detected["bbox_aspect_ratio"].dropna() if "bbox_aspect_ratio" in detected.columns else pd.Series(dtype=float)
    edge = (
        detected["touches_grid_edge"].astype(str).str.lower().isin({"true", "1"})
        if "touches_grid_edge" in detected.columns else pd.Series(False, index=detected.index)
    )

    mode_counts = (
        detected["object_mode"].fillna("unknown").astype(str).value_counts().to_dict()
        if "object_mode" in detected.columns else {}
    )
    rescue_count = int(
        detected.get("velocity_rescue", pd.Series(False, index=detected.index))
        .astype(str).str.lower().isin({"true", "1"}).sum()
    )

    report = {
        "status": "complete",
        "source": str(source),
        "rows_total": int(len(df)),
        "detected_object_rows": int(len(detected)),
        "context_only_rows": int(len(df) - len(detected)),
        "unique_scans": int(detected["scan_time_utc"].nunique()) if "scan_time_utc" in detected.columns else 0,
        "radar_sites": sorted(detected["radar_site"].dropna().astype(str).unique()) if "radar_site" in detected.columns else [],
        "unique_track_ids": int(detected["track_id"].nunique()) if "track_id" in detected.columns else 0,
        "object_mode_counts": {str(k): int(v) for k, v in mode_counts.items()},
        "detection_evidence_counts": {str(k): int(v) for k, v in sorted(evidence_counts.items())},
        "velocity_rescue_rows": rescue_count,
        "edge_touch_rows": int(edge.sum()),
        "high_aspect_rows_ge_20": int((aspect >= 20).sum()),
        "candidate_rank": {
            "count": int(len(rank)),
            "mean": float(rank.mean()) if len(rank) else None,
            "median": float(rank.median()) if len(rank) else None,
            "p90": float(rank.quantile(0.90)) if len(rank) else None,
            "priority_ge_80": int((rank >= 80).sum()),
            "strong_65_to_79": int(((rank >= 65) & (rank < 80)).sum()),
            "candidate_50_to_64": int(((rank >= 50) & (rank < 65)).sum()),
            "weak_35_to_49": int(((rank >= 35) & (rank < 50)).sum()),
            "low_lt_35": int((rank < 35).sum()),
        },
        "detector_qc_flags": {
            "no_detected_objects": bool(detected.empty),
            "high_edge_fraction": bool(len(detected) and edge.mean() > 0.50),
            "high_extreme_aspect_fraction": bool(len(detected) and (aspect >= 20).mean() > 0.25),
            "excessive_low_rank_fraction": bool(len(rank) and (rank < 35).mean() > 0.75),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.input_csv, args.output), indent=2))


if __name__ == "__main__":
    main()
