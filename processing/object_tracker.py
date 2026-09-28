"""Deterministic one-to-one centroid tracker for radar candidate objects.

The tracker uses a global minimum-cost assignment for each scan rather than
greedy object-order matching. Tracks older than the configured time gap are
pruned before matching. This keeps identity assignment deterministic when
multiple candidate objects are near multiple active tracks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import hypot

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class Track:
    object_id: int
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

    def _as_datetime(self, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _minutes_since(self, timestamp, previous):
        try:
            t = self._as_datetime(timestamp)
            p = self._as_datetime(previous)
            return abs((t - p).total_seconds()) / 60.0
        except (AttributeError, TypeError, ValueError):
            return float("inf")

    def _prune_stale(self, timestamp):
        stale = [
            tid
            for tid, track in self.tracks.items()
            if self._minutes_since(timestamp, track.last_time)
            > self.config.max_time_gap_minutes
        ]
        for tid in stale:
            del self.tracks[tid]
        return stale

    def update(self, timestamp, objects):
        """Assign current objects to active tracks using global minimum cost."""
        self._prune_stale(timestamp)

        objects = list(objects)
        if not objects:
            return []

        track_ids = sorted(self.tracks)
        assignments = {}
        used_object_indices = set()

        if track_ids:
            cost = np.full(
                (len(track_ids), len(objects)),
                fill_value=np.inf,
                dtype=float,
            )
            for ti, tid in enumerate(track_ids):
                track = self.tracks[tid]
                for oi, obj in enumerate(objects):
                    distance = hypot(
                        obj["row_centroid"] - track.row,
                        obj["column_centroid"] - track.column,
                    )
                    if distance <= self.config.max_pixel_distance:
                        cost[ti, oi] = distance

            finite_rows = np.where(np.isfinite(cost).any(axis=1))[0]
            finite_cols = np.where(np.isfinite(cost).any(axis=0))[0]
            if len(finite_rows) and len(finite_cols):
                sub = cost[np.ix_(finite_rows, finite_cols)]
                row_ind, col_ind = linear_sum_assignment(
                    np.where(np.isfinite(sub), sub, 1e9)
                )
                for r, c in zip(row_ind, col_ind):
                    track_index = int(finite_rows[r])
                    object_index = int(finite_cols[c])
                    distance = cost[track_index, object_index]
                    if np.isfinite(distance) and distance <= self.config.max_pixel_distance:
                        assignments[object_index] = track_ids[track_index]
                        used_object_indices.add(object_index)

        # Matched tracks are updated first.
        for object_index, tid in assignments.items():
            obj = objects[object_index]
            track = self.tracks[tid]
            track.last_time = timestamp
            track.row = float(obj["row_centroid"])
            track.column = float(obj["column_centroid"])
            track.age_scans += 1

        # Unmatched objects start new tracks.
        for object_index, obj in enumerate(objects):
            if object_index in used_object_indices:
                continue
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = Track(
                tid,
                timestamp,
                float(obj["row_centroid"]),
                float(obj["column_centroid"]),
            )
            assignments[object_index] = tid

        # Return in the same order as the input objects.
        return [
            {"object_id": assignments[index], **obj}
            for index, obj in enumerate(objects)
        ]

    def to_state(self):
        return {
            "next_id": self.next_id,
            "tracks": {
                str(tid): {
                    "object_id": track.object_id,
                    "last_time": self._as_datetime(track.last_time).isoformat(),
                    "row": track.row,
                    "column": track.column,
                    "age_scans": track.age_scans,
                }
                for tid, track in self.tracks.items()
            },
        }

    @classmethod
    def from_state(cls, state, config=TrackerConfig()):
        tracker = cls(config=config)
        if not state:
            return tracker

        tracker.next_id = int(state.get("next_id", 1))
        for tid_text, raw in state.get("tracks", {}).items():
            tid = int(tid_text)
            tracker.tracks[tid] = Track(
                object_id=int(raw["object_id"]),
                last_time=raw["last_time"],
                row=float(raw["row"]),
                column=float(raw["column"]),
                age_scans=int(raw.get("age_scans", 1)),
            )
        return tracker
