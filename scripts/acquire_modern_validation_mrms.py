"""Acquire archived MRMS lowest-elevation reflectivity for validation replay scans.

MRMS is supplemental verification context. No model feature fitting, threshold
selection, or probability scoring is performed here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd

from acquisition.mrms import find_latest, download


def acquire(replay_root: Path, output_root: Path) -> dict:
    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for geo_path in sorted(replay_root.glob("*/[0-9][0-9][0-9][0-9]_*.geojson")):
        payload = json.loads(geo_path.read_text(encoding="utf-8"))
        scan_time = payload.get("metadata", {}).get("scan_time_utc")
        radar_site = payload.get("metadata", {}).get("radar_id") or geo_path.parent.name
        case_id = geo_path.parent.name
        if not scan_time:
            rows.append({
                "case_id": case_id,
                "scan_time_utc": None,
                "radar_site": radar_site,
                "product": "mrms_lcref",
                "status": "missing_scan_time",
            })
            continue

        radar_time = pd.to_datetime(scan_time, utc=True).to_pydatetime()
        match = find_latest(radar_time, "mrms_lcref", max_age_minutes=120)
        if match is None:
            rows.append({
                "case_id": case_id,
                "scan_time_utc": scan_time,
                "radar_site": radar_site,
                "product": "mrms_lcref",
                "status": "unavailable",
            })
            continue

        case_out = output_root / case_id
        path = download(match, case_out)
        rows.append({
            "case_id": case_id,
            "scan_time_utc": scan_time,
            "radar_site": radar_site,
            "product": match.product,
            "mrms_valid_time_utc": match.valid_time.isoformat().replace("+00:00", "Z"),
            "age_minutes": round(match.age_minutes, 3),
            "status": "downloaded",
            "path": str(path),
            "source_url": match.url,
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_root / "mrms_validation_manifest.csv", index=False)
    summary = {
        "scan_records": int(len(df)),
        "downloaded": int((df.get("status", pd.Series(dtype=str)) == "downloaded").sum()),
        "unavailable": int((df.get("status", pd.Series(dtype=str)) == "unavailable").sum()),
        "max_age_minutes": (
            float(df["age_minutes"].max())
            if "age_minutes" in df.columns and df["age_minutes"].notna().any()
            else None
        ),
    }
    (output_root / "mrms_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    acquire(Path(args.replay_root), Path(args.output))


if __name__ == "__main__":
    main()
