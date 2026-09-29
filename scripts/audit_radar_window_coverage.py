"""Audit Level-II volume coverage for every manifest row.

This separates missing radar acquisition from a genuine zero-object window.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

STAMP_RE = re.compile(r"^(?P<radar>K[A-Z0-9]{3})(?P<stamp>\d{8}_\d{6})")


def volume_time(path: Path):
    match = STAMP_RE.match(path.name)
    if not match:
        return None
    try:
        return pd.to_datetime(match.group("stamp"), format="%Y%m%d_%H%M%S", utc=True)
    except Exception:
        return None


def audit(manifest_path: Path, raw_root: Path, min_fraction: float) -> dict:
    manifest = pd.read_csv(manifest_path)
    required = {"window_start_utc", "window_end_utc", "radar_site"}
    missing = sorted(required - set(manifest.columns))
    if missing:
        raise ValueError(f"Manifest missing columns: {missing}")

    rows = []
    for i, row in manifest.iterrows():
        start = pd.to_datetime(row["window_start_utc"], utc=True, errors="coerce")
        end = pd.to_datetime(row["window_end_utc"], utc=True, errors="coerce")
        radar = str(row["radar_site"])
        identifier = (
            row.get("case_id")
            or row.get("null_id")
            or row.get("window_id")
            or f"row_{i}"
        )
        files = []
        radar_root = raw_root / radar
        if radar_root.exists():
            for path in radar_root.rglob("*"):
                if path.is_file():
                    t = volume_time(path)
                    if t is not None and pd.notna(start) and pd.notna(end) and start <= t <= end:
                        files.append(path)

        rows.append({
            "identifier": str(identifier),
            "radar_site": radar,
            "window_start_utc": start.isoformat() if pd.notna(start) else None,
            "window_end_utc": end.isoformat() if pd.notna(end) else None,
            "volume_count": len(files),
            "status": "has_level2" if files else "no_level2",
        })

    details = pd.DataFrame(rows)
    expected = len(details)
    populated = int((details["volume_count"] > 0).sum()) if expected else 0
    fraction = populated / expected if expected else 0.0
    no_data = details.loc[details["volume_count"] == 0, "identifier"].tolist()

    summary = {
        "manifest_rows": expected,
        "rows_with_level2": populated,
        "rows_without_level2": len(no_data),
        "coverage_fraction": fraction,
        "minimum_coverage_fraction": min_fraction,
        "passed": fraction >= min_fraction,
        "no_level2_identifiers": no_data,
        "by_radar": (
            details.groupby("radar_site")["volume_count"]
            .agg(["count", "sum", lambda s: int((s == 0).sum())])
            .rename(columns={"<lambda_0>": "rows_without_level2"})
            .reset_index()
            .to_dict(orient="records")
            if expected else []
        ),
        "rows": details.to_dict(orient="records"),
    }

    if fraction < min_fraction:
        raise ValueError(
            f"Only {populated}/{expected} manifest rows have Level-II volumes "
            f"({fraction:.1%}); minimum is {min_fraction:.1%}. "
            f"No-data rows: {no_data}"
        )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("raw_root")
    parser.add_argument("--report", required=True)
    parser.add_argument("--min-fraction", type=float, default=0.75)
    args = parser.parse_args()

    summary = audit(
        Path(args.manifest),
        Path(args.raw_root),
        args.min_fraction,
    )
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
