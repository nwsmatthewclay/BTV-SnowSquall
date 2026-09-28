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

Core fields include object ID, scan time, radar site, centroid latitude/longitude, reflectivity statistics, pixel count, area, length, width, geometry, reader_backend provenance, and leakage-safe motion features.

Track catalogs additionally carry qc_status and qc_flags for suspicious reconstruction artifacts such as very large connected objects, temporal gaps, geometry loss, or abrupt area jumps. QC flags do not automatically remove observations; they identify records for review.

## Environment fields

The common environmental layer records environment_source, environment_valid_time_utc, environment_age_minutes, environment_status, CAPE, PWAT, visibility, surface temperature, 2-m temperature/dewpoint/RH, 10-m wind components and speed, and gust.

Environment source is date-aware:
- before 1 April 2007: NARR-A, 32-km, 3-hourly historical analysis;
- 1 April 2007 through 30 April 2012: RUC 13-km;
- 1 May 2012 onward: RAP.

The sources are intentionally retained as distinct fields rather than treated as numerically interchangeable. NARR is used for the early Banacos period because the RUC 13-km analysis archive does not provide the required 2004–2006 coverage. Missing diagnostics remain null rather than being invented.

## Labels

Verified-case labels are generated separately from descriptive case context. Positive association is now track-aware: a reconstructed object track must enter the 75-km station corridor during the verified event window (plus a bounded pre/post-event margin) before it can receive a positive event label.

Prospective outcome labels must only use future observations relative to the prediction timestamp. Null objects remain candidate negatives until radar/event quality control is complete.

## Dataset versions

object_population_pilot_v1 is the first common positive/null schema intended for dataset auditing and feature/model development. It is not yet a final training set.
