"""Build an ML-ready historical object dataset from reconstructed radar scans."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from processing.environment import acquire_for_radar_time, extract_features, environment_cache_key


def parse_time(value):
    if not value or pd.isna(value):
        return None
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


def load_cases(path: Path):
    df = pd.read_csv(path)
    df["event_start_dt"] = df["event_start_utc"].map(parse_time)
    return df.set_index("case_id")


def choose_case(scan_time, cases):
    candidates = []
    for case_id, case in cases.iterrows():
        start = case["event_start_dt"]
        if start is None:
            continue
        delta_min = abs((scan_time - start).total_seconds()) / 60.0
        if delta_min <= 180:
            candidates.append((delta_min, case_id, case))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])


def enrich(
    input_csv: Path,
    output_csv: Path,
    cases_csv: Path,
    rap_dir: Path,
    ruc_dir: Path,
    allow_temporal_case_inference: bool = False,
    narr_dir: Path | None = None,
):
    objects = pd.read_csv(input_csv)
    objects["scan_dt"] = pd.to_datetime(objects["scan_time_utc"], utc=True, errors="coerce")
    objects = objects.dropna(subset=["scan_dt"]).copy()
    cases = load_cases(cases_csv)

    cache = {}
    rows = []

    for _, obj in objects.iterrows():
        scan_time = obj["scan_dt"].to_pydatetime().astimezone(timezone.utc)
        explicit_case_id = obj.get("case_id")
        if pd.notna(explicit_case_id) and explicit_case_id in cases.index:
            case_match = (0.0, explicit_case_id, cases.loc[explicit_case_id])
            assignment_method = "explicit_case_id"
        elif allow_temporal_case_inference:
            case_match = choose_case(scan_time, cases)
            assignment_method = "temporal_inference" if case_match else "unmatched"
        else:
            case_match = None
            assignment_method = "unmatched_without_explicit_case_id"

        row = obj.to_dict()
        row.update({
            "case_id": None,
            "case_source_study": None,
            "case_event_start_utc": None,
            "case_observing_station": None,
            "case_peak_wind_kt": None,
            "case_min_visibility_km": None,
            "case_hybrid": None,
            "case_lat": None,
            "case_lon": None,
            "case_coordinate_source": None,
            "case_coordinate_precision": None,
            "case_time_relation": "unmatched",
            "case_assignment_method": assignment_method,
        })

        if case_match:
            _, case_id, case = case_match
            row.update({
                "case_id": case_id,
                "case_source_study": case["source_study"],
                "case_event_start_utc": case["event_start_utc"],
                "case_observing_station": case["observing_station"],
                "case_peak_wind_kt": case["peak_wind_kt"],
                "case_min_visibility_km": case["min_visibility_km"],
                "case_hybrid": bool(case["hybrid_case"]),
                "case_lat": case.get("lat"),
                "case_lon": case.get("lon"),
                "case_coordinate_source": case.get("coordinate_source"),
                "case_coordinate_precision": case.get("coordinate_precision"),
                "case_time_relation": (
                    "at_or_near_verified_onset"
                    if abs((scan_time - case["event_start_dt"]).total_seconds()) <= 30 * 60
                    else "within_case_context"
                ),
            })

        lat = obj.get("centroid_lat")
        lon = obj.get("centroid_lon")
        if pd.isna(lat) or pd.isna(lon):
            row["environment_status"] = "unavailable"
            rows.append(row)
            continue

        hour_key = environment_cache_key(scan_time)
        if hour_key not in cache:
            try:
                cache[hour_key] = acquire_for_radar_time(
                    scan_time,
                    rap_dir=rap_dir,
                    ruc_dir=ruc_dir,
                    narr_dir=narr_dir,
                    max_age_minutes=180,
                )
            except Exception as exc:
                cache[hour_key] = None
                cache[f"{hour_key}:error"] = f"{type(exc).__name__}: {exc}"

        acquired = cache[hour_key]
        if acquired is None:
            row["environment_status"] = "unavailable"
            row["environment_error"] = cache.get(
                f"{hour_key}:error",
                "no acceptable historical analysis found within age limit",
            )
            rows.append(row)
            continue

        provider, match, environment_path = acquired
        try:
            environment = extract_features(
                provider,
                environment_path,
                float(lat),
                float(lon),
                scan_time,
                expected_valid_time=match.valid_time,
            )
        except Exception as exc:
            row["environment_status"] = "unavailable"
            row["environment_error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue

        row["environment_status"] = environment.get("status", "partial")
        row["environment_source"] = provider
        row["environment_valid_time_utc"] = environment.get("source_valid_time_utc")
        row["environment_match_method"] = "latest_valid_analysis_at_or_before_scan"
        row["environment_time_delta_policy"] = "scan_time_minus_source_valid_time"
        row["environment_age_minutes"] = environment.get("age_minutes")
        for key, value in (environment.get("fields") or {}).items():
            row[key] = value

        row["label_status"] = "historical_case_context_only"
        row["snow_squall_outcome"] = None
        rows.append(row)

    result = pd.DataFrame(rows)
    result = result.sort_values(["scan_dt", "radar_site", "object_id"])
    result.drop(columns=["scan_dt"], inplace=True, errors="ignore")
    if "environment_source" not in result.columns:
        result["environment_source"] = pd.NA
    if "environment_error" not in result.columns:
        result["environment_error"] = pd.NA
    if "environment_status" not in result.columns:
        result["environment_status"] = "unavailable"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False)

    print(f"Wrote {len(result)} object-timestep records to {output_csv}")
    print("Environment sources:")
    print(result["environment_source"].value_counts(dropna=False).to_string())
    print("Environment status:")
    print(result["environment_status"].value_counts(dropna=False).to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", default="data/manifests/banacos_2014_cases.csv")
    parser.add_argument("--rap-dir", default="data/raw/RAP")
    parser.add_argument("--ruc-dir", default="data/raw/RUC")
    parser.add_argument("--narr-dir", default="data/raw/NARR")
    parser.add_argument("--allow-temporal-case-inference", action="store_true", help="Opt in to time-based case assignment when case_id is absent.")
    args = parser.parse_args()
    enrich(
        Path(args.input_csv),
        Path(args.output),
        Path(args.cases),
        Path(args.rap_dir),
        Path(args.ruc_dir),
        allow_temporal_case_inference=args.allow_temporal_case_inference,
        narr_dir=Path(args.narr_dir),
    )


if __name__ == "__main__":
    main()
