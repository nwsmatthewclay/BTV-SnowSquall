# Snow Squall Beta Test

## Purpose

This beta is a research/pilot viewer and replay workflow for archived snow-squall cases. It is not an operational warning recommendation and it does not expose an operational probability product.

## Historical viewer smoke test

1. Open the historical viewer and select a case/radar pair.
2. Confirm the reconstructed Level-II reflectivity frame follows the timeline.
3. Click an object and verify the selected footprint, object diagnostics, environment panel, and scan-to-scan track table update together.
4. Move the timeline slider through several scans and confirm the selected object's diagnostics follow the current/prior scan consistently.
5. In **Learned-model verification**, confirm the four horizon rows (15/30/45/60 min) render as research diagnostics only.
6. In **Learned-model replay**, confirm out-of-fold probabilities appear only where a historical OOF prediction exists and remain explicitly labeled research-only.
7. Confirm the viewer never presents the candidate as an operational warning, threshold, or release decision.

## Candidate replay smoke test

Use **Replay Learned Snow Squall Candidate** with:

- Case: `BTV20060224`
- Radar: `KCXX`
- `max_scans`: leave at `0` for the full available case, or set a small value for a quick smoke test.

The workflow should preflight all four model bundles, replay scans chronologically through the live processor, isolate replay history to the selected case, and report the actual probability status from the generated scan metadata.

## Live-product and shadow-scoring check

The operational live object feed should continue to report:

- `probability_status: not_scored`
- no model version attached to the operational probability field
- healthy object/environment/geometry contract status when source data are available.

Separately, the **Live research shadow** may show candidate scores from the expanded model bundle. The shadow feed is published on `snow-squall-shadow-data` and is explicitly marked `candidate_only_not_operational`.

A candidate model artifact is not operationally enabled unless its metadata explicitly marks it as `operational_release_status: released`.

## Beta acceptance notes

Record viewer usability observations separately from scientific model performance. Report any mismatches in timeline synchronization, object selection, radar background, environment timing, units, or stale/empty data behavior with the case ID, radar site, and scan time.

Scientific performance should be evaluated from the grouped, case-held-out diagnostics and independent validation plan rather than from a single successful replay.
