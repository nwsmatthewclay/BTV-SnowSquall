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
