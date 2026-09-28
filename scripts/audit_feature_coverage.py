"""Audit realized feature coverage against the canonical feature schema.

This is a transparency/QC report. A feature can be defined in the schema and
still be legitimately unavailable for a provider or historical era. The audit
reports coverage without inventing values or failing merely because an optional
scientific field is sparse.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


FIELD_ALIASES = {
    "scan_time": ("scan_time", "scan_time_utc"),
    "lat": ("lat", "centroid_lat"),
    "lon": ("lon", "centroid_lon"),
    "reflectivity_max_dbz": ("reflectivity_max_dbz", "max_reflectivity_dbz"),
    "reflectivity_mean_dbz": ("reflectivity_mean_dbz", "mean_reflectivity_dbz"),
    "motion_dir_deg": ("motion_dir_deg", "motion_direction_deg"),
}

def audit(input_csv: Path, schema_csv: Path) -> dict:
    frame = pd.read_csv(input_csv)
    schema = pd.read_csv(schema_csv)

    required_identity = {"scan_time_utc", "object_id", "radar_site"}
    missing_identity = sorted(required_identity - set(frame.columns))
    if missing_identity:
        raise ValueError(f"Missing core identity fields: {missing_identity}")

    rows = []
    for field in schema["field"].astype(str):
        aliases = FIELD_ALIASES.get(field, (field,))
        actual = next((candidate for candidate in aliases if candidate in frame.columns), None)
        schema_row = schema.loc[schema["field"].astype(str).eq(field)].iloc[0]
        group_value = schema_row["group"]
        availability_policy = schema_row.get("availability_policy", "unspecified")
        if actual is None:
            rows.append({
                "field": field,
                "group": group_value,
                "records": len(frame),
                "non_null": 0,
                "coverage_pct": 0.0,
                "present": False,
                "actual_field": None,
                "availability_policy": availability_policy,
                "coverage_interpretation": "expected_gap" if availability_policy in {"modern_2014_plus", "dualpol_era_dependent", "environment_provider_dependent", "observation_dependent", "target_or_review"} else "unexpected_gap",
            })
            continue

        series = frame[actual]
        non_null = int(series.notna().sum())
        rows.append({
            "field": field,
            "group": schema.loc[schema["field"].astype(str).eq(field), "group"].iloc[0],
            "records": int(len(frame)),
            "non_null": non_null,
            "coverage_pct": round(100.0 * non_null / len(frame), 2) if len(frame) else 0.0,
            "present": True,
            "actual_field": actual,
            "availability_policy": availability_policy,
            "coverage_interpretation": "populated" if non_null > 0 else ("expected_gap" if availability_policy in {"modern_2014_plus", "dualpol_era_dependent", "environment_provider_dependent", "observation_dependent", "target_or_review"} else "unexpected_gap"),
        })

    detail = pd.DataFrame(rows)
    group = (
        detail.groupby("group", dropna=False)
        .agg(
            fields=("field", "count"),
            fields_present=("present", "sum"),
            fields_with_values=("coverage_pct", lambda s: int((s > 0).sum())),
            mean_field_coverage_pct=("coverage_pct", "mean"),
        )
        .reset_index()
    )
    group["mean_field_coverage_pct"] = group["mean_field_coverage_pct"].round(2)

    return {
        "records": int(len(frame)),
        "core_identity_missing": missing_identity,
        "field_coverage": detail.to_dict(orient="records"),
        "group_coverage": group.to_dict(orient="records"),
        "zero_coverage_fields": detail.loc[
            detail["coverage_pct"].eq(0), "field"
        ].tolist(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--schema", default="schema/feature_schema.csv")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    summary = audit(Path(args.input_csv), Path(args.schema))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Feature coverage audit: {summary['records']:,} records")
    for row in summary["group_coverage"]:
        print(
            f"{row['group']}: {row['fields_with_values']}/{row['fields']} fields populated "
            f"({row['fields_present']} defined); mean field coverage={row['mean_field_coverage_pct']:.1f}%"
        )
    print(f"Zero-coverage fields: {len(summary['zero_coverage_fields'])}")


if __name__ == "__main__":
    main()
