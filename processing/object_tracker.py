"""Simple deterministic centroid tracker for radar candidate objects."""
from __future__ import annotations
from dataclasses import dataclass
from math import hypot

@dataclass
class Track:
    track_id: int
    last_time: object
    row: float
    column: float
    age_scans: int = 1

@dataclass(frozen=True)
class TrackerConfig:
    max_pixel_distance: float = 35.0
    max_time_gap_minutes: float = 10.0

class CentroidTracker:
    def __init__(self, config=TrackerConfig()):
        self.config = config
        self.tracks = {}
        self.next_id = 1

    def update(self, timestamp, objects):
        assignments = []
        unused = set(self.tracks)
        for obj in objects:
            best = None
            best_distance = float("inf")
            for tid in unused:
                track = self.tracks[tid]
                distance = hypot(obj["row_centroid"] - track.row,
                                 obj["column_centroid"] - track.column)
                if distance < best_distance and distance <= self.config.max_pixel_distance:
                    best, best_distance = tid, distance
            if best is None:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = Track(tid, timestamp, obj["row_centroid"],
                                         obj["column_centroid"])
            else:
                tid = best
                unused.remove(tid)
                track = self.tracks[tid]
                track.last_time = timestamp
                track.row = obj["row_centroid"]
                track.column = obj["column_centroid"]
                track.age_scans += 1
            assignments.append((tid, obj))
        return [{"track_id": tid, **obj} for tid, obj in assignments]
