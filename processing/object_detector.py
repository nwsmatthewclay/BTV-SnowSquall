"""2-D radar object detector for research-quality candidate generation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class ObjectDetectionConfig:
    threshold_dbz: float = 20.0
    core_threshold_dbz: float = 35.0
    min_pixels: int = 20
    connectivity: int = 2


def detect_reflectivity_objects(reflectivity, config=ObjectDetectionConfig()):
    """Detect contiguous candidate precipitation objects in a 2-D field.

    Every candidate retains its exact grid-cell footprint so downstream code can
    construct geographic polygons without inventing geometry around a centroid.
    """
    arr = np.asarray(reflectivity, dtype=float)
    mask = np.isfinite(arr) & (arr >= config.threshold_dbz)
    structure = ndimage.generate_binary_structure(2, config.connectivity)
    labels, count = ndimage.label(mask, structure=structure)

    objects = []
    for object_id in range(1, count + 1):
        yy, xx = np.where(labels == object_id)
        if len(xx) < config.min_pixels:
            continue

        values = arr[yy, xx]
        objects.append({
            "object_id": int(object_id),
            "pixel_count": int(len(xx)),
            "row_centroid": float(np.mean(yy)),
            "column_centroid": float(np.mean(xx)),
            "max_reflectivity_dbz": float(np.nanmax(values)),
            "mean_reflectivity_dbz": float(np.nanmean(values)),
            "core_pixel_count": int(np.sum(values >= config.core_threshold_dbz)),
            "row_indices": yy.tolist(),
            "column_indices": xx.tolist(),
        })
    return objects
