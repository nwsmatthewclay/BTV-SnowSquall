"""Score a multi-scan historical candidate-model replay against documented onset times.

This is a research diagnostic. It does not change truth labels or perform
operational verification. Metrics are reported at both radar-replay and
case-aggregated levels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (15, 30, 45, 60)
THRESHOLDS = (0.10, 0.25, 0.50, 0.75)


def load_cases(path: Path) -> pd.DataFrame:
    cases = pd.read_csv(path)
    required = {"case_id", "event_start_utc"}
    missing = required - set(cases.columns)
    if missing:
        raise ValueError(f"Cases file missing columns: {sorted(missing)}")
    cases["event_start_utc"] = pd.to_datetime(cases["event_start_utc"], utc=True, errors="coerce")
    return cases.set_index(cases["case_id"].astype(str))


def replay_features(replay_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(replay_dir.glob("*.geojson")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            row = {
                "timestamp": props.get("timestamp") or payload.get("metadata", {}).get("scan_time_utc"),
                "track_id": props.get("track_id"),
                "radar_site": props.get("radar_site") or payload.get("metadata", {}).get("radar_id"),
                "source_file": path.name,
            }
            for horizon in HORIZONS:
                row[f"probability_{horizon}min"] = props.get(f"probability_{horizon}min")
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    for horizon in HORIZONS:
        frame[f"probability_{horizon}min"] = pd.to_numeric(
            frame[f"probability_{horizon}min"], errors="coerce"
        )
    return frame.dropna(subset=["timestamp"])


def radar_metrics(frame: pd.DataFrame, onset: pd.Timestamp) -> list[dict]:
    if frame.empty:
        return []

    frame = frame.sort_values("timestamp")
    scan_times = sorted(frame["timestamp"].dropna().unique())
    output = []

    for horizon in HORIZONS:
        pcol = f"probability_{horizon}min"
        pre_start = onset - pd.Timedelta(minutes=horizon)
        lead_window = frame[(frame["timestamp"] >= pre_start) & (frame["timestamp"] < onset)].copy()
        full_pre = frame[frame["timestamp"] < onset].copy()
        post = frame[
            (frame["timestamp"] >= onset)
            & (frame["timestamp"] < onset + pd.Timedelta(minutes=30))
        ].copy()

        scan_max = (
            lead_window.groupby("timestamp")[pcol].max()
            if not lead_window.empty else pd.Series(dtype=float)
        )
        full_scan_max = (
            full_pre.groupby("timestamp")[pcol].max()
            if not full_pre.empty else pd.Series(dtype=float)
        )

        peak_pre = float(lead_window[pcol].max()) if lead_window[pcol].notna().any() else np.nan
        peak_post = float(post[pcol].max()) if post[pcol].notna().any() else np.nan

        for threshold in THRESHOLDS:
            key = str(threshold).replace(".", "p")
            crossings = scan_max[scan_max >= threshold]
            first_time = crossings.index[0] if not crossings.empty else pd.NaT
            lead_min = (
                float((onset - pd.Timestamp(first_time)).total_seconds() / 60.0)
                if pd.notna(first_time) else np.nan
            )
            alert_fraction = (
                float((full_scan_max >= threshold).mean())
                if not full_scan_max.empty else np.nan
            )
            output.append({
                "horizon_min": horizon,
                "threshold": threshold,
                "peak_pre_onset_probability": peak_pre,
                "peak_post_onset_30min_probability": peak_post,
                "first_crossing_utc": first_time.isoformat() if pd.notna(first_time) else None,
                "first_crossing_lead_min": lead_min,
                "hit_within_horizon": bool(pd.notna(first_time)),
                "pre_onset_alert_scan_fraction": alert_fraction,
                "pre_onset_scan_count": int(len(full_scan_max)),
                "lead_window_scan_count": int(len(scan_max)),
                "object_timestep_count": int(len(lead_window)),
                "radar_site": str(frame["radar_site"].dropna().iloc[0]) if frame["radar_site"].notna().any() else None,
            })
    return output


def summarize_case(replay_metrics: pd.DataFrame) -> pd.DataFrame:
    if replay_metrics.empty:
        return replay_metrics
    grouped = (
        replay_metrics.groupby(["case_id", "horizon_min", "threshold"], dropna=False)
        .agg(
            peak_pre_onset_probability=("peak_pre_onset_probability", "max"),
            peak_post_onset_30min_probability=("peak_post_onset_30min_probability", "max"),
            first_crossing_lead_min=("first_crossing_lead_min", "max"),
            hit_within_horizon=("hit_within_horizon", "max"),
            radar_count=("radar_site", "nunique"),
        )
        .reset_index()
    )
    return grouped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-root", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    rows = []

    manifests = sorted(args.replay_root.rglob("replay_manifest.json"))
    if not manifests:
        raise SystemExit(f"No replay_manifest.json files found under {args.replay_root}")

    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        case_id = str(manifest.get("case_id") or "")
        if case_id not in cases.index:
            continue
        onset = cases.loc[case_id, "event_start_utc"]
        if pd.isna(onset):
            continue
        frame = replay_features(manifest_path.parent)
        metrics = radar_metrics(frame, onset)
        for row in metrics:
            row["case_id"] = case_id
            row["replay_directory"] = str(manifest_path.parent)
            row["model_directory"] = manifest.get("model_directory")
            row["probability_status"] = manifest.get("probability_status")
            rows.append(row)

    radar_df = pd.DataFrame(rows)
    if radar_df.empty:
        raise SystemExit("No scored replay records were found.")

    case_df = summarize_case(radar_df)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    radar_df.to_csv(args.output_dir / "radar_replay_metrics.csv", index=False)
    case_df.to_csv(args.output_dir / "case_replay_metrics.csv", index=False)

    summary = {
        "replay_directories": int(len(manifests)),
        "cases": int(case_df["case_id"].nunique()),
        "radar_replays": int(radar_df[["case_id", "radar_site"]].drop_duplicates().shape[0]),
        "horizons": {},
        "thresholds": list(THRESHOLDS),
        "research_only": True,
    }

    for horizon in HORIZONS:
        for threshold in THRESHOLDS:
            subset = case_df[
                (case_df["horizon_min"] == horizon)
                & (case_df["threshold"] == threshold)
            ]
            if subset.empty:
                continue
            hits = subset["hit_within_horizon"].fillna(False).astype(bool)
            hit_leads = pd.to_numeric(
                subset.loc[hits, "first_crossing_lead_min"], errors="coerce"
            ).dropna()
            key = f"{horizon}m_{str(threshold).replace('.', 'p')}"
            summary["horizons"][key] = {
                "case_count": int(len(subset)),
                "case_hit_fraction": float(hits.mean()),
                "median_first_crossing_lead_min": (
                    float(hit_leads.median()) if not hit_leads.empty else None
                ),
                "mean_peak_pre_onset_probability": float(
                    pd.to_numeric(subset["peak_pre_onset_probability"], errors="coerce").mean()
                ),
                "median_peak_pre_onset_probability": float(
                    pd.to_numeric(subset["peak_pre_onset_probability"], errors="coerce").median()
                ),
            }

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
