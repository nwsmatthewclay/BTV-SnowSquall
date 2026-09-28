"""Audit time matching and provider-era integrity of attached environments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from processing.environment import provider_for_time


def audit(path: Path, max_age_minutes: float = 180.0) -> dict:
    df = pd.read_csv(path)
    required = {"scan_time_utc", "environment_valid_time_utc", "environment_source"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing environment audit columns: {missing}")

    scan = pd.to_datetime(df["scan_time_utc"], utc=True, errors="coerce")
    valid = pd.to_datetime(df["environment_valid_time_utc"], utc=True, errors="coerce")
    attached = valid.notna() & df["environment_source"].notna()

    future_rows = attached & (valid > scan)
    stale_rows = attached & (((scan - valid).dt.total_seconds() / 60.0) > max_age_minutes)
    bad_provider = []
    for idx in df.index[attached]:
        expected = provider_for_time(scan.loc[idx].to_pydatetime())
        actual = str(df.loc[idx, "environment_source"])
        if actual != expected:
            bad_provider.append(int(idx))

    summary = {
        "records": int(len(df)),
        "environment_attached_records": int(attached.sum()),
        "environment_missing_records": int((~attached).sum()),
        "future_environment_records": int(future_rows.sum()),
        "stale_environment_records": int(stale_rows.sum()),
        "wrong_provider_era_records": len(bad_provider),
        "provider_counts": df.loc[attached, "environment_source"].value_counts(dropna=False).to_dict(),
    }

    if future_rows.any():
        raise ValueError(f"{int(future_rows.sum())} rows use a future environment analysis")
    if stale_rows.any():
        raise ValueError(f"{int(stale_rows.sum())} rows exceed the {max_age_minutes:.0f}-minute environment age limit")
    if bad_provider:
        raise ValueError(f"{len(bad_provider)} rows use an environment provider outside its configured historical era")

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-age-minutes", type=float, default=180.0)
    args = parser.parse_args()

    summary = audit(Path(args.input_csv), max_age_minutes=args.max_age_minutes)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
