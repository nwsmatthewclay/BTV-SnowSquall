"""Create weakly supervised SQW warning-object labels from radar object scans.

This is a pretraining/research population only. It does not claim that every
object near a warning centroid is the physical squall. Warning verification and
object-to-warning proximity are retained as separate evidence dimensions.
"""
from __future__ import annotations

import argparse
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd

HORIZONS = (15, 30, 45, 60)
ASSOCIATION_RADIUS_KM = 60.0


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = radians(float(lat1)), radians(float(lat2))
    dp = radians(float(lat2) - float(lat1))
    dl = radians(float(lon2) - float(lon1))
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371.0 * 2.0 * asin(min(1.0, sqrt(a)))


def build(object_csv: Path, warnings_csv: Path, output: Path):
    objects = pd.read_csv(object_csv)
    warnings = pd.read_csv(warnings_csv)

    required_objects = {"scan_time_utc", "centroid_lat", "centroid_lon", "radar_site", "object_id", "case_id"}
    missing = required_objects - set(objects.columns)
    if missing:
        raise ValueError(f"Object scans missing required fields: {sorted(missing)}")

    required_warnings = {"case_id", "warning_issue_utc", "lat", "lon", "iem_verified"}
    missing = required_warnings - set(warnings.columns)
    if missing:
        raise ValueError(f"Warning table missing required fields: {sorted(missing)}")

    objects["scan_dt"] = pd.to_datetime(objects["scan_time_utc"], utc=True, errors="coerce")
    warnings["warning_dt"] = pd.to_datetime(warnings["warning_issue_utc"], utc=True, errors="coerce")
    warning_map = warnings.drop_duplicates("case_id").set_index("case_id")

    rows = []
    for _, obj in objects.dropna(subset=["scan_dt"]).iterrows():
        case_id = str(obj.get("case_id") or "")
        if not case_id or case_id not in warning_map.index:
            continue
        warning = warning_map.loc[case_id]
        warning_dt = warning["warning_dt"]
        if pd.isna(warning_dt) or pd.isna(warning.get("lat")) or pd.isna(warning.get("lon")):
            continue

        obj_lat = obj.get("centroid_lat")
        obj_lon = obj.get("centroid_lon")
        if pd.isna(obj_lat) or pd.isna(obj_lon):
            continue

        dist = distance_km(obj_lat, obj_lon, warning["lat"], warning["lon"])
        lead_min = (warning_dt - obj["scan_dt"]).total_seconds() / 60.0

        row = obj.to_dict()
        row["warning_issue_utc"] = warning_dt.isoformat()
        row["warning_lat"] = float(warning["lat"])
        row["warning_lon"] = float(warning["lon"])
        row["warning_distance_km"] = float(dist)
        row["warning_iem_verified"] = bool(warning.get("iem_verified", False))
        row["warning_verifying_lsr_count"] = int(warning.get("verifying_lsr_count", 0) or 0)
        row["warning_supervision_class"] = str(warning.get("supervision_class") or "warning_only")

        nearby = dist <= ASSOCIATION_RADIUS_KM
        pre_warning = lead_min >= 0
        row["weak_warning_associated"] = bool(nearby)
        row["weak_label_status"] = "weak_positive_candidate" if nearby and pre_warning else (
            "pre_warning_nonassociated" if pre_warning else "post_warning_context"
        )
        row["lead_time_to_warning_min"] = lead_min

        for horizon in HORIZONS:
            row[f"weak_onset_within_{horizon}m"] = int(
                nearby and pre_warning and lead_min <= horizon
            )

        # Conservative weak-training weight: IEM-verified warnings are stronger
        # supervision than warning-only cases, but both remain below physical-truth
        # labels in downstream policy.
        base = 1.0 if bool(warning.get("iem_verified", False)) else 0.5
        row["weak_sample_weight"] = base if row["weak_label_status"] == "weak_positive_candidate" else 0.1

        rows.append(row)

    result = pd.DataFrame(rows).drop(columns=["scan_dt"], errors="ignore")
    result.to_csv(output, index=False)

    summary = {
        "object_rows": int(len(result)),
        "weak_positive_rows": int((result["weak_label_status"] == "weak_positive_candidate").sum()) if not result.empty else 0,
        "pre_warning_nonassociated_rows": int((result["weak_label_status"] == "pre_warning_nonassociated").sum()) if not result.empty else 0,
        "verified_warning_rows": int(result["warning_iem_verified"].sum()) if not result.empty else 0,
        "association_radius_km": ASSOCIATION_RADIUS_KM,
        "policy": "Weak warning supervision is isolated from physical-truth labels. It may support radar-feature pretraining but is not eligible for operational release or final BTV calibration without independent verification.",
    }
    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--objects", required=True)
    parser.add_argument("--warnings", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(Path(args.objects), Path(args.warnings), Path(args.output))


if __name__ == "__main__":
    main()
