# Radar reconstruction and object detection

## Processing sequence

1. Read the native KCXX/KTYX Level-II volume and retain the complete volume.
2. Resolve reflectivity, radial velocity, spectrum width, ZDR, RHOHV and KDP fields.
3. Grid reflectivity on the common Cartesian BTV domain.
4. Grid each radar moment from the lowest sweep that actually contains finite data. This prevents base velocity from disappearing when the velocity moment is not populated on literal sweep 0.
5. Generate candidate precipitation objects from reflectivity structure.
6. Use collocated base radial velocity as a first-class object signal. Velocity cannot create a free-standing object from wind noise, but coherent velocity contrast/gradient can:
   - rescue modest-echo precipitation footprints,
   - preserve narrow coherent radar structures that morphology might otherwise remove,
   - contribute to deterministic candidate ranking,
   - provide object-level velocity statistics for machine-learning predictors.
7. Track candidates across consecutive scans using radar-derived storm motion as a diagnostic/evolution feature.
8. Compute object geometry, intensity, reflectivity structure, radial-velocity structure, dual-pol structure, native multi-elevation profile metrics and temporal evolution.
9. Attach the nearest valid environmental analysis and additional observational context.
10. Apply evidence-based future-outcome labels only after the observation window is complete.

## Base radial velocity methodology

The native Level-II velocity field is in m/s and is converted to knots for the common research schema. Every training object can carry both whole-scan base-velocity context and object-footprint velocity statistics:

- base_velocity_mean_kt
- base_velocity_std_kt
- base_velocity_p90_abs_kt
- base_velocity_valid_fraction
- velocity_mean_kt
- velocity_std_kt
- velocity_p90_abs_kt
- velocity_gradient_p90_ktkm
- velocity_background_kt
- velocity_contrast_kt
- velocity_support_fraction

The detector uses reflectivity as the precipitation anchor. Velocity evidence is only considered where at least 15 dBZ precipitation is present, so isolated radial-wind texture does not become a snow-squall object by itself. A velocity-supported patch must also meet the configured velocity contrast/gradient tests before it can rescue weak reflectivity.

## Display products

The live viewer publishes the same base radar moments used by the live processor. KCXX and KTYX base reflectivity and base radial velocity are retained as separate per-radar products. Reflectivity may be mosaicked; signed radial velocity is not directly max/min mosaicked because radial velocity is viewpoint-dependent.

## Important design rule

Do not collapse the radar volume to one scalar before feature extraction. Preserve sweep-level information so the dataset can represent low-level organization, vertical growth and changes in structure through time. Full 3-D volume gridding remains a later enhancement.
