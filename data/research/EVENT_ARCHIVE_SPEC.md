# Snow Squall Event Radar + Environment Archive

## Purpose

This archive is the synchronized research layer for SnowSquallProbSevere. Each
case/radar scan is tied to an event timestamp and a historical environment
analysis. The goal is to make radar-signature research reproducible without
re-reading every native Level-II volume.

## Radar payload

Each scan directory contains:

- `radar_fields.npz`: common 1-km geographic grid with latitude/longitude,
  reflectivity in dBZ, and lowest-tilt radial/base velocity in both m/s and kt.
  When present, spectrum width and dual-pol fields (ZDR, RHOHV, KDP) are also
  retained.
- `reflectivity.png`: fixed-extent visual product.
- `base_velocity.png`: fixed-extent lowest-sweep velocity product.
- `metadata.json`: source Level-II path, scan/event timing, reader backend,
  and field availability.

The fixed grid is the same geographic reconstruction used by the object
detector, so image-space signatures can be compared between KCXX and KTYX
without mixing native polar-grid geometry.

## Environment payload

`event_environment_timeseries.csv` contains one row per event/radar scan.
The archive preserves the historical source policy already used by the model:

- NARR for the earliest archive era.
- RUC for the transition era.
- RAP for the modern era.

Core diagnostics include SNSQ, SBCAPE/MLCAPE/MUCAPE, CIN, DCAPE, PWAT, LCL,
0-1/0-3/0-6 km wind/shear diagnostics, lapse rates, thermodynamic fields,
frontogenesis/dCVA/omega/EPV when available, and the Schneider-style
cloud-layer diagnostics.

`snsq_status` is explicit. A null SNSQ is never silently converted to zero;
historical provider limitations remain distinguishable from acquisition
failures.

## Event organization

The top-level archive contains:

```
snow_squall_events/
  archive_summary.json
  event_scan_manifest.csv
  event_environment_timeseries.csv
  event_archive_qc.csv
  object_model_features_expanded.csv        # when supplied by expansion
  scans/
    KCXX/YYYYMMDD/YYYYMMDD_HHMMSS/
      radar_fields.npz
      reflectivity.png
      base_velocity.png
      metadata.json
    KTYX/...
```

The global scan manifest is the join key between event metadata, radar images,
and environmental snapshots. `minutes_from_event_start` supports aligned
composites such as -90, -60, -30, 0, +30 minutes.

## Training principle

Keep three layers distinct:

1. **Raw truth/provenance** — native Level-II and source environmental files.
2. **Portable archive** — gridded radar + images + synchronized environments.
3. **Model features** — object-centered features, temporal evolution, labels and
   candidate probabilities.

That separation lets us change object definitions, image-derived features, or
model families without rebuilding the historical raw archive.
