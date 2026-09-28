"""Stable object-detection interface used by downstream snow-squall code.

The production implementation lives in object_detector.py. This module keeps a
small, dependency-light public interface so callers do not have to know the
implementation module.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from processing.object_detector import (
    ObjectDetectionConfig,
    detect_reflectivity_objects,
)


@dataclass(frozen=True)
class DetectionConfig:
    reflectivity_threshold_dbz: float = 20.0
    core_threshold_dbz: float = 35.0
    min_area_km2: float = 4.0
    spacing_km: float = 1.0
    connectivity: int = 2

    @property
    def min_pixels(self) -> int:
        return max(1, int(np.ceil(self.min_area_km2 / (self.spacing_km ** 2))))


def detect_objects(reflectivity, config: DetectionConfig | None = None):
    """Detect candidate reflectivity objects using the canonical implementation.

    Returns the same object dictionaries used by the tracking and feature
    layers. The detector remains a candidate generator; snow-squall truth is
    assigned later by the evidence/labeling pipeline.
    """
    cfg = config or DetectionConfig()
    impl = ObjectDetectionConfig(
        threshold_dbz=cfg.reflectivity_threshold_dbz,
        core_threshold_dbz=cfg.core_threshold_dbz,
        min_pixels=cfg.min_pixels,
        connectivity=cfg.connectivity,
    )
    return detect_reflectivity_objects(reflectivity, config=impl)
