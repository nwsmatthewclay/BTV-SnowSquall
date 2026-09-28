# BTV Snow Squall

Experimental BTV CWA snow-squall detection and probability project.

## What we are building

This is a **living event/object database and prediction system**, not an SNSQ calculator.

The core training unit is:

> **tracked radar object × scan time**

Each row combines the conditional environment with observed storm structure and evolution.

## Data flow

acquisition → normalization → candidate detection → tracking → 3-D/dual-pol features → environmental/MRMS attachment → evidence-based labeling → training table → model → verification

## Data layers

- NEXRAD Level II from KCXX and KTYX
- RAP environmental analyses and derived SNSQ/thermodynamic/kinematic fields
- MRMS precipitation, rate, type, echo-top and related fields
- ASOS/METAR/NCEI surface observations
- Official SQW/event documentation
- Published snow-squall case datasets and studies

## Initial prediction target

Probability that a tracked radar object will meet the positive snow-squall definition within the **next 30 minutes**.

The first model ladder is intentionally interpretable: logistic regression, random forest, histogram gradient boosting, then calibrated/ensemble models after the feature set is stable.

## Radar philosophy

The detector is deliberately permissive. It generates candidate precipitation objects; it does **not** decide whether they are snow squalls.

Native Level-II volumes are retained so we can extract reflectivity intensity and gradients, object geometry and organization, velocity/kinematic signatures, echo-top and vertical depth, ZDR/RHOHV/KDP, and scan-to-scan growth, weakening, motion and structural change.

## Truth philosophy

No single product is treated as perfect truth. A warning polygon, surface visibility observation, radar structure/evolution, and published case documentation can each contribute evidence. Labels retain the evidence sources and confidence.

Uncertain cases remain in the archive but are excluded from the initial supervised training set.

## Repository structure

- `acquisition/` — archive/near-real-time data acquisition and readers
- `config/` — dataset and archive configuration
- `schema/` — feature schema and labeling policy
- `processing/` — radar detection, tracking and feature calculations
- `labeling/` — evidence and truth construction
- `training/` — model-training utilities
- `docs/` — architecture, source registry, ML strategy and implementation plan
- `scripts/` — reproducible dataset/manifest utilities
- `tests/` — automated smoke tests
- `data/` — manifests and local scientific data; large files are excluded from Git

## Development

Use `requirements.txt` for lightweight development and `requirements-science.txt` for Level-II/radar reconstruction.

GitHub Actions intentionally keeps the default test job lightweight. Scientific archive processing will use separate integration tests so large radar dependencies do not block normal code changes.

## Modeling principles

The environmental Snow Squall Parameter is a predictor, not the answer.

Training/evaluation will:

1. Preserve complete case histories.
2. Use radar-object and temporal information.
3. Keep future information out of predictors.
4. Hold out complete events rather than random adjacent rows.
5. Evaluate calibration, discrimination, false alarms, misses and lead time.
6. Preserve missing-data/provenance flags instead of silently filling gaps with future information.

See `docs/architecture.md`, `docs/implementation_plan.md`, `docs/ml_strategy.md`, `schema/label_policy.md`, and `docs/git_workflow.md`.
