# Object Population Dataset Schema

The object-population pilot combines verified-case context with winter null candidates without treating every null radar object as a confirmed negative.

## Population fields

| Field | Meaning |
|---|---|
| population | verified_case_context or winter_null_candidate |
| truth_status | Current evidence status; nulls remain unverified until event QC |
| case_id | Banacos verified case identifier when applicable |
| null_id | Deterministic sampled null-window identifier when applicable |
| population_track_key | Unique population/radar/object namespace |
| future_information_policy | Declares that features are restricted to information available by scan time |

## Radar/object fields

Core fields include object ID, scan time, radar site, centroid latitude/longitude, reflectivity statistics, pixel count, area, length, width, geometry, and leakage-safe motion features.

## Environment fields

The common environmental layer records environment_source, environment_valid_time_utc, environment_age_minutes, environment_status, CAPE, PWAT, visibility, surface temperature, 2-m temperature/dewpoint/RH, 10-m wind components and speed, and gust.

For scans before 1 May 2012, the historical provider is RUC 13-km. For scans on/after 1 May 2012, the provider is RAP. This distinction is intentional: the model generations are not assumed to be numerically interchangeable; fields unavailable in one source remain null.

## Labels

Verified-case labels are generated separately from descriptive case context. Prospective outcome labels must only use future observations relative to the prediction timestamp. Null objects remain candidate negatives until radar/event quality control is complete.

## Dataset versions

object_population_pilot_v1 is the first common positive/null schema intended for dataset auditing and feature/model development. It is not yet a final training set.
