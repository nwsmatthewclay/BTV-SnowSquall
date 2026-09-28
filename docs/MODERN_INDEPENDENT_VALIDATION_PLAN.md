# Modern Independent Validation Plan

## Purpose

The Banacos historical population is the development foundation for object
reconstruction, causal feature construction, and initial model experiments.
It should not also serve as the final independent verification population.

The next validation population should begin in the modern data era and be
constructed independently from the historical training cases.

## Recommended modern population

Use a separate case manifest for events from 2014 onward so archived MRMS
products can be evaluated where available. Preserve the historical population
unchanged; do not backfill MRMS fields into older cases.

The modern population should contain:

- event timing and location from independent documentation;
- archived KCXX/KTYX Level-II where available;
- surface observations;
- RAP environmental analyses;
- MRMS products when the archive provides them;
- a documented observation/warning provenance field;
- explicit uncertain cases that remain archived but outside the first verification
  sample.

## Independent verification boundary

No modern verification case should contribute:

- model tuning;
- threshold selection;
- feature selection;
- calibration parameters;
- post-hoc label corrections driven by verification results.

The final verification code revision should be frozen before the modern sample is
scored. The release manifest must record the exact code SHA and hashes of all
verification artifacts.

## Dual verification products

Produce both scan-level and event-level diagnostics.

Scan-level:
ROC AUC, PR AUC, Brier score, log loss, reliability, grouped uncertainty
intervals, false alarms, misses, and threshold diagnostics.

Event-level:
case detection fraction, null-window alert fraction, maximum/mean case
probability, and first diagnostic threshold crossing relative to documented
event onset when the required timestamps are available.

Neither diagnostic set should be interpreted as operational forecast skill until
the modern population is independently verified and its sampling process is
documented.

## Warning-era context

The NWS began developing Snow Squall Warning operations at Burlington in the
2019 era, making post-2019 warning products a useful independent provenance
stream. Warning products should be treated as one source of evidence, not as
a perfect substitute for radar/surface impact truth.

References:
- https://www.weather.gov/btv/research
- https://www.weather.gov/media/directives/010_pdfs/pd01005013curr.pdf
- https://www.weather.gov/news/220411_snow-squall
- https://www.weather.gov/safety/winter-snow-squall
