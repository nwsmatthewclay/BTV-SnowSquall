"""Score the live object stream with candidate models into a separate shadow feed."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.live_model_features import build_live_feature_frame, feature_coverage
from snow_squall.environment_contract import assess_environment
from scripts.add_national_pretraining_features import augment as augment_national_pretraining
from scripts.model_runtime import ModelRuntime
from scripts.probability_postprocess import monotone_cumulative_probabilities

HORIZONS = (15, 30, 45, 60)
SITES = ("KCXX", "KTYX")
MIN_FEATURE_COVERAGE = 0.80
MAX_ENVIRONMENT_AGE_MINUTES = 180.0
ENVIRONMENT_PREDICTORS = {
    "cape_jkg", "cin_jkg", "snsq", "mean_rh_0_2km_pct", "thetae_delta_0_2km_k",
    "mean_wind_0_2km_ms", "wetbulb_2m_c", "snsq_moisture_factor",
    "snsq_instability_factor", "snsq_wind_factor", "shear_0_6km_kt",
    "pwat_mm", "mlcape_jkg", "mlcin_jkg", "mucape_jkg", "mucin_jkg",
    "srh01_m2s2", "srh03_m2s2", "shear_u_0_6km_ms", "shear_v_0_6km_ms",
    "shear_0_6km_ms", "u10_ms", "v10_ms", "temperature_2m_k", "dewpoint_2m_k",
    "rh_2m_pct", "temperature_dewpoint_spread_k",
}
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
            "bundle_family": (
                "candidate_soft_vote_ensemble"
                if directory is not None and directory.name.startswith("candidate_ensemble_")
                else ("baseline_hist_gradient_boosting" if directory is not None else None)
            ),
        }

    for feature in current_features:
        props = feature.get("properties") or {}
        track_id = props.get("track_id")
        if track_id is None:
            continue
        current_timestamp = props.get("timestamp") or geo.get("metadata", {}).get("scan_time_utc")
        try:
            current_dt = datetime.fromisoformat(str(current_timestamp).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            current_dt = None
        track_history = [r for r in history if str(r.get("track_id")) == str(track_id)]
        if current_dt is not None:
            filtered_history = []
            for row in track_history:
                try:
                    row_dt = datetime.fromisoformat(
                        str(row.get("timestamp")).replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except (TypeError, ValueError):
                    continue
                if row_dt <= current_dt:
                    filtered_history.append(row)
            track_history = filtered_history
        if not track_history:
            track_history = [dict(props)]
        frame = build_live_feature_frame(track_history, track_id)
        frame, national_pretraining = augment_national_pretraining(frame, model_root)
        environment_readiness = assess_environment(
            frame.tail(1).iloc[0].to_dict() if not frame.empty else {},
            radar_time=current_timestamp,
            max_age_minutes=MAX_ENVIRONMENT_AGE_MINUTES,
        )
        record = {
            "radar_site": site,
            "track_id": str(track_id),
            "timestamp": props.get("timestamp") or geo.get("metadata", {}).get("scan_time_utc"),
            "max_reflectivity_dbz": props.get("max_reflectivity_dbz"),
            "data_quality": props.get("data_quality"),
            "environment_readiness": environment_readiness,
            "environment_confidence": (
                "fresh"
                if environment_readiness.get("ready") and (environment_readiness.get("age_minutes") or 0) <= 90
                else "degraded_freshness"
                if environment_readiness.get("ready")
                else "not_ready"
            ),
            "feature_coverage": {},
            "research_probabilities": {},
            "score_errors": {},
            "national_pretraining": national_pretraining,
            "score_policy": {
                "minimum_feature_coverage": MIN_FEATURE_COVERAGE,
                "max_environment_age_minutes": MAX_ENVIRONMENT_AGE_MINUTES,
                "fresh_environment_target_minutes": 90,
                "requires_complete_environment": environment_required,
                "environment_requirement": (
                    "model_predictors_require_environment"
                    if environment_required
                    else "bootstrap_radar_object_model_does_not_use_environment_predictors"
                ),
                "stale_but_usable_policy": "complete_RAP_environment_up_to_180m_is_scored_with_degraded_freshness",
            },
        }
        for horizon in HORIZONS:
            runtime = runtimes[horizon]
            coverage = feature_coverage(frame.tail(1), runtime.feature_columns)
            record["feature_coverage"][str(horizon)] = coverage
            environment_required = bool(set(runtime.feature_columns) & ENVIRONMENT_PREDICTORS)
            record.setdefault("environment_requirement", {})[str(horizon)] = (
                "required" if environment_required else "not_used_by_model"
            )
            available_instantaneous = [
                c for c in MIN_INSTANTANEOUS_FEATURES
                if c in frame.columns and frame.tail(1)[c].notna().any()
            ]
            if (
                coverage["fraction"] < MIN_FEATURE_COVERAGE
                or len(available_instantaneous) < 6
            ):
                reason = (
                    "low_feature_coverage:{:.3f}".format(coverage["fraction"])
                    if coverage["fraction"] < MIN_FEATURE_COVERAGE
                    else "insufficient_instantaneous_object_features"
                )
                if environment_required and not environment_readiness["ready"]:
                    reason += ";environment_not_model_ready:" + ",".join(environment_readiness["reasons"])
                record["score_errors"][str(horizon)] = reason
                continue
            if environment_required and not environment_readiness["ready"]:
                record["score_errors"][str(horizon)] = (
                    "environment_not_model_ready:" + ",".join(environment_readiness["reasons"])
                )
                continue
            record.setdefault("coverage_class", {})[str(horizon)] = (
                "evolution_enhanced"
                if coverage["fraction"] >= 0.70
                else "initial_object_state"
            )
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
