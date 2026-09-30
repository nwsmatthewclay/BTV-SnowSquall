"""Audit the leakage, identity, cohort, and horizon integrity of an expansion feature table."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd

HORIZONS = (15, 30, 45, 60)

def audit(features_path: Path, schema_path: Path, cases_path: Path | None = None) -> dict:
    df = pd.read_csv(features_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    report = {"status": "pass", "rows": int(len(df)), "errors": [], "warnings": []}

    predictors = list(schema.get("predictor_columns", []))
    operational = list(schema.get("operational_predictor_columns", []))
    targets = set(schema.get("target_columns", []))

    if schema.get("future_information_policy") != "current_and_past_only":
        report["errors"].append("schema_future_information_policy_not_current_and_past_only")
    missing_predictors = sorted(set(predictors) - set(df.columns))
    if missing_predictors:
        report["errors"].append(f"missing_schema_predictors:{missing_predictors}")
    if not set(operational).issubset(predictors):
        report["errors"].append("operational_predictors_not_subset_of_predictors")
    if set(predictors) & targets:
        report["errors"].append("target_columns_present_in_predictor_list")
    if "row_identity_key" in df.columns and df["row_identity_key"].duplicated().any():
        report["errors"].append(f"duplicate_row_identity_keys:{int(df['row_identity_key'].duplicated().sum())}")

    if "scan_time_utc" in df.columns:
        times = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
        report["invalid_scan_times"] = int(times.isna().sum())
        if report["invalid_scan_times"]:
            report["errors"].append("invalid_scan_times")
    else:
        report["errors"].append("missing_scan_time_utc")

    group_cols = [c for c in ("population_track_key", "object_id") if c in df.columns]
    if "population_track_key" in df.columns and "scan_time_utc" in df.columns:
        ordered = df.assign(_t=pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")).sort_values(["population_track_key", "_t"])
        backwards = ordered.groupby("population_track_key")["_t"].diff().dt.total_seconds().lt(0).sum()
        report["backward_time_steps"] = int(backwards)
        if backwards:
            report["errors"].append("backward_time_steps")

    if "population" in df.columns:
        report["population_counts"] = {str(k): int(v) for k, v in df["population"].value_counts(dropna=False).items()}
        positive = df[df["population"].eq("verified_case_context")]
        report["positive_rows"] = int(len(positive))
        report["positive_cases"] = int(positive["case_id"].nunique()) if "case_id" in positive.columns else 0
        if "supervision_class" in positive.columns:
            unsupervised = int((positive["supervision_class"] != "supervised_positive").sum())
            report["positive_rows_without_supervised_provenance"] = unsupervised
            if unsupervised:
                report["errors"].append(f"positive_rows_without_supervised_provenance:{unsupervised}")
        nulls = df[df["population"].eq("winter_null_candidate")]
        report["null_rows"] = int(len(nulls))
        report["null_windows"] = int(nulls["null_id"].nunique()) if "null_id" in nulls.columns else 0
    else:
        report["errors"].append("missing_population")

    horizon_report = {}
    for h in HORIZONS:
        col = f"squall_onset_within_{h}m"
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            horizon_report[str(h)] = {
                "rows_with_target": int(s.notna().sum()),
                "positive_rows": int((s == 1).sum()),
                "negative_rows": int((s == 0).sum()),
            }
        else:
            horizon_report[str(h)] = {"rows_with_target": 0, "positive_rows": 0, "negative_rows": 0, "missing": True}
            report["warnings"].append(f"missing_target:{col}")
    report["horizons"] = horizon_report

    if cases_path is not None:
        cases = pd.read_csv(cases_path)
        case_ids = set(cases["case_id"].astype(str)) if "case_id" in cases.columns else set()
        positive_ids = set(df.loc[df.get("population", pd.Series(index=df.index)).eq("verified_case_context"), "case_id"].dropna().astype(str)) if "case_id" in df.columns else set()
        outside = sorted(positive_ids - case_ids)
        report["cohort_case_count"] = len(case_ids)
        report["positive_cases_outside_current_supervised_cohort"] = outside[:50]
        report["positive_cases_outside_current_supervised_cohort_count"] = len(outside)
        if outside:
            report["warnings"].append("positive_rows_include_cases_outside_current_supervised_cohort")

    report["status"] = "fail" if report["errors"] else "pass"
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("features")
    p.add_argument("--schema", required=True)
    p.add_argument("--cases", default=None)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    report = audit(Path(a.features), Path(a.schema), Path(a.cases) if a.cases else None)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] == "fail":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
