# Historical Viewer Publication

The historical viewer is generated from a validated archived-viewer smoke-test artifact and published to the repository's `gh-pages` branch.

## Current package

The current validated package contains the BTV20060224 / KCXX archived case, including reconstructed radar-object geometry, tracks, scan-by-scan navigation, and georeferenced Level-II reflectivity frames. The viewer remains explicitly research/pilot output and does not expose an operational probability.

## GitHub Pages

The repository integration used for Actions cannot create or configure the GitHub Pages site through the Pages API. The publication workflow therefore writes the validated site to `gh-pages`.

One-time repository setting:

1. Open **Settings → Pages** for the repository.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select branch **gh-pages** and folder **/(root)**.
4. Save.

After that setting is enabled, future successful archived-viewer smoke runs can republish the `gh-pages` branch automatically.

## Data flow

`Archived Viewer Smoke Test` → `archived-snow-squall-viewer-site` artifact → `Publish Snow Squall Historical Viewer` → `gh-pages`.

This keeps the published viewer decoupled from the large historical/model artifacts and prevents a growing archive from blocking the visualization surface.

## Model status

The viewer is intentionally not considered an operational model release. Case-held-out model evaluation and candidate release auditing remain dependent on a successful expansion feature artifact and refreshed candidate model bundle.
