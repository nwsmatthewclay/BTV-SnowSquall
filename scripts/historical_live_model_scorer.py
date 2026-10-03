"""Replay the live shadow scorer over historical object scans.

This intentionally uses the same live feature adapter and candidate model runtime as
the live shadow scorer. At each historical scan, only that track's current and prior
scans are supplied to the feature builder, so future scans cannot leak into predictors.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.live_model_features import build_live_feature_frame, feature_coverage
from scripts.add_national_pretraining_features import augment as augment_national_pretraining
from scripts.model_runtime import ModelRuntime
from scripts.probability_postprocess import monotone_cumulative_probabilities

HORIZONS = (15, 30, 45, 60)
MIN_FEATURE_COVERAGE = 0.40
MIN_INSTANTANEOUS_FEATURES = {
    "max_reflectivity_dbz",
    "mean_reflectivity_dbz",
    "area_km2",
    "length_km",
    "width_km",
    "core_pixel_count",
    "bbox_aspect_ratio",
    "reflectivity_gradient_p90_dbkm",
    "gradient_fraction_above_5dbkm",
    "background_reflectivity_dbz",
    "reflectivity_contrast_db",
}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def flatten_environment(props: dict) -> dict:
    """Expose nested historical environment fields to the live adapter."""
    row = dict(props)
    env = props.get("environment") or {}
    if isinstance(env, dict):
        for key, value in env.items():
            if isinstance(value, dict) and "value" in value:
                row[key] = value.get("value")
            elif key not in row:
                row[key] = value
    return row


def load_runtimes(model_root: Path):
    runtimes = {}
    model_info = {}
    for horizon in HORIZONS:
        candidates = [
            model_root / f"candidate_ensemble_refresh_{horizon}m",
            model_root / f"candidate_ensemble_expansion_{horizon}m",
            model_root / f"baseline_refresh_{horizon}m",
            model_root / f"baseline_expansion_{horizon}m",
        ]
        directory = next(
            (candidate for candidate in candidates if (candidate / "metrics.json").exists()),
            None,
        )
        runtime = ModelRuntime.load(directory) if directory is not None else ModelRuntime()
        runtimes[horizon] = runtime
        model_info[horizon] = {
            "model_present": runtime.model is not None,
            "model_version": runtime.metadata.get("model_version"),
            "operational_release_status": runtime.metadata.get("operational_release_status"),
            "predictor_count": len(runtime.feature_columns),
            "model_family": runtime.metadata.get("estimator_family") or runtime.metadata.get("model_version"),
            "selected_artifact": directory.name if directory is not None else None,
        }
    return runtimes, model_info


def score_case(path: Path, model_root: Path):
    payload = read_json(path, {})
    features = payload.get("features") or []
    by_track = {}
    for feature in features:
        props = feature.get("properties") or {}
        track_id = props.get("track_key") or props.get("track_id")
        if track_id is None:
            continue
        by_track.setdefault(str(track_id), []).append(feature)

    runtimes, model_info = load_runtimes(model_root)
    scored_count = 0
    error_count = 0

    for track_id, track_features in by_track.items():
        track_features.sort(key=lambda f: str((f.get("properties") or {}).get("timestamp", "")))
        history = []
        for feature in track_features:
            props = feature.setdefault("properties", {})
            current = flatten_environment(props)
            current["track_id"] = props.get("track_id", track_id)

            # Only scans through the current scan are available to the scorer.
            history.append(current)
            frame = build_live_feature_frame(history, current["track_id"])
            frame, national_pretraining = augment_national_pretraining(frame, model_root)

            score_record = {
                "15": None, "30": None, "45": None, "60": None,
            }
            raw_record = {}
            coverage_record = {}
            errors = {}
            available_instantaneous = None

            for horizon in HORIZONS:
                runtime = runtimes[horizon]
                coverage = feature_coverage(frame.tail(1), runtime.feature_columns)
                coverage_record[str(horizon)] = coverage

                if available_instantaneous is None:
                    available_instantaneous = [
                        c for c in MIN_INSTANTANEOUS_FEATURES
                        if c in frame.columns and frame.tail(1)[c].notna().any()
                    ]

                if coverage["fraction"] < MIN_FEATURE_COVERAGE:
                    errors[str(horizon)] = f"low_feature_coverage:{coverage['fraction']:.3f}"
                    continue
                if len(available_instantaneous) < 6:
                    errors[str(horizon)] = "insufficient_instantaneous_object_features"
                    continue
                try:
                    result = runtime.score_candidate(frame.tail(1))
                    if result:
                        raw_record[str(horizon)] = float(result[0])
                except Exception as exc:
                    errors[str(horizon)] = f"{type(exc).__name__}: {exc}"

            if raw_record:
                projected = monotone_cumulative_probabilities(raw_record)
                score_record.update(projected.get("cumulative", {}))
                scored_count += 1
            if errors:
                error_count += 1

            props["research_probabilities"] = score_record
            props["research_probabilities_raw"] = raw_record
            props["research_interval_probabilities"] = (
                monotone_cumulative_probabilities(raw_record).get("interval", {})
                if raw_record else {}
            )
            props["research_score_metadata"] = {
                "mode": "historical_live_shadow_replay",
                "release_status": "candidate_only_not_operational",
                "feature_coverage": coverage_record,
                "score_errors": errors,
                "national_pretraining": national_pretraining,
                "model_artifacts": {
                    str(h): model_info[h]["selected_artifact"] for h in HORIZONS
                },
                "leakage_policy": "current_and_prior_track_scans_only",
            }

    payload.setdefault("metadata", {})
    payload["metadata"]["historical_live_scorer"] = {
        "status": "scored",
        "mode": "historical_live_shadow_replay",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_only_not_operational": True,
        "scored_object_scans": scored_count,
        "object_scans_with_errors": error_count,
        "model_info": model_info,
        "feature_policy": "same_live_scorer_adapter_and_model_runtime",
    }
    return payload, scored_count, error_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    total_scored = 0
    total_errors = 0
    case_count = 0

    for path in sorted(args.input_root.glob("*.geojson")):
        payload, scored, errors = score_case(path, args.model_root)
        out = args.output_root / path.name
        out.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
        total_scored += scored
        total_errors += errors
        case_count += 1
        print(path.name, "scored:", scored, "with_errors:", errors)

    summary = {
        "status": "complete",
        "mode": "historical_live_shadow_replay",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "cases": case_count,
        "scored_object_scans": total_scored,
        "object_scans_with_errors": total_errors,
        "candidate_only_not_operational": True,
    }
    (args.output_root / "historical_live_scorer_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
