"""Audit the mandatory radar + environment training data contract.

Every supervised positive/null training row must carry:
  * full-scan base reflectivity context,
  * full-scan base velocity context, and
  * a common cross-era environmental package available from NARR/RUC/RAP.

Rows that do not meet the contract remain useful for QC, but model training
must stop rather than silently imputing an absent data source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

REQUIRED_POPULATIONS = ("verified_case_context", "winter_null_candidate")

ENVIRONMENT_REQUIRED_FIELDS = (
    "cape_jkg",
    "pwat_mm",
    "temperature_2m_k",
    "dewpoint_2m_k",
    "rh_2m_pct",
    "u10_ms",
    "v10_ms",
)

BASE_REFLECTIVITY_FIELDS = (
    "base_reflectivity_mean_dbz",
    "base_reflectivity_max_dbz",
    "base_reflectivity_p90_dbz",
)

BASE_VELOCITY_FIELDS = (
    "base_velocity_mean_kt",
    "base_velocity_std_kt",
    "base_velocity_p90_abs_kt",
)

OBJECT_VELOCITY_FIELDS = (
    "velocity_mean_kt",
    "velocity_std_kt",
    "velocity_p90_abs_kt",
)

def _finite_count(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    present = [c for c in columns if c in frame.columns]
    if not present:
        return pd.Series(0, index=frame.index, dtype=int)
    numeric = frame[present].apply(pd.to_numeric, errors="coerce")
    return numeric.notna().sum(axis=1)

def audit(
    features_path: Path,
    output_path: Path | None = None,
    require_object_velocity: bool = True,
) -> dict:
    df = pd.read_csv(features_path)
    required = set(BASE_REFLECTIVITY_FIELDS + BASE_VELOCITY_FIELDS + ENVIRONMENT_REQUIRED_FIELDS)
    report = {
        "status": "pass",
        "features_path": str(features_path),
        "rows": int(len(df)),
        "required_populations": list(REQUIRED_POPULATIONS),
        "required_environment_fields": list(ENVIRONMENT_REQUIRED_FIELDS),
        "required_base_reflectivity_fields": list(BASE_REFLECTIVITY_FIELDS),
        "required_base_velocity_fields": list(BASE_VELOCITY_FIELDS),
        "require_object_velocity": bool(require_object_velocity),
        "missing_required_columns": sorted(required - set(df.columns)),
        "errors": [],
        "warnings": [],
    }
    if report["missing_required_columns"]:
        report["errors"].append("missing_required_contract_columns")
    elif "population" not in df.columns:
        report["errors"].append("missing_population")

    if report["errors"]:
        report["status"] = "fail"
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    d = df[df["population"].astype(str).isin(REQUIRED_POPULATIONS)].copy()
    report["training_contract_rows"] = int(len(d))
    report["population_counts"] = {
        str(k): int(v) for k, v in d["population"].value_counts(dropna=False).items()
    }
    if d.empty:
        report["errors"].append("no_positive_or_null_rows_for_contract")
        report["status"] = "fail"
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    d["_base_refl_count"] = _finite_count(d, BASE_REFLECTIVITY_FIELDS)
    d["_base_vel_count"] = _finite_count(d, BASE_VELOCITY_FIELDS)
    d["_env_count"] = _finite_count(d, ENVIRONMENT_REQUIRED_FIELDS)
    d["_object_vel_count"] = _finite_count(d, OBJECT_VELOCITY_FIELDS)

    refl_ok = d["_base_refl_count"] >= 1
    vel_ok = d["_base_vel_count"] >= 1
    env_ok = d["_env_count"] == len(ENVIRONMENT_REQUIRED_FIELDS)
    object_velocity_ok = d["_object_vel_count"] >= 1 if require_object_velocity else pd.Series(True, index=d.index)

    if "base_reflectivity_valid_fraction" in d.columns:
        refl_ok &= pd.to_numeric(d["base_reflectivity_valid_fraction"], errors="coerce").gt(0)
    if "base_velocity_valid_fraction" in d.columns:
        vel_ok &= pd.to_numeric(d["base_velocity_valid_fraction"], errors="coerce").gt(0)

    d["_radar_environment_contract_ok"] = refl_ok & vel_ok & env_ok & object_velocity_ok

    def summarize(group: pd.DataFrame) -> dict:
        return {
            "rows": int(len(group)),
            "base_reflectivity_complete": float(refl_ok.loc[group.index].mean()) if len(group) else 0.0,
            "base_velocity_complete": float(vel_ok.loc[group.index].mean()) if len(group) else 0.0,
            "environment_complete": float(env_ok.loc[group.index].mean()) if len(group) else 0.0,
            "object_velocity_complete": float(object_velocity_ok.loc[group.index].mean()) if len(group) else 0.0,
            "contract_complete": float(group["_radar_environment_contract_ok"].mean()) if len(group) else 0.0,
            "failed_rows": int((~group["_radar_environment_contract_ok"]).sum()),
        }

    report["population_summary"] = {}
    for population in REQUIRED_POPULATIONS:
        report["population_summary"][population] = summarize(
            d[d["population"].astype(str).eq(population)]
        )

    positive = d[d["population"].astype(str).eq("verified_case_context")]
    if "case_id" in positive.columns:
        report["positive_case_summary"] = {
            str(case_id): summarize(group)
            for case_id, group in positive.groupby("case_id", dropna=False)
        }
        report["positive_cases_with_any_failure"] = sorted(
            case_id for case_id, info in report["positive_case_summary"].items()
            if info["failed_rows"] > 0
        )

    nulls = d[d["population"].astype(str).eq("winter_null_candidate")]
    if "null_id" in nulls.columns:
        report["null_window_summary"] = {
            str(null_id): summarize(group)
            for null_id, group in nulls.groupby("null_id", dropna=False)
        }
        report["null_windows_with_any_failure"] = sorted(
            null_id for null_id, info in report["null_window_summary"].items()
            if info["failed_rows"] > 0
        )

    for population in REQUIRED_POPULATIONS:
        info = report["population_summary"][population]
        if info["rows"] == 0:
            report["errors"].append(f"population_missing:{population}")
        elif info["contract_complete"] < 1.0:
            report["errors"].append(f"population_contract_incomplete:{population}")

    failed = d[~d["_radar_environment_contract_ok"]]
    report["row_failures"] = int(len(failed))
    if not failed.empty:
        reasons = []
        for idx in failed.index:
            missing = []
            if not bool(refl_ok.loc[idx]):
                missing.append("base_reflectivity")
            if not bool(vel_ok.loc[idx]):
                missing.append("base_velocity")
            if not bool(env_ok.loc[idx]):
                missing.append("environment")
            if not bool(object_velocity_ok.loc[idx]):
                missing.append("object_velocity")
            reasons.append(";".join(missing))
        report["failure_reason_counts"] = {
            str(k): int(v) for k, v in pd.Series(reasons).value_counts().items()
        }
        report["errors"].append(f"contract_incomplete_rows:{len(failed)}")

    report["status"] = "fail" if report["errors"] else "pass"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--allow-missing-object-velocity",
        action="store_true",
        help="Require base radar velocity/environment, but do not require object-footprint velocity.",
    )
    args = parser.parse_args()
    report = audit(
        Path(args.features),
        Path(args.output),
        require_object_velocity=not args.allow_missing_object_velocity,
    )
    print(json.dumps(report, indent=2))
    if report["status"] != "pass":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
