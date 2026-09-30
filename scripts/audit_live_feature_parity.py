"""Audit parity between historical feature construction and the live feature adapter.

The audit converts replay object history into both feature paths and compares
availability plus numeric values for the final scan of each track. This catches
live/historical naming, units, and causal-evolution drift before a model bundle
is trusted in replay or shadow scoring.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_model_features import predictor_columns, build_features
from scripts.live_model_features import build_live_feature_frame


def load_replay_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"Replay history is empty: {path}")
    if "timestamp" not in frame.columns or "track_id" not in frame.columns:
        raise ValueError("Replay history requires timestamp and track_id columns.")
    out = frame.copy()
    out["scan_time_utc"] = out["timestamp"]
    out["object_id"] = out["track_id"].astype(str)
    out["population"] = "replay"
    out["radar_site"] = out.get("radar_site", "REPLAY")
    return out


def numeric_close(a, b, atol=1e-8, rtol=1e-6) -> bool:
    try:
        if pd.isna(a) and pd.isna(b):
            return True
    except (TypeError, ValueError):
        return False
    try:
        return bool(np.isclose(float(a), float(b), atol=atol, rtol=rtol, equal_nan=True))
    except (TypeError, ValueError):
        return str(a) == str(b)


def audit_track(raw: pd.DataFrame, predictor_names: list[str], track_id: str) -> dict:
    normalized = raw.copy()
    if "object_id" not in normalized.columns and "track_id" in normalized.columns:
        normalized["object_id"] = normalized["track_id"].astype(str)
    if "scan_time_utc" not in normalized.columns and "timestamp" in normalized.columns:
        normalized["scan_time_utc"] = normalized["timestamp"]
    track = normalized[normalized["object_id"].astype(str) == str(track_id)].copy()
    track = track.sort_values("scan_time_utc")
    if track.empty:
        raise ValueError(f"Track not found: {track_id}")

    historical = build_features(track)
    live_records = track.to_dict(orient="records")
    live = build_live_feature_frame(live_records, str(track_id))
    if historical.empty or live.empty:
        raise ValueError(f"Track {track_id}: feature path returned no rows")

    hrow = historical.iloc[-1]
    lrow = live.iloc[-1]
    comparable = []
    mismatches = []
    unavailable_both = []
    historical_available = 0
    live_available = 0
    for name in predictor_names:
        if name not in historical.columns and name not in live.columns:
            continue
        hv = hrow.get(name, np.nan)
        lv = lrow.get(name, np.nan)
        h_available = pd.notna(hv)
        l_available = pd.notna(lv)
        comparable.append(name)
        historical_available += int(h_available)
        live_available += int(l_available)
        if not h_available and not l_available:
            unavailable_both.append(name)
            continue
        if h_available != l_available:
            mismatches.append({
                "feature": name,
                "kind": "availability_mismatch",
                "historical": None if not h_available else float(hv),
                "live": None if not l_available else float(lv),
            })
        elif h_available and not numeric_close(hv, lv):
            mismatches.append({
                "feature": name,
                "kind": "numeric_mismatch",
                "historical": float(hv),
                "live": float(lv),
            })

    return {
        "track_id": str(track_id),
        "scan_count": int(len(track)),
        "comparable_predictors": len(comparable),
        "historical_available_predictors": historical_available,
        "live_available_predictors": live_available,
        "both_unavailable_predictors": unavailable_both,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "pass" if not mismatches else "fail",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--track-id", default=None)
    parser.add_argument("--max-tracks", type=int, default=20)
    args = parser.parse_args()

    raw = load_replay_history(args.history)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    predictor_names = list(schema.get("operational_predictor_columns") or predictor_columns(raw))

    track_ids = [args.track_id] if args.track_id is not None else (
        raw[["track_id"]].drop_duplicates().astype(str)["track_id"].tolist()[:args.max_tracks]
    )
    rows = [audit_track(raw, predictor_names, track_id) for track_id in track_ids]

    report = {
        "status": "pass" if all(r["status"] == "pass" for r in rows) else "fail",
        "future_information_policy": "one_scan_at_a_time",
        "tracks_audited": len(rows),
        "tracks_with_mismatches": sum(r["mismatch_count"] > 0 for r in rows),
        "tracks": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
