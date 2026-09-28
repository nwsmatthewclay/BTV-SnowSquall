# BTV Snow Squall Modeling Architecture

## Goal

Build a living, reproducible snow-squall dataset combining the conditional environmental threat with observed radar structure and storm evolution.

Core unit: radar object × scan time.

## Data layers

1. Environment: RAP hourly fields, SNSQ, thermodynamics, moisture, lapse rates, wind/shear, vertical motion and synoptic diagnostics.
2. Radar: native KCXX/KTYX Level II, reflectivity, velocity, spectrum width and dual-pol; derived geometry, vertical structure and kinematics.
3. MRMS: maximum available scan frequency, precipitation type/rate, reflectivity, echo-top and relevant masks/products.
4. Surface truth: NCEI/ASOS/METAR visibility, snow/precipitation, wind/gust and timing.
5. Event truth: official SQW information and published case documentation.

## Archive design

Process at most 30 minutes per archive run. Retain a rolling 3 hours. Backfill missing periods oldest-first. Preserve native/full-resolution scientific inputs and all masks/composites/derived science products without degradation. RAP is hourly/cached. MRMS is collected at maximum available scan frequency. Dual-pol is processed on every archive run.

The Git repository stores code, manifests, metadata, schemas and small fixtures. Large scientific archives are not committed as ordinary Git blobs.

## Modeling flow

acquisition → normalization → object detection → tracking → feature extraction → labeling → training table → model → verification

SNSQ is a feature, not the model itself.

## Initial models

Start with interpretable tabular baselines such as logistic regression and gradient-boosted trees. The first target is a 30-minute probability.

## Validation

Hold out complete cases, not random rows. Report reliability/calibration, Brier score, ROC-AUC, PR-AUC, probability distributions, lead-time performance and performance by case/environment regime.
