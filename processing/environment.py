"""Select the appropriate historical environment analysis for a radar time."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from acquisition.narr_environment import acquire_for_radar_time as acquire_narr
from acquisition.rap_environment import acquire_for_radar_time as acquire_rap
from acquisition.ruc_environment import acquire_for_radar_time as acquire_ruc
from processing.narr_features import extract_features as extract_narr
from processing.rap_features import extract_features as extract_rap
from processing.ruc_features import extract_features as extract_ruc

NARR_END = datetime(2007, 4, 1, tzinfo=timezone.utc)
RAP_START = datetime(2012, 5, 1, tzinfo=timezone.utc)


def provider_for_time(radar_time: datetime) -> str:
    radar_time = radar_time.astimezone(timezone.utc)
    if radar_time < NARR_END:
        return "NARR"
    if radar_time < RAP_START:
        return "RUC"
    return "RAP"


def environment_cache_key(radar_time):
    """Return the historical analysis cadence bucket for a radar time.

    NARR analyses are 3-hourly; RUC and RAP analyses are hourly. Using the
    native cadence prevents repeated remote existence probes for the same
    analysis when many objects share one scan window.
    """
    radar_time = radar_time.astimezone(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    provider = provider_for_time(radar_time)
    if provider == "NARR":
        radar_time = radar_time.replace(hour=(radar_time.hour // 3) * 3)
    return provider, radar_time.isoformat()


def acquire_for_radar_time(
    radar_time, rap_dir, ruc_dir, narr_dir=None, max_age_minutes=180
):
    provider = provider_for_time(radar_time)
    if provider == "NARR":
        result = acquire_narr(
            radar_time,
            output_dir=Path(narr_dir) if narr_dir else Path(ruc_dir).parent / "NARR",
            max_age_minutes=max(360, max_age_minutes),
        )
    elif provider == "RUC":
        result = acquire_ruc(
            radar_time, output_dir=ruc_dir, max_age_minutes=max_age_minutes
        )
    else:
        result = acquire_rap(
            radar_time, output_dir=rap_dir, max_age_minutes=max_age_minutes
        )
    if result is None:
        return None
    match, path = result
    return provider, match, path


def canonicalize_environment_fields(provider, fields):
    """Map provider-specific names onto the repository's canonical schema."""
    out = dict(fields or {})

    aliases = {
        "sbcape_jkg": "cape_jkg",
        "sbcin_jkg": "cin_jkg",
        "lapse_rate_0_3km_c_km": "lr_0_3_c_km",
        "lapse_rate_0_7_5km_c_km": "lr_0_7p5_c_km",
        "wet_bulb_0_3km_c": "wetbulb_0_3_c",
    }
    for canonical, source in aliases.items():
        if canonical not in out and out.get(source) is not None:
            out[canonical] = out[source]

    if out.get("shear_0_6km_ms") is not None and out.get("shear_0_6km_kt") is None:
        out["shear_0_6km_kt"] = float(out["shear_0_6km_ms"]) * 1.943844

    if out.get("visibility_m") is not None and out.get("visibility_sm") is None:
        out["visibility_sm"] = float(out["visibility_m"]) / 1609.344

    if out.get("cloud_layer_mean_wind_ms") is not None and out.get("cloud_layer_mean_wind_kt") is None:
        out["cloud_layer_mean_wind_kt"] = float(out["cloud_layer_mean_wind_ms"]) * 1.94384449244
    if out.get("cloud_layer_shear_ms") is not None and out.get("cloud_layer_shear_kt") is None:
        out["cloud_layer_shear_kt"] = float(out["cloud_layer_shear_ms"]) * 1.94384449244

    return out


def extract_features(
    provider, path, latitude, longitude, radar_time, expected_valid_time
):
    if expected_valid_time is not None:
        radar_utc = radar_time.astimezone(timezone.utc)
        valid_utc = expected_valid_time.astimezone(timezone.utc)
        if valid_utc > radar_utc:
            raise ValueError(
                f"future {provider} environment analysis {valid_utc.isoformat()} > "
                f"radar {radar_utc.isoformat()}"
            )

    if provider == "NARR":
        result = extract_narr(
            path, latitude, longitude, radar_time, expected_valid_time
        )
    elif provider == "RUC":
        result = extract_ruc(
            path, latitude, longitude, radar_time, expected_valid_time
        )
    else:
        result = extract_rap(path, latitude, longitude, radar_time, expected_valid_time)

    result["fields"] = canonicalize_environment_fields(
        provider, result.get("fields", {})
    )
    return result
