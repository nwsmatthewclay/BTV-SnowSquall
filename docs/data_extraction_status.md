# Data Extraction Status

## Verified and extracted

### Banacos et al. (2014)
- 36 event records extracted from published Table 2.
- Raw ASOS wind group preserved alongside derived peak gust.
- Observing stations: KBTV, KMPV, KMSS.
- Event start time, visibility, visibility-duration fields, temperatures, hybrid flag, and peak wind are retained.
- Published methodology states that candidate METAR hourly/special observations were compared against 2-km composite reflectivity to identify narrow convective bands.
- The study also used NARR environmental data and a 2005-06 winter control dataset.

### Southern New England (Colby et al. 2022)
- 100-event population metadata extracted: 72 Classic, 15 Atlantic, 9 Northern, 4 Special.
- Domain and event definition recorded.
- Methodology confirms METAR, NEXRAD Level II, radar cell tracking, WPC analyses, and hourly ERA5.
- Exact 100 case dates are deliberately not populated yet; they must be extracted from the authors' underlying event catalog or machine-readable supplementary data rather than inferred from figures.

## Native radar reconstruction now staged

- 36 Banacos events have reproducible T-90 to T+120 minute radar windows for both KCXX and KTYX.
- `data/manifests/banacos_radar_windows.csv` contains 72 acquisition rows.
- `acquisition/historical_level2.py` targets the public `unidata-nexrad-level2` archive without requiring an AWS account.
- `data/manifests/banacos_pilot_cases.csv` defines five representative cases for the first end-to-end radar/object reconstruction.
- KCXX and KTYX Level-II archives cover the full Banacos period.

## Next extraction

1. Download and inspect the five pilot cases before scaling to all 36.
2. Acquire ASOS/METAR observations around each case.
3. Reconstruct radar object tracks.
4. Match NARR/ERA5/RAP environmental fields.
5. Build null-object population from control periods.
6. Extract the 100 Southern New England event dates and radar windows.


## Current pilot hardening

The end-to-end pilot now audits manifest identity, object-to-population annotation,
radar reconstruction failures, outcome-label integrity, predictor leakage, and
case/window-held-out model validation.

Historical Level-II reconstruction uses the existing Py-ART reader first and
falls back to the xradar NEXRAD Level-II reader when the legacy reader fails.
Each successfully decoded volume is tagged with its reader backend, while files
that fail both paths remain in an explicit error log. This makes recovery gains
measurable rather than silently changing the historical sample.

The five-case pilot is still a research dataset, not a final truth set. Candidate
null windows require additional event/radar QC before they become definitive
negative training examples.
