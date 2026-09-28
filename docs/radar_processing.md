# Radar reconstruction and object tracking

## Processing sequence

1. Read the native KCXX/KTYX Level-II volume.
2. Preserve the original volume and a manifest entry.
3. Resolve reflectivity, velocity, spectrum width, ZDR, RHOHV and KDP fields.
4. Generate a candidate precipitation-object mask.
5. Track candidates across consecutive scans.
6. Compute object geometry, intensity, vertical structure, dual-pol signatures and evolution.
7. Attach the nearest valid environmental analysis and MRMS context.
8. Apply the evidence-based label policy only after the observation window is complete.

The detector is intentionally permissive. Its job is to avoid missing candidate snow-squall structures. The supervised model later decides whether a tracked object is consistent with a snow squall.

## Important design rule

Do not collapse the radar volume to one scalar before feature extraction. Preserve sweep-level information so the dataset can represent vertical growth, low-level organization and changes in structure through time.
