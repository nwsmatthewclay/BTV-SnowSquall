# Penn State 2024 Convective Snow Climatology

## Source

Schneider, K., Lombardo, K., Kumjian, M. R., and Bowley, K. (2024), *A Radar-Based 10-Year Climatology of Convective Snow Events in Central Pennsylvania*, Weather and Forecasting, 39(7), 965–994. DOI: 10.1175/WAF-D-23-0187.1.

Penn State Data Commons dataset DOI: 10.26208/9xj2-g003.

The study identified 159 convective-snow cases during November–April across ten cold seasons from November 2012 through April 2022 using KCCX WSR-88D Level-II radar, RAP analyses, and KUNV ASOS observations.

## Why this source matters

This is a high-value external research cohort because it provides a radar-first definition of convective snow and separates organizational modes rather than treating every winter precipitation event as a snow squall.

The five radar organization modes are:

- S1: frontal band approximately perpendicular to the mean wind; the mode most directly analogous to the classic non-lake-effect snow squall.
- S2: cellular convective snow.
- S3-A: multicellular convection approximately perpendicular to the mean wind.
- S3-B: multicellular convection approximately parallel to the mean wind.
- S4: streamer bands approximately parallel to the mean wind.

The paper reports that S1 is uncommon, while multicellular modes dominate the broader convective-snow population. Therefore the complete 159-case cohort MUST NOT be promoted wholesale to supervised-positive snow-squall truth.

## Intended use in BTV-SnowSquall

1. Research/representation cohort: retain all 159 cases as external convective-snow analogs.
2. Potential positive cohort: prioritize S1 cases for detailed reconstruction and independent evidence checks.
3. Mode-aware analysis: retain the S1/S2/S3-A/S3-B/S4 classification as a research label, never as an NWS warning truth label.
4. Independent validation: use the cohort to test whether BTV features generalize to a physically related but geographically separate radar climatology.
5. Feature design: use the paper's environmental findings to guide candidate predictors, especially lower-tropospheric instability, moisture, cloud-layer depth/RH, vertical shear, 925-hPa frontogenesis, differential vorticity advection, vertical motion, and synoptic trough structure.

## Case identification methodology

The study first screened RAP wet-bulb profiles and KUNV ASOS snowfall reports, then examined hourly KCCX lowest-elevation-angle reflectivity. Candidate convective-snow elements were based on less than 67% of the 100-km radar domain containing stratiform precipitation, 20-dBZ contours, element area between 50 and 25,000 km², and horizontal reflectivity gradient of at least 5 dB/km, followed by manual review.

Flagged scans were grouped into cases, with a new case after more than 12 hours without a flagged scan.

This methodology is useful as an external benchmark for our object detector and should not be copied into the live BTV score without regional validation.

## External data package

Penn State Data Commons provides the associated files, including snsq.nc, null.nc, reduced 100-km datasets, and a sample CSV. The Data Commons directory lists three ZIP archives totaling roughly 25.7 GB on disk, containing roughly 98 GB of uncompressed NetCDF data. The repository should acquire only the small case catalog and selectively reconstruct Level-II data rather than commit the bulk archive.

Penn State also provides a public case-list spreadsheet linked by the paper's Data Availability Statement. The acquisition script in this repository is designed to retrieve that public catalog without requiring private Google credentials.

## Provenance and labeling policy

source_study=PSU_SCHNEIDER_2024 identifies the research source.

research_mode stores the study's S1/S2/S3-A/S3-B/S4 classification when available.

verification_class=research_documented_cs is intentionally non-strong. A research-paper identification is evidence of convective snow, not automatically independent BTV snow-squall truth.

A case may become eligible for supervised training only after passing the repository's existing evidence gate, including surface timing and radar reconstruction requirements.

## Key scientific findings to carry into feature work

The study found statistically meaningful differences among convective-snow modes involving 500-hPa trough position, surface-based CAPE, unstable/cloud-layer depth, cloud-layer moisture, cloud-layer wind and shear, 925-hPa frontogenesis, differential vorticity advection, vertical motion, and 2-m thermodynamic state.

The BTV model should treat these as candidate physical predictors, not assumed causal thresholds. All predictors must remain current/past-only at scoring time.

## References

- Penn State Data Commons dataset DOI: https://doi.org/10.26208/9xj2-g003
- AMS article DOI: https://doi.org/10.1175/WAF-D-23-0187.1
- Public case-list spreadsheet is linked from the article's Data Availability Statement.