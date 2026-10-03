# Historical Replay and Tuning Lab

## Purpose

The replay lab evaluates the current snow-squall object detector and candidate probability model by processing archived Level-II scans one timestamp at a time.

The replay path is deliberately identical to the live object-processing path:
1. Read one Level-II volume.
2. Detect candidate objects with the current reflectivity/gradient/contrast detector.
3. Associate persistent object identity.
4. Build current-and-past-only radar/environment features.
5. Score the research candidate models for 15/30/45/60 minute horizons.
6. Preserve raw horizon outputs and monotone cumulative probabilities.
7. Compare the resulting timeline to independently documented event onset.

## Tuning measurements

Each replay records:
- first probability crossing by threshold,
- lead time to first crossing,
- peak pre-onset probability,
- post-onset probability,
- fraction of pre-onset scans above threshold,
- object count and radar coverage,
- detector geometry and enhancement diagnostics.

The goal is to tune both segmentation and modeling against the same historical episodes rather than optimize either component in isolation.

## Model generations

candidate_ensemble_refresh_*m is the current research candidate trained from the previously archived feature population.

A new candidate model trained after the corrected object reconstruction becomes available as a separate generation. Historical replay must preserve the model generation in its experiment manifest so detector and model changes remain attributable.

## Operational progression

Candidate probabilities remain isolated from the operational product until:
- the object detector has acceptable historical continuity and false-object behavior,
- independent historical cases demonstrate useful lead-time behavior,
- calibration is checked,
- modern held-out validation remains separate,
- live shadow behavior is reviewed,
- the predictor schema is fully live-compatible.

A candidate can therefore be replayed and shadowed repeatedly without being treated as an operational forecast.