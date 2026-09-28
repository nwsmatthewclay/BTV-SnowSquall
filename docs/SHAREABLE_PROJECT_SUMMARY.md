# BTV Snow Squall — Research Project Summary

## Purpose

The BTV Snow Squall project is a research pipeline for building a living,
event/object-level snow-squall dataset and eventually testing a probabilistic
forecast model.

The intended prediction unit is a **tracked radar object at a specific scan
time**. Environmental ingredients such as the Snow Squall Parameter are treated
as predictors rather than as the complete answer.

## What is already implemented

### Historical case reconstruction
- A 36-case Banacos-based historical manifest is staged.
- KCXX and KTYX Level-II acquisition is automated through the public NEXRAD
  archive.
- Archived volumes are retained with explicit reader provenance and failures.
- Geographic object reconstruction uses a common Cartesian grid.
- The detector preserves candidate footprints rather than reducing each object
  to a centroid only.
- A deterministic object tracker provides scan-to-scan identity and age.
- Native multi-elevation radar sampling provides a vertical-structure profile
  diagnostic.
- Lowest-sweep dual-polarization and radial-velocity descriptors are available.
- Scan-to-scan growth, reflectivity change, motion, and structural evolution
  are represented.

### Environmental context
Historical environments are selected by valid date so the predictor pipeline
does not accidentally use a later analysis era. Available providers are
recorded rather than silently substituted.

### Truth and labels
The project separates:
1. documented historical case context;
2. independent surface-observation evidence;
3. candidate winter-null context; and
4. final model targets.

Labels retain evidence-source and confidence information. Candidate null windows
remain explicitly provisional until quality control is complete.

### Leakage protection
Forecast-time predictors are constructed from current and past observations.
Published onset, outcome labels, surface observations used as truth, event
identifiers, and future-derived fields are excluded from the predictor set.
Training groups are held out by complete historical case/null window rather than
randomly splitting adjacent scans.

### Operational bridge
Archived Level-II scans can now be replayed one scan at a time through the same
processing path used by the near-real-time worker. This validates the software
pathway without allowing future scans into the current-scan state.

## Quality gates

The repository includes explicit audits for:
- manifest identity;
- independent surface-observation coverage;
- native Level-II field availability;
- radar reconstruction failures and reader provenance;
- geographic sanity bounds;
- annotation identity;
- feature coverage;
- model feature policy;
- training-table integrity; and
- unscored live-object product integrity.

The radar reconstruction audit distinguishes failed volumes from successful
volumes that simply contain no detected candidate objects. A configurable
failure-rate gate is applied to keep materially incomplete reconstruction from
passing silently.

## Current operational status

The current live worker is **probability-free**. Its product explicitly reports
probability_status = not_scored.

The historical explorer can display:
- reconstructed radar frames;
- candidate object footprints;
- track history;
- object geometry and evolution;
- time-matched environmental information where available; and
- historical context/analog comparisons.

These outputs are research/pilot products, not operational forecast guidance.

## What remains before operational probability scoring

The most important remaining work is scientific validation at larger sample size:
- complete full-population 3-D radar feature extraction;
- complete and quality-controlled MRMS feature extraction;
- definitive hard-negative/object QC;
- larger independent historical populations;
- stable target definitions and annotation review;
- case-held-out model evaluation with enough independent positive cases;
- probability calibration and reliability evaluation;
- false-alarm, miss, and lead-time evaluation; and
- an independent operational-style replay/test set not used to develop the
  model.

## Scientific reference

The Snow Squall Parameter implementation follows Banacos, Loconto, and DeVoir
(2014). Their published formulation combines mean 0–2 km relative humidity,
surface-to-2-km potential instability in equivalent potential temperature, and
mean 0–2 km wind speed, with a 2-m wet-bulb temperature threshold used to zero
the parameter when the near-surface environment is too warm for snow. The
project treats this parameter as one environmental predictor within a much
larger object-level framework.

Reference:
Banacos, P. C., Loconto, A. N., & DeVoir, G. A. (2014), *Snow Squalls:
Forecasting and Hazard Mitigation*, Journal of Operational Meteorology 2(12),
130–151.
