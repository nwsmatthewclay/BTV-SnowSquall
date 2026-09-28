# Dataset Build Pipeline

## Goal

Build a living object-level dataset for a ProbSevere-like snow-squall nowcast. The fundamental row is one tracked radar object at one scan time. Predictors are restricted to information available at that scan; future observations are used only for labels.

## Pipeline

1. Download native Level II volumes for each case window.
2. Normalize radar fields and geography.
3. Detect candidate objects.
4. Track objects between scans.
5. Calculate structure and evolution features.
6. Match environmental data to the object.
7. Match ASOS/METAR truth and published event timing.
8. Generate 15/30/45/60-minute future-event targets.
9. Sample matched null objects from the same cool-season windows.
10. Write provenance for every row.

## Outputs

- data/training/object_scans.parquet
- data/training/sequences.parquet
- data/training/labels.parquet
- data/training/training_table.csv
- data/training/provenance.csv

Do not randomly split individual scans. Split by complete case/event to prevent adjacent scans from leaking across train and test.