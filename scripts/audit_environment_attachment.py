"""Audit time matching and provider-era integrity of attached environments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from processing.environment import provider_for_time

DEFAULT_MAX_AGE_MINUTES = {"NARR": 360.0, "RUC": 180.0, "RAP": 180.0}


def audit(path: Path, max_age_minutes: float | None = None) -> dict:
    df = pd.read_csv(path)
    required = {"scan_time_utc", "environment_valid_time_utc", "environment_source"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing environment audit columns: {missing}")

    scan = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    valid = pd.to_datetime(df["environment_valid_time_utc"], utc=True, errors="coerce")
    attached = valid.notna() & df["environment_source"].notna()

    future_rows = attached & (valid > scan)
    ages = (scan - valid).dt.total_seconds() / 60.0
    stale_rows = pd.Series(False, index=df.index)
    bad_provider = []
    for idx in df.index[attached]:
        expected = provider_for_time(scan.loc[idx].to_pydatetime())
        actual = str(df.loc[idx, "environment_source"])
        if actual != expected:
            bad_provider.append(int(idx))
        limit = (
            float(max_age_minutes)
            if max_age_minutes is not None
            else DEFAULT_MAX_AGE_MINUTES[expected]
        )
        if float(ages.loc[idx]) > limit:
            stale_rows.loc[idx] = True

    missing_by_case = {}
    case_coverage = {}
    if "case_id" in df.columns:
        valid_cases = df["case_id"].notna()
        missing_by_case = (
            df.loc[~attached & valid_cases, "case_id"]
            .astype(str)
            .value_counts()
            .to_dict()
        )
        totals = df.loc[valid_cases].groupby("case_id").size()
        attached_totals = df.loc[attached & valid_cases].groupby("case_id").size()
        for case_id, total in totals.items():
            count = int(attached_totals.get(case_id, 0))
            case_coverage[str(case_id)] = {
                "records": int(total),
                "attached": count,
                "missing": int(total - count),
                "attachment_fraction": count / int(total) if total else 0.0,
            }

    missing_by_radar = {}
    radar_coverage = {}
    if "radar_site" in df.columns:
        valid_radar = df["radar_site"].notna()
        missing_by_radar = (
            df.loc[~attached, "radar_site"]
            .fillna("unknown")
            .astype(str)
            .value_counts()
            .to_dict()
        )
        totals = df.loc[valid_radar].groupby("radar_site").size()
        attached_totals = df.loc[attached & valid_radar].groupby("radar_site").size()
        for radar, total in totals.items():
            count = int(attached_totals.get(radar, 0))
            radar_coverage[str(radar)] = {
                "records": int(total),
                "attached": count,
                "missing": int(total - count),
                "attachment_fraction": count / int(total) if total else 0.0,
            }

    summary = {
        "records": int(len(df)),
        "environment_attached_records": int(attached.sum()),
        "environment_missing_records": int((~attached).sum()),
        "attachment_fraction": float(attached.mean()) if len(df) else 0.0,
        "future_environment_records": int(future_rows.sum()),
        "stale_environment_records": int(stale_rows.sum()),
        "wrong_provider_era_records": len(bad_provider),
        "provider_counts": df.loc[attached, "environment_source"].value_counts(dropna=False).to_dict(),
        "missing_by_case": missing_by_case,
        "case_coverage": case_coverage,
        "missing_by_radar": missing_by_radar,
        "radar_coverage": radar_coverage,
    }

    if future_rows.any():
        raise ValueError(f"{int(future_rows.sum())} rows use a future environment analysis")
    if stale_rows.any():
        limit_text = f"{max_age_minutes:.0f}-minute" if max_age_minutes is not None else "configured"
        raise ValueError(f"{int(stale_rows.sum())} rows exceed the {limit_text} environment age limit")
    if bad_provider:
        raise ValueError(f"{len(bad_provider)} rows use an environment provider outside its configured historical era")

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-age-minutes", type=float, default=None)
    args = parser.parse_args()

    summary = audit(Path(args.input_csv), max_age_minutes=args.max_age_minutes)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
