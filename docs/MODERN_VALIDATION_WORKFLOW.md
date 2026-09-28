# Modern Independent Validation Workflow

The modern validation workflow is intentionally separate from the Banacos development population.

## Current candidate boundary

The file data/manifests/modern_independent_validation_cases.csv contains two provenance candidates.

- BTV20181121 is reconstruction-eligible because the WFO Burlington 2018-19 winter summary documents a significant snow squall event and provides Burlington visibility/wind observations plus time-stamped VTrans webcam evidence.
- BTV20191218 remains provenance-only. Its current evidence source is an NWS warning-policy example rather than a case-specific impact archive, so it is not yet eligible for independent reconstruction.

The 2018 reconstruction window is explicitly bounded and is not an event-truth label. It is centered on the documented VTrans webcam timestamps and the published timing of the squall threat.

## Workflow

.github/workflows/modern-independent-validation.yml performs:

1. Manifest and provenance QC.
2. Creation of an eligible Level-II acquisition manifest.
3. Archived KCXX/KTYX Level-II acquisition.
4. ASOS/METAR acquisition over the bounded analysis window.
5. Scan-by-scan replay through the same object processor used by the live path.
6. Archived MRMS lowest-elevation reflectivity acquisition where available.
7. A non-scoring validation inventory.

The workflow does not train models, choose thresholds, calibrate probabilities, or modify the development population.

## Independent boundary

Every validation artifact should retain the validation case ID, exact analysis-window bounds, source provenance, reconstruction eligibility, radar/surface/MRMS acquisition status, and verification code revision.

The inventory is evidence for an independent verification exercise, not a new training dataset.

## Scientific use

The first useful output is cross-sensor and event-level evidence:

- whether Level-II replay reconstructs a coherent object during the independently documented impact period;
- whether object timing and location agree with surface observations and independent imagery;
- whether MRMS provides consistent spatial reflectivity structure;
- whether discrepancies expose radar reconstruction or label weaknesses.

Model skill statistics should remain frozen until the independent sample is fully reconstructed and the verification population is documented.
