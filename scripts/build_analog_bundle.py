"""Build a frozen historical analog reference bundle."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.snow_squall.analogs import AnalogLibrary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-cases", type=int, default=0)
    args = parser.parse_args()

    frame = pd.read_csv(args.features_csv)
    if "scan_time_utc" not in frame.columns:
        raise SystemExit("features table requires scan_time_utc")

    frame["_scan_dt"] = pd.to_datetime(
        frame["scan_time_utc"], utc=True, errors="coerce"
    )
    frame = frame[frame["_scan_dt"].notna()].drop(columns=["_scan_dt"])
    if frame.empty:
        raise SystemExit("features table contains no valid timestamps")

    if args.max_cases:
        cases = sorted(frame.get(
            "case_id", pd.Series("", index=frame.index)
        ).astype(str).unique())
        keep = set(cases[-args.max_cases:])
        frame = frame[
            frame.get("case_id", pd.Series("", index=frame.index)).astype(str).isin(keep)
        ].copy()

    library = AnalogLibrary.fit(frame)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    library.save(output)

    print(f"Analog bundle: {output}")
    print(f"Reference rows: {len(frame)}")
    print(f"Reference groups: {len(set(library.groups))}")
    print(f"Feature count: {len(library.feature_columns)}")


if __name__ == "__main__":
    main()
