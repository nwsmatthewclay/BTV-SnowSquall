"""Shared environment completeness and freshness contract for training/live inference."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

REQUIRED_ENVIRONMENT_FIELDS = (
    "cape_jkg",
    "pwat_mm",
    "temperature_2m_k",
    "dewpoint_2m_k",
    "rh_2m_pct",
    "u10_ms",
    "v10_ms",
)

DEFAULT_MAX_AGE_MINUTES = 90.0


def _parse_time(value):
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def flatten_environment(record: Mapping) -> dict:
    """Promote nested environment.fields into top-level feature keys."""
    row = dict(record)
    environment = row.get("environment")
    if isinstance(environment, Mapping):
        fields = environment.get("fields")
        if isinstance(fields, Mapping):
            for key, value in fields.items():
                if row.get(key) is None:
                    row[key] = value
        if row.get("environment_source") in (None, ""):
            row["environment_source"] = environment.get("source")
        if row.get("environment_status") in (None, "", "unknown"):
            row["environment_status"] = environment.get("status")
        if row.get("environment_source_valid_time_utc") is None:
            row["environment_source_valid_time_utc"] = environment.get("source_valid_time_utc")
        if row.get("environment_age_minutes") is None:
            row["environment_age_minutes"] = environment.get("age_minutes")
        if row.get("environment_missing_fields") is None:
            row["environment_missing_fields"] = environment.get("missing_fields") or []
    return row


def assess_environment(
    record: Mapping,
    *,
    radar_time=None,
    max_age_minutes: float = DEFAULT_MAX_AGE_MINUTES,
    required_fields=REQUIRED_ENVIRONMENT_FIELDS,
) -> dict:
    """Assess whether an environment record is safe for model scoring."""
    row = flatten_environment(record)
    environment = row.get("environment") if isinstance(row.get("environment"), Mapping) else {}

    fields = {name: row.get(name) for name in required_fields}
    missing = [name for name, value in fields.items() if value is None]

    source = row.get("environment_source") or environment.get("source")
    status = row.get("environment_status") or environment.get("status")
    source_value = row.get("environment_source_valid_time_utc") or environment.get("source_valid_time_utc")
    source_time = _parse_time(source_value)

    reference_time = _parse_time(radar_time or row.get("timestamp"))
    age = row.get("environment_age_minutes")
    try:
        age = float(age) if age is not None else None
    except (TypeError, ValueError):
        age = None
    if age is None and source_time is not None and reference_time is not None:
        age = (reference_time - source_time).total_seconds() / 60.0

    reasons = []
    if source in (None, ""):
        reasons.append("environment_source_missing")
    if status not in ("complete", "ready"):
        reasons.append("environment_status_not_complete")
    if missing:
        reasons.append("required_fields_missing")
    if age is None:
        reasons.append("environment_age_unknown")
    elif age > max_age_minutes:
        reasons.append("environment_stale")
    elif age < -2.0:
        reasons.append("environment_timestamp_in_future")

    return {
        "ready": not reasons,
        "source": source,
        "status": status,
        "source_valid_time_utc": source_time.isoformat().replace("+00:00", "Z") if source_time else None,
        "age_minutes": round(age, 2) if age is not None else None,
        "max_age_minutes": float(max_age_minutes),
        "required_fields": list(required_fields),
        "missing_fields": missing,
        "reasons": reasons,
    }
