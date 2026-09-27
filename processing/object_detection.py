"""Initial radar-object detection interface.

The first implementation will be deliberately conservative: identify
contiguous precipitation/reflectivity objects, retain their geometry, and
leave scientific thresholds configurable rather than hard-coded.
"""
from dataclasses import dataclass

@dataclass
class DetectionConfig:
    reflectivity_threshold_dbz: float = 20.0
    min_area_km2: float = 4.0

def detect_objects(reflectivity, config=DetectionConfig()):
    raise NotImplementedError(
        "Connect the Py-ART/raster object detector here. The interface is fixed "
        "so tracking and feature extraction remain independent."
    )
