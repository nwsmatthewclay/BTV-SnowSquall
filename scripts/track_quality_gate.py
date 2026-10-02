"""Apply the track-quality gate and preserve rejected/review tracks separately.

The gate is an engineering/QC filter for object histories. It does not claim that
a rejected track is meteorologically false; it means the track is not clean
enough for the first supervised training population.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.build_object_track_catalog import build_track_catalog


KEY_COLUMNS = (
    "population",
    "episode_id",
    "case_id",
    "null_id",
    "window_id",
    "radar_site",
    "object_id",
)


def _keys(frame: pd.DataFrame) -> pd.Series:
    columns = [c for c in KEY_COLUMNS if c in frame.columns]
    if "object_id" not in columns:
        raise ValueError("object_id is required")
    if "radar_site" not in columns:
        raise ValueError("radar_site is required")

    parts = []
    for column in columns:
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series):
            series = series.map(
                lambda value: "__NA__"
                if pd.isna(value)
                else str(value)
            )
        else:
            series = series.fillna("__NA__").astype(str)
        parts.append(column + "=" + series)
    return parts[0].str.cat(parts[1:], sep="|") if len(parts) > 1 else parts[0]


def apply_track_quality_gate(
    objects: pd.DataFrame,
    catalog: pd.DataFrame,
    min_score: float = 75.0,
    allow_review: bool = False,
):
    object_frame = objects.copy()
    catalog_frame = catalog.copy()

    if catalog_frame.empty:
        object_frame["track_quality_score"] = 0.0
        object_frame["track_quality_tier"] = "reject"
        object_frame["track_quality_gate"] = "reject"
        return object_frame, catalog_frame

    object_frame["_track_key"] = _keys(object_frame)
    catalog_frame["_track_key"] = _keys(catalog_frame)

    selected = catalog_frame[
        (
            catalog_frame["quality_score"].ge(float(min_score))
            & catalog_frame["quality_tier"].eq("pass")
        )
        | (
            bool(allow_review)
            & catalog_frame["quality_tier"].eq("review")
        )
    ].copy()

    status_map = catalog_frame.set_index("_track_key")[
        ["quality_score", "quality_tier", "qc_status", "qc_flags"]
    ].to_dict("index")

    def annotate(row):
        info = status_map.get(
            row["_track_key"],
            {
                "quality_score": 0.0,
                "quality_tier": "reject",
                "qc_status": "reject",
                "qc_flags": "track_not_in_catalog",
            },
        )
        return pd.Series(
            {
                "track_quality_score": info["quality_score"],
                "track_quality_tier": info["quality_tier"],
                "track_quality_gate": (
                    "pass"
                    if (
                        info["quality_tier"] == "pass"
                        and float(info["quality_score"]) >= min_score
                    )
                    or (
                        allow_review
                        and info["quality_tier"] == "review"
                    )
                    else "reject"
                ),
                "track_quality_flags": info["qc_flags"],
            }
        )

    annotations = object_frame.apply(annotate, axis=1)
    enriched = pd.concat([object_frame.drop(columns=["_track_key"]), annotations], axis=1)

    selected_keys = set(selected["_track_key"])
    pass_mask = enriched.apply(
        lambda row: _keys(pd.DataFrame([row])).iloc[0] in selected_keys,
        axis=1,
    )
    accepted = enriched.loc[pass_mask].copy()
    rejected = enriched.loc[~pass_mask].copy()

    catalog_frame = catalog_frame.drop(columns=["_track_key"])
    return accepted, rejected, enriched, catalog_frame


def build_audit(
    original_catalog: pd.DataFrame,
    original_objects: pd.DataFrame,
    accepted: pd.DataFrame,
    enriched: pd.DataFrame,
):
    track_tiers = (
        original_catalog["quality_tier"].value_counts().to_dict()
        if "quality_tier" in original_catalog.columns
        else {}
    )
    row_tiers = (
        enriched["track_quality_tier"].value_counts().to_dict()
        if "track_quality_tier" in enriched.columns
        else {}
    )
    return {
        "input_tracks": int(len(original_catalog)),
        "input_object_scans": int(len(original_objects)),
        "accepted_tracks": int(
            original_catalog["quality_tier"].eq("pass").sum()
        )
        if "quality_tier" in original_catalog.columns
        else 0,
        "accepted_object_scans": int(len(accepted)),
        "track_tiers": track_tiers,
        "object_scan_tiers": row_tiers,
        "accepted_row_fraction": (
            float(len(accepted) / len(original_objects))
            if len(original_objects)
            else 0.0
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--catalog", default=None)
    parser.add_argument("--output", required=True, help="Accepted/pass object scans.")
    parser.add_argument("--review-output", default=None, help="Review/reject object scans.")
    parser.add_argument("--annotated-output", default=None, help="All object scans with track-QC annotations.")
    parser.add_argument("--catalog-output", default=None, help="Rewritten/enriched track catalog.")
    parser.add_argument("--audit-output", default=None)
    parser.add_argument("--min-score", type=float, default=75.0)
    parser.add_argument(
        "--allow-review",
        action="store_true",
        help="Include review-tier tracks in the accepted output.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    objects = pd.read_csv(input_path)
    catalog_path = (
        Path(args.catalog)
        if args.catalog
        else input_path.with_name(f"{input_path.stem}_tracks.csv")
    )

    if args.catalog:
        catalog = pd.read_csv(catalog_path)
    else:
        catalog = build_track_catalog(input_path)

    accepted, rejected, enriched, catalog_clean = apply_track_quality_gate(
        objects,
        catalog,
        min_score=args.min_score,
        allow_review=args.allow_review,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    accepted.to_csv(output, index=False)

    if args.review_output:
        review_path = Path(args.review_output)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        rejected.to_csv(review_path, index=False)

    if args.annotated_output:
        annotated_path = Path(args.annotated_output)
        annotated_path.parent.mkdir(parents=True, exist_ok=True)
        enriched.to_csv(annotated_path, index=False)

    if args.catalog_output:
        catalog_output = Path(args.catalog_output)
        catalog_output.parent.mkdir(parents=True, exist_ok=True)
        catalog_clean.to_csv(catalog_output, index=False)

    audit = build_audit(catalog, objects, accepted, enriched)
    if args.audit_output:
        audit_path = Path(args.audit_output)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(audit, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
