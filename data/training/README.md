# Training Dataset

The final ML matrix will contain one row per tracked radar object per scan time.

The current verified seed is the 36-case Banacos et al. (2014) northern NY/VT snow-squall climatology. It contains published event timing, observing station, visibility, wind, temperature, and hybrid-event metadata.

This event table is not itself the ML matrix. Reconstruction must turn each event into scan-by-scan radar objects, attach environment and surface observations, and create future-event targets.

The Southern New England 1994-2018 climatology contributes a separate 100-event positive population.

## Supervised positive gate

The expanded pipeline separates three populations:

1. **Documented case archive** — all cases with strong documentary or operational evidence remain available for research/review.
2. **Supervised training cohort** — a hard positive is admitted only when the case has a strong documented/study source, observed surface timing, reconstructed radar-object evidence, and sufficient evidence points.
3. **Review/weak population** — warning-only, screening, incomplete, or otherwise insufficient cases remain archived but are not automatically converted into hard positives.

This distinction is deliberate. An official Snow Squall Warning is evidence, but warning issuance time is not assumed to equal observed squall onset. The target labels remain tied to the best independently supported event timing available at replay time.

## Cumulative-batch protection

Expanded feature batches carry `supervision_class=supervised_positive` on positive-context rows. When a new batch is merged with an older cumulative artifact, positive rows from pre-gate batches that lack this provenance are discarded rather than silently becoming training positives. Null/research rows are retained.

The expansion workflow also runs an integrity audit covering predictor/target separation, forecast-time timestamp validity, duplicate object-timestep identities, population counts, and 15/30/45/60-minute target availability.
