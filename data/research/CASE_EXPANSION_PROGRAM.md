# Snow Squall Case Expansion Program

## Objective
Build the largest defensible historical snow-squall/convective-snow reconstruction pool practical for BTV-SnowSquall while keeping truth classes separate from research analogs.

The target is not all published cases becoming positives. The target is:
1. discover as many candidate events as possible;
2. attach exact event timing/location and provenance;
3. retrieve radar and environmental data with the same causal feature pipeline used by live scoring;
4. independently verify surface impacts where possible;
5. promote only evidence-qualified cases to supervised-positive truth;
6. retain weaker cases as research-positive/analog populations and hard negatives.

## Cohort inventory

| Source | Approx. cases | Primary use |
|---|---:|---|
| Banacos et al. 2014 | 36 | BTV/Northern NY benchmark and highest-priority reconstruction |
| Colby et al. 2022 | 100 | Southern New England independent snow-squall cohort |
| Schneider et al. 2024 | 159 | Central PA convective-snow research cohort; prioritize S1 |
| Lukinbeal 2024 | 74 | Western Montana external snow-squall validation |
| Capella Wyoming cohort | 56 | Western Plains external validation |
| Northeast radar mosaic archive | 600+ winter-storm days | candidate discovery and hard-negative/background radar |
| Individual published case studies | additional | targeted extreme/atypical cases |

These populations overlap conceptually and geographically. Deduplication and provenance must occur before any training promotion.

## Evidence tiers

### Tier A — supervised positive
Requires strong event documentation, consistent surface timing, successful radar reconstruction, and independent verification points under the repository evidence gate.

### Tier B — research positive
Published/documented event with usable reconstruction but incomplete independent verification.

### Tier C — research analog
Convective snow or snow-band event that is physically relevant but does not meet the project snow-squall truth definition.

### Tier D — hard negative
Winter precipitation/object environment with substantial radar activity or squall-like ingredients but no verified target outcome.

### Tier E — quiet/null
Non-event background windows sampled causally from the same cool-season/radar population.

## Reconstruction contract

Every promoted reconstruction should use the same pipeline:
provenance -> radar inventory -> Level-II/MRMS reconstruction -> object tracking -> environmental retrieval -> surface/METAR/MPING evidence -> causal feature builder -> horizon labels -> evidence audit

Do not create a separate feature path for literature cases.

### Radar
Primary BTV reconstruction: KCXX and KTYX.
For external cohorts, use the radar identified by the source study where practical and retain source radar and sampling metadata. Record radar coverage and beam limitations explicitly.

### Environment
Retrieve the best historically available analysis consistent with the case period, prioritizing RAP/RUC where available and ERA5 for longer-period research/validation. Source-study environmental data may be mapped into the project schema when defensible.

All live predictors remain current/past-only at score time. Future environmental values may be retained only in truth/diagnostic tables, never predictor columns.

### Surface verification
Use, where available: METAR/ASOS/AWOS present weather; NCEI/SWDI; IEM Local Storm Reports; NWS Snow Squall Warnings/VTEC; MPING; and source-study observations.

Association is QC evidence, not automatically event truth.

## Acquisition order

1. Finish the 36-case Banacos benchmark.
2. Extract and deduplicate the 100 Colby cases; prioritize events intersecting northern New England/BTV radar coverage.
3. Acquire the 159 Schneider case catalog; prioritize S1/frontally organized cases for detailed reconstruction while retaining all modes as research analogs.
4. Add the 74 Lukinbeal events as an external validation cohort.
5. Add the 56 Wyoming events as a separate external validation cohort.
6. Mine the Northeast 1996–2023 radar mosaic archive for additional candidate events and hard negatives.
7. Add targeted case studies such as Milrad 2011/2014, Pettegrew 2009, Rosenow 2018 and similar high-value atypical cases.
8. Re-run evidence scoring and only then expand supervised training.

## Computational strategy

Because full radar/environment reconstruction for hundreds of cases is expensive:
- maintain a lightweight case catalog first;
- deduplicate before downloading Level-II;
- reconstruct bounded pre/post windows around each candidate;
- cache acquisition metadata and failure reasons;
- checkpoint every cohort;
- merge cumulatively with row-identity protection;
- keep missing data explicit rather than silently substituting values;
- train only after cumulative audits pass.

The expansion should be a growing research archive rather than one giant all-or-nothing job.

## Scientific guardrails

Published identification is not equivalent to NWS warning truth.

The Schneider climatology distinguishes broad convective snow from the smaller subset of frontal snow-squall-like events, while the Colby climatology uses an observation-based definition that can still miss events and include borderline cases. Those distinctions must remain encoded in the dataset.

## Deliverables

- case discovery ledger
- source-specific normalized case catalogs
- radar acquisition manifests
- environmental acquisition manifests
- surface verification tables
- object-track catalogs
- evidence scorecards
- cumulative causal feature batches
- independent validation splits
- replay viewer cases
- four-horizon candidate model bundles

No model is operationally released merely because the historical case count increases.

## Initial model-development batch

The first science test will target approximately 200 reconstructed episodes rather than waiting for the full literature inventory. The 200-case target is a sampling objective, not a quota: supervised positives are limited by evidence quality, while research positives, analogs, hard negatives, and strong nulls are retained separately. The database remains extensible after the first model/replay test.

Null screening uses IEM LSRs plus NCEI Storm Events, NWS warnings/VTEC, surface observations, and radar/object reconstruction. Missing IEM or Storm Events records are never sufficient alone to label a negative.
