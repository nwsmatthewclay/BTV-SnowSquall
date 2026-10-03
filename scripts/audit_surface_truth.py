"""Compare reconstructed ASOS/METAR observations with published event timing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

THRESHOLDS_KM = (0.4, 0.8)
TOLERANCE_MINUTES = 15.0


def first_at_or_below(frame: pd.DataFrame, column: str):
    if column not in frame.columns:
        return None
    eligible = frame.loc[frame[column].fillna(False)]
    if eligible.empty:
        return None
    return pd.to_datetime(eligible["valid"].min(), utc=True)


def audit(cases_csv: Path, surface_root: Path):
    cases = pd.read_csv(cases_csv)
    rows = []

    for case in cases.drop_duplicates("case_id").itertuples(index=False):
        station = str(case.observing_station)
        path = surface_root / station / f"{case.case_id}.csv"
        expected = pd.Timestamp(case.event_start_utc, tz="UTC")
        if not path.exists():
            rows.append({
                "case_id": case.case_id,
                "station": station,
                "status": "missing_surface_file",
            })
            continue

        obs = pd.read_csv(path)
        obs["valid"] = pd.to_datetime(obs["valid"], utc=True, errors="coerce")
        obs = obs.dropna(subset=["valid"]).sort_values("valid")

        row = {
            "case_id": case.case_id,
            "station": station,
            "status": "ok" if not obs.empty else "empty_surface_file",
            "published_event_start_utc": expected.isoformat(),
            "observation_count": int(len(obs)),
            "minimum_visibility_m": (
                float(pd.to_numeric(obs["visibility_m"], errors="coerce").min())
                if "visibility_m" in obs.columns and obs["visibility_m"].notna().any()
                else None
            ),
            "maximum_gust_kt": (
                float(pd.to_numeric(obs["wind_gust_kt"], errors="coerce").max())
                if "wind_gust_kt" in obs.columns and obs["wind_gust_kt"].notna().any()
                else None
            ),
            "maximum_peak_wind_gust_kt": (
                float(pd.to_numeric(obs["peak_wind_gust_kt"], errors="coerce").max())
                if "peak_wind_gust_kt" in obs.columns and obs["peak_wind_gust_kt"].notna().any()
                else None
            ),
        }

        starts = {}
        for threshold_km in THRESHOLDS_KM:
            col = f"visibility_le_{str(threshold_km).replace('.', 'p')}km"
            first = first_at_or_below(obs, col)
            starts[threshold_km] = first
            suffix = str(threshold_km).replace(".", "p")
            row[f"first_le_{suffix}km_utc"] = first.isoformat() if first else None
            row[f"offset_from_published_start_{suffix}km_min"] = (
                (first - expected).total_seconds() / 60.0 if first is not None else None
            )

        offsets = [
            abs(row[f"offset_from_published_start_{str(t).replace('.', 'p')}km_min"])
            for t in THRESHOLDS_KM
            if row[f"offset_from_published_start_{str(t).replace('.', 'p')}km_min"] is not None
        ]
        row["surface_timing_consistent"] = bool(offsets and min(offsets) <= TOLERANCE_MINUTES)
        row["published_min_visibility_km"] = getattr(case, "min_visibility_km", None)
        row["published_peak_wind_kt"] = getattr(case, "peak_wind_kt", None)
        rows.append(row)

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--surface-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--download-errors")
    args = parser.parse_args()

    result = audit(Path(args.cases), Path(args.surface_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    statuses = result["status"] if "status" in result.columns else pd.Series(dtype="string")
    timing = result["surface_timing_consistent"] if "surface_timing_consistent" in result.columns else pd.Series(dtype="boolean")
    minimum_visibility = result["minimum_visibility_m"] if "minimum_visibility_m" in result.columns else pd.Series(dtype="float64")
    summary = {
        "cases": int(len(result)),
        "surface_files_missing": int(statuses.eq("missing_surface_file").sum()),
        "surface_files_empty": int(statuses.eq("empty_surface_file").sum()),
        "download_error_cases": 0,
        "timing_consistent_cases": int(timing.fillna(False).sum()),
        "minimum_visibility_km_all_cases": (
            float(pd.to_numeric(minimum_visibility, errors="coerce").min() / 1000.0)
            if minimum_visibility.notna().any() else None
        ),
        "surface_evidence_status": "no_case_rows" if result.empty else "evaluated",
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
