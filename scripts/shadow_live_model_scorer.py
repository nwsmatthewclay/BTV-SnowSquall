"""Score the live object stream with candidate models into a separate shadow feed."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.live_model_features import build_live_feature_frame, feature_coverage
from scripts.add_national_pretraining_features import augment as augment_national_pretraining
from scripts.model_runtime import ModelRuntime
from scripts.probability_postprocess import monotone_cumulative_probabilities

HORIZONS = (15, 30, 45, 60)
SITES = ("KCXX", "KTYX")
MIN_FEATURE_COVERAGE = 0.80


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def score_site(site: str, live_root: Path, model_root: Path) -> tuple[dict, list[dict]]:
    objects_path = live_root / f"{site}_objects.geojson"
    history_path = live_root / f"{site}_history.json"
    geo = read_json(objects_path, {})
    history = read_json(history_path, [])
    now = datetime.now(timezone.utc)
    rows = []
    current_features = geo.get("features") or []

    runtimes = {}
    model_info = {}
    for horizon in HORIZONS:
        ensemble_dir = model_root / f"candidate_ensemble_expansion_{horizon}m"
        baseline_dir = model_root / f"baseline_expansion_{horizon}m"
        directory = ensemble_dir if (ensemble_dir / "metrics.json").exists() else baseline_dir
        runtime = ModelRuntime.load(directory)
        runtimes[horizon] = runtime
        model_info[horizon] = {
            "model_present": runtime.model is not None,
            "model_version": runtime.metadata.get("model_version"),
            "operational_release_status": runtime.metadata.get("operational_release_status"),
            "predictor_count": len(runtime.feature_columns),
            "model_family": runtime.metadata.get("estimator_family") or runtime.metadata.get("model_version"),
            "selected_artifact": directory.name,
            "bundle_family": "candidate_soft_vote_ensemble" if directory.name.startswith("candidate_ensemble_expansion_") else "baseline_hist_gradient_boosting",
        }

    for feature in current_features:
        props = feature.get("properties") or {}
        track_id = props.get("track_id")
        if track_id is None:
            continue
        track_history = [r for r in history if str(r.get("track_id")) == str(track_id)]
        if not track_history:
            track_history = [dict(props)]
        frame = build_live_feature_frame(track_history, track_id)
        frame, national_pretraining = augment_national_pretraining(frame, model_root)
        frame, national_prior = augment_national_pretraining(frame, model_root)
        record = {
            "radar_site": site,
            "track_id": str(track_id),
            "timestamp": props.get("timestamp") or geo.get("metadata", {}).get("scan_time_utc"),
            "max_reflectivity_dbz": props.get("max_reflectivity_dbz"),
            "data_quality": props.get("data_quality"),
            "feature_coverage": {},
            "research_probabilities": {},
            "score_errors": {},
            "national_pretraining": national_pretraining,
            "score_policy": {"minimum_feature_coverage": MIN_FEATURE_COVERAGE},
        "national_pretraining": national_prior,
        }
        for horizon in HORIZONS:
            runtime = runtimes[horizon]
            coverage = feature_coverage(frame.tail(1), runtime.feature_columns)
            record["feature_coverage"][str(horizon)] = coverage
            if coverage["fraction"] < MIN_FEATURE_COVERAGE:
                record["score_errors"][str(horizon)] = "low_feature_coverage:{:.3f}".format(coverage["fraction"])
                continue
            try:
                score = runtime.score_candidate(frame.tail(1))
                if score:
                    record["research_probabilities"][str(horizon)] = float(score[0])
            except Exception as exc:
                record["score_errors"][str(horizon)] = f"{type(exc).__name__}: {exc}"
        if record["research_probabilities"]:
            projected = monotone_cumulative_probabilities(record["research_probabilities"])
            record["research_probabilities_raw"] = dict(record["research_probabilities"])
            record["research_probabilities"] = projected.get("cumulative", {})
            record["research_interval_probabilities"] = projected.get("interval", {})
            record["probability_projection"] = "isotonic_non_decreasing_horizon"
        rows.append(record)

    scored = sum(bool(r["research_probabilities"]) for r in rows)
    payload = {
        "site": site,
        "updated_utc": now.isoformat(),
        "mode": "live_shadow_research",
        "operational_release_status": "candidate_only_not_operational",
        "model_info": model_info,
        "current_object_count": len(current_features),
        "scored_object_count": scored,
        "records": rows,
    }
    return payload, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    all_site_payloads = {}
    for site in SITES:
        payload, rows = score_site(site, args.live_root, args.model_root)
        all_site_payloads[site] = payload
        (args.output_root / f"{site}_shadow.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

        history_path = args.output_root / f"{site}_shadow_history.json"
        history = read_json(history_path, [])
        history.extend(rows)
        dedup = {}
        for row in history:
            key = (str(row.get("timestamp", "")), str(row.get("track_id", "")))
            dedup[key] = row
        history = list(dedup.values())
        cleaned = []
        for row in history:
            try:
                ts = datetime.fromisoformat(str(row.get("timestamp")).replace("Z", "+00:00")).astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            if ts >= cutoff:
                cleaned.append(row)
        cleaned.sort(key=lambda r: (r.get("timestamp", ""), r.get("track_id", "")))
        cleaned = cleaned[-20000:]
        history_path.write_text(json.dumps(cleaned, separators=(",", ":")) + "\n", encoding="utf-8")

    (args.output_root / "shadow_health.json").write_text(
        json.dumps({"status": "healthy", "mode": "live_shadow_research", "updated_utc": datetime.now(timezone.utc).isoformat(), "sites": {s: {"current_objects": p["current_object_count"], "scored_objects": p["scored_object_count"]} for s, p in all_site_payloads.items()}}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
