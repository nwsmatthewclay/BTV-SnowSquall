# Radar Case Reconstruction

## Purpose

The first scientific reconstruction target is the 36-event Banacos et al. (2014) northern New York/Vermont snow-squall dataset. The paper identified candidate hourly/special surface observations and compared them with 2-km composite reflectivity; our reconstruction goes back to native WSR-88D Level-II so the training database can retain storm structure and evolution rather than only the published event summary.

NOAA's NEXRAD archive provides Level-II base and dual-polarization data, including reflectivity, velocity, spectrum width, ZDR, correlation coefficient and differential phase.

## Radar coverage

Every Banacos event occurs after the Level-II period of record begins for both KCXX and KTYX. KCXX Level-II begins 4 June 1997 and KTYX begins 10 June 1998. Therefore both sites are available for the complete 2001-02 through 2010-11 Banacos climatology.

We use:

- **KCXX** — primary radar for northern Vermont/Champlain Valley.
- **KTYX** — supplemental radar for northern New York and upper-level/structural information where KCXX coverage is affected by distance or terrain.

The two-radar approach is intentional. A single radar can make a shallow winter squall look artificially weak or vertically incomplete.

## Initial extraction window

Each event gets a reproducible three-and-a-half-hour reconstruction window:

- **T-90 min** through **T+120 min** relative to the published event start.
- Native Level-II volumes are retained.
- Missing scans are recorded rather than silently interpolated.
- Event start remains an observation/truth anchor, not a radar-derived label.

The manifest is `data/manifests/banacos_radar_windows.csv`.

## Processing sequence

1. Enumerate Level-II volumes in the case window.
2. Read native volumes with Py-ART.
3. Normalize field names and metadata.
4. Create quality/coverage masks.
5. Convert the lowest usable reflectivity scan to a common Cartesian grid.
6. Detect permissive precipitation candidates.
7. Track candidates from scan to scan.
8. Extract object geometry, intensity, vertical depth, velocity and dual-pol characteristics.
9. Calculate past-only temporal evolution features.
10. Attach environmental and surface observations at the scan timestamp.
11. Associate the tracked object with the independently documented event anchor.
12. Preserve all provenance and missing-data flags.

## Important modeling rule

The published event observation is allowed to establish truth timing, but no information occurring after a given radar scan may become a predictor for that scan. In particular, later visibility, later radar intensity, warning issuance, and post-event observations cannot leak into a pre-onset probability.

## First pilot

The first pilot should use a small, representative set of cases before scaling to all 36. Include:

- a non-hybrid case,
- a hybrid case,
- a very low-visibility case,
- a short-duration case,
- a longer-duration case.

The pilot's purpose is to verify the complete radar-to-object pipeline, not to train a production model.
