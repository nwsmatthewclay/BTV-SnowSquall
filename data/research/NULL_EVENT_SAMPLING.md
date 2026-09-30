# Null Event Sampling Strategy

Nulls are necessary to prevent the model from learning that winter radar activity itself means a snow squall. They must not be created by simply taking every period without a report.

## Evidence hierarchy

1. Strong null: radar/object reconstruction shows no target snow-squall object AND no nearby NWS/IEM/Storm Data evidence.
2. Research null: no target event in radar reconstruction, with supporting surface observations and no event evidence.
3. Candidate null: screened for nearby IEM LSRs but not yet radar-reviewed.
4. Contaminated/unknown: any indication of a possible event; exclude from negative training until reviewed.

## Sources

IEM LSRs are useful for screening but IEM explicitly describes its archive as incomplete and not official. NOAA NCEI Storm Events is a stronger independent event archive, but it records significant weather phenomena rather than every snow squall. Therefore absence from either source is never sufficient by itself to prove a null.

Use:
- IEM Local Storm Reports
- NCEI Storm Events Database
- NWS warning/VTEC history
- METAR/ASOS/AWOS present weather and visibility
- MPING where available
- radar/object reconstruction

## Sampling balance

Start the first experimental database around 200 reconstructed cases, but balance the populations deliberately rather than forcing a 1:1 ratio:
- science-based supervised positives: highest-evidence cases only;
- research positives/analogs: retained separately;
- hard negatives: winter convective/radar-active periods without the target outcome;
- strong nulls: quiet/background winter periods.

The ratio should be selected from the resulting case/track population and sensitivity analyses, not chosen solely for class balance.

## Temporal leakage protection

Null windows must be separated from documented events by a configurable exclusion buffer. Sampling must be based only on information available at the prediction time when the resulting rows become predictors.

## Promotion rule

A null candidate may enter negative training only after radar/object and evidence review. Otherwise it remains `null_candidate_pending_radar_review`.