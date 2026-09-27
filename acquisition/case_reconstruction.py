"""Case reconstruction orchestrator.

Coordinates radar, environment, MRMS and surface-truth inputs without
coupling the ML layer to any single data provider.
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass
class CaseWindow:
    case_id: str
    start_utc: datetime
    end_utc: datetime
    latitude: float
    longitude: float

class CaseReconstructor:
    def __init__(self, radar_source, environment_source, mrms_source, surface_source):
        self.radar=radar_source
        self.environment=environment_source
        self.mrms=mrms_source
        self.surface=surface_source

    def reconstruct(self, case: CaseWindow):
        radar=self.radar.load(case)
        environment=self.environment.load(case)
        mrms=self.mrms.load(case)
        surface=self.surface.load(case)
        return {"case":case,"radar":radar,"environment":environment,"mrms":mrms,"surface":surface}
