# Operational Readiness Contract

Before probability scoring is enabled, the project must first demonstrate that
the live object stream itself is trustworthy.

## Current gate

The live worker is currently **probability-free**. A valid unscored live product
must have a coherent worker state and GeoJSON scan timestamp, a non-empty source
identifier, matching object counts, Polygon geometry for every delivered object,
object timestamps consistent with the output scan, centroids inside the BTV
sanity bounds, probability fields explicitly null, and metadata explicitly set
to probability_status = not_scored.

Run:

    python scripts/audit_operational_readiness.py

The command is intended for CI and manual operational tests.

## Why this exists

The model should not become the first thing we validate operationally. Acquisition,
Level-II reading, geolocation, object detection, tracking, state persistence,
and product serialization each need a contract first.

Once a model exists, this gate can be extended with model version, probability
range, feature availability, latency, and stale-product checks without changing
the live-worker interface.

## Research-operational candidate stage

The project now has an intermediate release state between a probability-free
research build and a fully operational product:

1. **Probability-free** — live object acquisition/detection is validated, but no
   model probabilities are exposed.
2. **Research shadow** — a calibrated candidate model scores live objects in an
   isolated shadow feed; the score never controls an operational product.
3. **Research-operational candidate** — the four horizon candidate bundles pass
   live-compatibility and calibration checks, have minimum case-held-out support,
   and may be used for sustained real-time shadow testing and historical replay.
4. **Operational release** — requires independent modern validation, sustained
   live verification, human forecaster review, reproducibility evidence, and an
   explicit release decision.

The research-operational candidate gate intentionally allows a smaller initial
training population. Limited sample size lowers confidence in the evaluation
rather than forcing the project to wait for a perfect dataset. The operational
probability switch remains disabled until the higher-level evidence gates pass.

Environment freshness is carried as a live-compatible predictor. Complete RAP
analyses through the allowed retrospective age window may be scored with a
`degraded_freshness` confidence flag when they exceed the preferred freshness
target.
