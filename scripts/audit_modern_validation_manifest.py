"""Validate modern independent-validation candidate manifests.

Candidates in this manifest are provenance anchors only. This audit prevents
their accidental use as historical training truth before independent
reconstruction and verification are complete.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED = {
    "case_id",
    "event_date_utc",
    "radar_site",
    "truth_role",
    "independence_status",
    "evidence_source",
}

ALLOWED_RADARS = {"KCXX", "KTYX"}


def audit(path: Path) -> dict:
    df = pd.read_csv(path)
    missing = sorted(REQUIRED - set(df.columns))
    if missing:
        raise ValueError(f"Missing required manifest columns: {missing}")

    issues = []
    if df["case_id"].duplicated().any():
        issues.append("duplicate_case_id")
    if (~df["radar_site"].isin(ALLOWED_RADARS)).any():
        issues.append("unsupported_radar_site")
    if (~df["truth_role"].eq("validation_candidate")).any():
        issues.append("non_validation_truth_role")
    if (~df["independence_status"].eq("independent_candidate")).any():
        issues.append("candidate_not_marked_independent")
    if df["event_date_utc"].isna().any():
        issues.append("missing_event_date")
    if df["evidence_source"].isna().any() or df["evidence_source"].eq("").any():
        issues.append("missing_evidence_source")

    summary = {
        "records": int(len(df)),
        "case_ids": df["case_id"].astype(str).tolist(),
        "radar_sites": sorted(df["radar_site"].astype(str).unique()),
        "truth_roles": sorted(df["truth_role"].astype(str).unique()),
        "independence_statuses": sorted(df["independence_status"].astype(str).unique()),
        "issues": issues,
        "training_eligible": False,
        "training_eligibility_reason": "candidate_manifest_only; requires independent reconstruction and verification",
    }

    if issues:
        raise ValueError("Modern validation manifest QC failed: " + ", ".join(issues))

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    summary = audit(Path(args.manifest))
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
