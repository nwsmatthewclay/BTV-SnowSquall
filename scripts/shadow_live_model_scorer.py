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
LIMITED_DATA_MIN_FEATURE_COVERAGE = 0.40
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


def load_candidate_summary(model_root: Path) -> dict:
    candidates = [
        model_root / "snow_squall_candidate_refresh_summary.json",
        model_root / "data" / "derived" / "snow_squall_candidate_refresh_summary.json",
    ]
    candidates.extend(model_root.rglob("snow_squall_candidate_refresh_summary.json"))
    for path in candidates:
        if path.exists():
            payload = read_json(path, {})
            if isinstance(payload, dict):
                return payload
    return {}


def score_site(site: str, live_root: Path, model_root: Path) -> tuple[dict, list[dict]]:
    objects_path = live_root / f"{site}_objects.geojson"
    history_path = live_root / f"{site}_history.json"
    geo = read_json(objects_path, {})
    history = read_json(history_path, [])
    now = datetime.now(timezone.utc)
    rows = []
    current_features = geo.get("features") or []
    candidate_summary = load_candidate_summary(model_root)
    candidate_mode = str(candidate_summary.get("candidate_mode") or "").strip()
    training_contract_status = str(candidate_summary.get("training_contract_status") or "").strip()

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
            "training_contract_status": runtime.metadata.get("training_contract_status") or training_contract_status or None,
            "candidate_mode": runtime.metadata.get("candidate_mode") or candidate_mode or None,
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

        # The live objects feed can be one filesystem write ahead of the
        # persisted history feed. Always insert the actual current object row
        # for this score, replacing any stale same-timestamp history row.
        by_timestamp = {}
        for row in track_history:
            stamp = str(row.get("timestamp") or "")
            if stamp:
                by_timestamp[stamp] = dict(row)
        if current_timestamp:
            by_timestamp[str(current_timestamp)] = dict(props)
        track_history = sorted(
            by_timestamp.values(),
            key=lambda row: str(row.get("timestamp") or ""),
        )
        if not track_history:
            track_history = [dict(props)]
        frame = build_live_feature_frame(track_history, track_id)
        frame, national_pretraining = augment_national_pretraining(frame, model_root)

        # Preserve explicit track chronology in the shadow payload so the
        # browser can plot one probability point for every observed scan.
        track_datetimes = []
        for row in track_history:
            try:
                track_datetimes.append(
                    datetime.fromisoformat(
                        str(row.get("timestamp")).replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                )
            except (TypeError, ValueError):
                continue
        first_track_dt = min(track_datetimes) if track_datetimes else current_dt
        track_age_min = (
            max(0.0, (current_dt - first_track_dt).total_seconds() / 60.0)
            if current_dt is not None and first_track_dt is not None
            else None
        )

        environment_readiness = assess_environment(
            frame.tail(1).iloc[0].to_dict() if not frame.empty else {},
            radar_time=current_timestamp,
            max_age_minutes=MAX_ENVIRONMENT_AGE_MINUTES,
        )
        any_runtime_environment_required = any(
            bool(set(runtime.feature_columns) & ENVIRONMENT_PREDICTORS)
            for runtime in runtimes.values()
            if runtime.model is not None
        )
        current_frame_row = frame.tail(1).iloc[0].to_dict() if not frame.empty else {}
        environment_keys = (
            "snsq", "cape_jkg", "sbcape_jkg", "mlcape_jkg", "mucape_jkg",
            "cin_jkg", "sbcin_jkg", "mlcin_jkg", "mucin_jkg", "dcape_jkg",
            "pwat_mm", "mean_rh_0_2km_pct", "rh_0_2km_pct",
            "thetae_delta_0_2km_k", "mean_wind_0_2km_ms",
            "wind_0_1km_kt", "wind_0_3km_kt",
            "srh01_m2s2", "srh03_m2s2",
            "shear_0_1km_kt", "shear_0_3km_kt", "shear_0_6km_kt",
            "shear_0_6km_ms", "wetbulb_2m_c", "wet_bulb_0_3km_c",
            "lcl_m", "lfc_m", "el_m",
            "lapse_rate_0_3km_c_km", "lapse_rate_0_7_5km_c_km",
            "freezing_level_m",
            "temperature_2m_k", "dewpoint_2m_k", "rh_2m_pct",
        )
        environment_snapshot = {
            key: current_frame_row.get(key)
            for key in environment_keys
            if key in current_frame_row
        }
        forecast_keys = {
            key[len("expected_30min_"):]: value
            for key, value in props.items()
            if str(key).startswith("expected_30min_")
        }

        record = {
            "radar_site": site,
            "track_id": str(track_id),
            "timestamp": props.get("timestamp") or geo.get("metadata", {}).get("scan_time_utc"),
            "track_first_scan_utc": first_track_dt.isoformat() if first_track_dt is not None else None,
            "track_age_min": track_age_min,
            "track_scan_count": len(track_history),
            "max_reflectivity_dbz": props.get("max_reflectivity_dbz"),
            "data_quality": props.get("data_quality"),
            "environment_snapshot": environment_snapshot,
            "environment_forecast_30min_snapshot": forecast_keys,
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
                "limited_data_minimum_feature_coverage": LIMITED_DATA_MIN_FEATURE_COVERAGE,
                "limited_data_shadow_policy": "candidate_only_models_may_score_at_0.40_coverage_for_research_shadow_only",
                "max_environment_age_minutes": MAX_ENVIRONMENT_AGE_MINUTES,
                "fresh_environment_target_minutes": 90,
                "requires_complete_environment": "per_horizon",
                "environment_requirement": (
                    "model_predictors_require_environment"
                    if any_runtime_environment_required
                    else "bootstrap_radar_object_model_does_not_use_environment_predictors"
                ),
                "stale_but_usable_policy": "complete_RAP_environment_up_to_180m_is_scored_with_degraded_freshness",
            },
        }
        for horizon in HORIZONS:
            runtime = runtimes[horizon]
            coverage = feature_coverage(frame.tail(1), runtime.feature_columns)
            record["feature_coverage"][str(horizon)] = coverage
            runtime_release_status = str(runtime.metadata.get("operational_release_status") or "").strip()
            runtime_candidate_mode = str(runtime.metadata.get("candidate_mode") or "").strip()
            runtime_training_contract = str(runtime.metadata.get("training_contract_status") or "").strip()
            limited_candidate = (
                training_contract_status == "limited_data_bootstrap"
                or candidate_mode.startswith("bootstrap")
                or runtime_training_contract == "limited_data_bootstrap"
                or runtime_candidate_mode.startswith("bootstrap")
                # Candidate-only bundles are intentionally allowed to shadow-score
                # at reduced feature coverage while the historical dataset warms.
                # This does NOT release probabilities to the operational feed.
                or runtime_release_status == "candidate_only"
            )
            coverage_floor = (
                LIMITED_DATA_MIN_FEATURE_COVERAGE if limited_candidate else MIN_FEATURE_COVERAGE
            )
            record.setdefault("coverage_policy", {})[str(horizon)] = {
                "minimum_fraction": coverage_floor,
                "mode": "limited_data_shadow" if limited_candidate else "full_candidate",
            }
            environment_required = bool(set(runtime.feature_columns) & ENVIRONMENT_PREDICTORS)
            record.setdefault("environment_requirement", {})[str(horizon)] = (
                "required" if environment_required else "not_used_by_model"
            )
            available_instantaneous = [
                c for c in MIN_INSTANTANEOUS_FEATURES
                if c in frame.columns and frame.tail(1)[c].notna().any()
            ]
            if (
                coverage["fraction"] < coverage_floor
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

    site_health = {}
    for site, payload in all_site_payloads.items():
        probabilities = []
        ready = 0
        for record in payload.get("records", []):
            probabilities.extend(
                float(value)
                for value in (record.get("research_probabilities") or {}).values()
                if value is not None
            )
            if (record.get("environment_readiness") or {}).get("ready"):
                ready += 1

        probabilities.sort()
        count = len(probabilities)
        site_health[site] = {
            "current_objects": payload["current_object_count"],
            "scored_objects": payload["scored_object_count"],
            "score_fraction": (
                payload["scored_object_count"] / payload["current_object_count"]
                if payload["current_object_count"] else 0.0
            ),
            "environment_ready_fraction": (
                ready / len(payload.get("records", []))
                if payload.get("records") else 0.0
            ),
            "probability_max": max(probabilities) if probabilities else None,
            "probability_median": probabilities[count // 2] if probabilities else None,
            "probability_p90": (
                probabilities[min(count - 1, int(round((count - 1) * 0.90)))]
                if probabilities else None
            ),
            "probability_ge_10pct": sum(value >= 0.10 for value in probabilities),
            "probability_ge_20pct": sum(value >= 0.20 for value in probabilities),
            "probability_ge_50pct": sum(value >= 0.50 for value in probabilities),
            "candidate_only_not_operational": True,
        }

    (args.output_root / "shadow_health.json").write_text(
        json.dumps({
            "status": "healthy",
            "mode": "live_shadow_research",
            "operational_release_status": "candidate_only_not_operational",
            "probability_status": "research_shadow_candidate",
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "sites": site_health,
        }, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
