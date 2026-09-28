"""Provider interfaces for scientific data acquisition."""
from abc import ABC, abstractmethod

class Provider(ABC):
    @abstractmethod
    def load(self, case):
        raise NotImplementedError

class RadarProvider(Provider): pass
class EnvironmentProvider(Provider): pass
class MRMSProvider(Provider): pass
class SurfaceProvider(Provider): pass
