"""Profile the training population for coverage, balance, and failure modes.

This is a dataset-health audit only. It does not relabel cases or select a model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


HORIZONS = (15, 30, 45, 60)
RADAR_REQUIRED = (
    "base_reflectivity_mean_dbz",
    "base_reflectivity_max_dbz",
    "base_velocity_mean_kt",
    "base_velocity_std_kt",
)
ENVIRONMENT_HINTS = (
    "cape_jkg",
    "mlcape_jkg",
    "mucape_jkg",
    "snsq",
    "pwat_mm",
    "srh01_m2s2",
    "shear_0_6km_ms",
)


def _count_unique(df: pd.DataFrame, column: str) -> int | None:
    return int(df[column].nunique(dropna=True)) if column in df.columns else None


def _distribution(df: pd.DataFrame, column: str) -> dict:
    if column not in df.columns:
        return {}
    return {
        str(k): int(v)
        for k, v in df[column].value_counts(dropna=False).items()
    }


def _coverage(df: pd.DataFrame, columns: list[str]) -> dict:
    out = {}
    for col in columns:
        if col not in df.columns:
            out[col] = {"present": False, "fraction": 0.0}
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        out[col] = {
            "present": True,
            "fraction": round(float(numeric.notna().mean()), 4),
        }
    return out


def audit(path: Path) -> dict:
    df = pd.read_csv(path)
    report = {
        "dataset": str(path),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "errors": [],
        "warnings": [],
    }

    if "row_identity_key" in df.columns:
        report["unique_row_identity"] = int(df["row_identity_key"].nunique(dropna=True))
        dup = int(df["row_identity_key"].duplicated().sum())
        report["duplicate_row_identity"] = dup
        if dup:
            report["errors"].append(f"duplicate_row_identity:{dup}")

    report["unique_cases"] = _count_unique(df, "case_id")
    report["unique_null_windows"] = _count_unique(df, "null_id")
    report["unique_episodes"] = _count_unique(df, "episode_id")
    report["unique_objects"] = _count_unique(df, "object_id")
    report["radars"] = sorted(df["radar_site"].dropna().astype(str).unique()) if "radar_site" in df.columns else []

    if "scan_time_utc" in df.columns:
        t = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
        report["time_range_utc"] = {
            "min": t.min().isoformat() if t.notna().any() else None,
            "max": t.max().isoformat() if t.notna().any() else None,
            "invalid": int(t.isna().sum()),
        }
        if report["time_range_utc"]["invalid"]:
            report["errors"].append("invalid_scan_time_utc")

    if "population" in df.columns:
        report["population_counts"] = _distribution(df, "population")
    if "supervision_class" in df.columns:
        report["supervision_counts"] = _distribution(df, "supervision_class")
    if "activity_class" in df.columns:
        report["null_activity_counts"] = _distribution(df, "activity_class")

    report["radar_population_counts"] = (
        df.groupby([c for c in ["radar_site", "population"] if c in df.columns], dropna=False)
        .size()
        .to_dict()
        if "radar_site" in df.columns and "population" in df.columns
        else {}
    )

    if "scan_time_utc" in df.columns:
        years = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce").dt.year
        report["rows_by_year"] = {
            str(int(k)): int(v) for k, v in years.dropna().value_counts().sort_index().items()
        }

    horizon_report = {}
    for h in HORIZONS:
        col = f"squall_onset_within_{h}m"
        if col not in df.columns:
            horizon_report[str(h)] = {"present": False}
            continue
        y = pd.to_numeric(df[col], errors="coerce")
        horizon_report[str(h)] = {
            "present": True,
            "rows_with_target": int(y.notna().sum()),
            "positive_rows": int((y == 1).sum()),
            "negative_rows": int((y == 0).sum()),
            "positive_rate": round(float((y == 1).mean()), 5),
        }
    report["horizons"] = horizon_report

    group_col = "split_group" if "split_group" in df.columns else (
        "population_track_key" if "population_track_key" in df.columns else None
    )
    if group_col:
        groups = df[group_col].astype(str)
        sizes = groups.value_counts()
        report["independent_groups"] = int(sizes.size)
        report["largest_group_fraction"] = round(float(sizes.iloc[0] / max(len(df), 1)), 5)
        if sizes.size < 3:
            report["warnings"].append("fewer_than_3_independent_groups")

        if "population" in df.columns:
            positive = df[df["population"].eq("verified_case_context")]
            if "case_id" in positive.columns:
                positive_cases = positive["case_id"].dropna().astype(str).value_counts()
                if not positive_cases.empty:
                    report["positive_case_top_share"] = round(
                        float(positive_cases.iloc[0] / max(len(positive), 1)), 5
                    )
                    if len(positive_cases) < 5:
                        report["warnings"].append("fewer_than_5_supervised_positive_cases")
                    if positive_cases.iloc[0] / max(len(positive), 1) > 0.50:
                        report["warnings"].append("one_positive_case_exceeds_50pct_of_positive_rows")

            nulls = df[df["population"].eq("winter_null_candidate")]
            if "null_id" in nulls.columns:
                null_counts = nulls["null_id"].dropna().astype(str).value_counts()
                if not null_counts.empty:
                    report["largest_null_window_share"] = round(
                        float(null_counts.iloc[0] / max(len(nulls), 1)), 5
                    )
                    if null_counts.iloc[0] / max(len(nulls), 1) > 0.25:
                        report["warnings"].append("one_null_window_exceeds_25pct_of_null_rows")

    report["required_radar_field_coverage"] = _coverage(df, list(RADAR_REQUIRED))
    radar_required_fraction = min(
        [v["fraction"] for v in report["required_radar_field_coverage"].values() if v["present"]]
        or [0.0]
    )
    report["minimum_required_radar_field_fraction"] = round(float(radar_required_fraction), 4)

    report["environment_hint_coverage"] = _coverage(df, list(ENVIRONMENT_HINTS))
    if radar_required_fraction < 0.90:
        report["warnings"].append("radar_contract_coverage_below_90pct")

    if "environment_contract_ok" in df.columns:
        env_ok = df["environment_contract_ok"].fillna(False).astype(bool)
        report["environment_contract_ok_fraction"] = round(float(env_ok.mean()), 4)
        if env_ok.mean() < 0.90:
            report["warnings"].append("environment_contract_below_90pct")

    if "track_quality" in df.columns:
        report["track_quality"] = _distribution(df, "track_quality")
    if "qc_status" in df.columns:
        report["qc_status"] = _distribution(df, "qc_status")

    operational = []
    if "operational_predictor_columns" in df.columns:
        operational = [str(x) for x in df["operational_predictor_columns"].dropna().unique()]
    report["top_missing_numeric_fields"] = []
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    for col in sorted(numeric_cols, key=lambda c: float(df[c].isna().mean()), reverse=True)[:30]:
        report["top_missing_numeric_fields"].append({
            "field": col,
            "missing_fraction": round(float(df[col].isna().mean()), 4),
        })

    report["status"] = "fail" if report["errors"] else "pass"
    if report["warnings"]:
        report["status"] = "pass_with_warnings"

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("features")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = audit(Path(args.features))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
