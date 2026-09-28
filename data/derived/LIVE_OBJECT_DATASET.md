# Live Object-Timestep Dataset

The live worker maintains an append-only object history at:

- `data/derived/live_object_history.jsonl` — canonical nested record stream.
- `data/derived/live_object_history.csv` — flattened training-friendly view.

One record represents **one tracked radar object at one radar scan time**.

## Temporal rule

A record may contain only information that was available at the observation time.

Radar evolution fields use the current scan plus retained state from earlier scans. RAP environmental fields use the latest RAP analysis whose valid time is at or before the radar scan. Future model analyses are never substituted.

## Record groups

### Identity/time
- `timestamp`
- `radar_site`
- `source_file`
- `track_id`

### Radar structure
- centroid latitude/longitude
- area, length, width, aspect ratio, orientation
- pixel/core counts and core fraction
- maximum and mean reflectivity

### Object evolution
- motion speed/direction
- age in scans
- reflectivity trend
- area growth fraction

### Environment
- RAP valid time and age
- visibility, gust, surface temperature
- CAPE/CIN variants
- PWAT
- 0–1 km and 0–3 km SRH
- 0–6 km shear components and magnitude
- 10-m wind
- 2-m temperature/dewpoint/RH

RAP provides the environmental fields used here, including CAPE/CIN, PWAT, HLCY, VUCSH/VVCSH, temperature, wind, and visibility.

### Label fields

`label_status` is initially `unlabeled` and `snow_squall_outcome` is null.

These fields must be populated by a **separate historical labeling pipeline**. The live worker must never infer a future outcome from later scans.

## Why JSONL + CSV?

JSONL preserves the full object record and can be extended with nested diagnostics without changing the schema of older records. CSV provides a simple tabular input for analysis and baseline machine-learning experiments.

The dataset is intentionally separate from the probability model. This allows the same historical object records to support multiple label definitions and model experiments without rewriting the acquisition/tracking system.
