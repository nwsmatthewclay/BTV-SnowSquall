"""Storm-object tracking interface."""
class ObjectTracker:
    def __init__(self, max_distance_km=30.0, max_time_gap_minutes=10):
        self.max_distance_km=max_distance_km
        self.max_time_gap_minutes=max_time_gap_minutes

    def update(self, detections):
        raise NotImplementedError("Implement spatial/temporal object association.")
