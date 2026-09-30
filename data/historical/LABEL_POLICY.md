# Historical training label policy

## Positive benchmark

The 36 Banacos et al. (2014) events are treated as research-confirmed positives. Their event time is the first moderate snow report in Table 2. These labels are immutable except through a documented source correction.

## Modern warning era

NWS Snow Squall Warning records from the IEM VTEC archive are candidate operational labels. A warning record becomes a verified event only after linking its warning polygon/timing to radar and surface evidence.

## Candidate / negative set

Candidate cases and near misses are stored separately. A near miss is especially valuable when the environmental field or radar object looked favorable but the observed outcome did not meet the event definition.

## Anti-leakage rule

At replay time T, the model may use only information that would have existed by T. Do not use peak reflectivity, minimum visibility, later radar scans, final warning polygons, post-event temperature changes, or complete object tracks in a pre-event row.

## Evaluation

Use event-level holdouts, not random scan-level splits. All scans from a given storm episode must stay in the same fold to prevent temporal and spatial leakage.
