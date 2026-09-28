"""Select the appropriate historical environment analysis for a radar time."""
from __future__ import annotations

from datetime import datetime, timezone

from acquisition.rap_environment import acquire_for_radar_time as acquire_rap
from acquisition.ruc_environment import acquire_for_radar_time as acquire_ruc
from processing.rap_features import extract_features as extract_rap
from processing.ruc_features import extract_features as extract_ruc

RAP_START = datetime(2012, 5, 1, tzinfo=timezone.utc)


def provider_for_time(radar_time: datetime) -> str:
    radar_time = radar_time.astimezone(timezone.utc)
    if radar_time < RAP_START:
        return "RUC"
    return "RAP"


def acquire_for_radar_time(radar_time, rap_dir, ruc_dir, max_age_minutes=180):
    provider = provider_for_time(radar_time)
    if provider == "RUC":
        result = acquire_ruc(radar_time, output_dir=ruc_dir, max_age_minutes=max_age_minutes)
    else:
        result = acquire_rap(radar_time, output_dir=rap_dir, max_age_minutes=max_age_minutes)
    if result is None:
        return None
    match, path = result
    return provider, match, path


def extract_features(provider, path, latitude, longitude, radar_time, expected_valid_time):
    if provider == "RUC":
        return extract_ruc(path, latitude, longitude, radar_time, expected_valid_time)
    return extract_rap(path, latitude, longitude, radar_time, expected_valid_time)
