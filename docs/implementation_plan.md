# Implementation Plan

## Phase 1 — foundation

Preserve the current Level II acquisition prototype. Establish the dataset schema, label policy, reproducible configuration, manifests, archive interfaces and smoke tests.

## Phase 2 — case reconstruction

Seed the case universe from the Banacos BTV 36-case climatology, the 100-case Southern New England study, and the Penn State SNSQ/null dataset as an external environmental reference.

Build a case manifest before downloading data. Record source availability for every case.

## Phase 3 — radar reconstruction

For every case: determine the event window, determine radar coverage, acquire native Level II, build the scan manifest, detect candidate precipitation objects, track objects through time, extract 3-D structure and dual-pol features, and attach MRMS fields.

## Phase 4 — environmental reconstruction

Match each radar object/scan to the nearest valid RAP analysis, preserve source analysis time and age, interpolate environmental fields to the object location, and attach SNSQ and derived environmental fields.

## Phase 5 — truth and labeling

Attach SQW, ASOS/METAR, NCEI and case-study evidence. Assign label and confidence according to the label policy.

## Phase 6 — first model

Construct a leakage-controlled 30-minute target and train interpretable baselines. Use complete-case holdouts and document every train/test split.

## Phase 7 — operational testing

Run the model on newly arriving radar data without future information. The first test asks whether the model identifies evolving snow-squall-like objects early enough to be operationally useful while maintaining useful probability calibration.

## Reproducibility

Every dataset build records configuration version, code commit, source manifests, model version, processing timestamp, missing-data flags, and label source/confidence.
