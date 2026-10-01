"""Deterministic radar-object tracker with motion/shape-aware association.

The live viewer is fed by two independent radars, so identity quality matters:
a loose centroid-only gate can create track swaps and long "spaghetti" tails.
This tracker uses a predicted centroid, normalized position/size/intensity costs,
and a deliberately tight gate. State remains backward-compatible with the
earlier centroid tracker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import hypot, log1p

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class Track:
    object_id: int
    last_time: object
    row: float
    column: float
    age_scans: int = 1
    velocity_row: float = 0.0
    velocity_column: float = 0.0
    area_km2: float | None = None
    max_reflectivity_dbz: float | None = None
    missed_scans: int = 0


@dataclass(frozen=True)
class TrackerConfig:
    # Use both a physical speed gate and an absolute pixel cap. A fixed pixel
    # radius can be too permissive on fast scans and too restrictive on long gaps.
    max_pixel_distance: float = 18.0
    grid_spacing_km: float = 1.0
    max_motion_kt: float = 75.0
    min_gate_distance_km: float = 4.0
    max_time_gap_minutes: float = 10.0
    max_missed_scans: int = 1
    max_area_ratio: float = 16.0
    prediction_weight: float = 0.72
    size_weight: float = 0.16
    intensity_weight: float = 0.12


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

    def _dt_minutes(self, timestamp, previous):
        try:
            return max(0.1, (self._as_datetime(timestamp) - self._as_datetime(previous)).total_seconds() / 60.0)
        except (AttributeError, TypeError, ValueError):
            return 1.0

    def _prune_stale(self, timestamp):
        stale = [
            tid for tid, track in self.tracks.items()
            if self._minutes_since(timestamp, track.last_time) > self.config.max_time_gap_minutes
        ]
        for tid in stale:
            del self.tracks[tid]
        return stale

    @staticmethod
    def _area(obj):
        value = obj.get("area_km2", obj.get("pixel_count"))
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _z(obj):
        try:
            return float(obj.get("max_reflectivity_dbz"))
        except (TypeError, ValueError):
            return 0.0

    def _predicted_position(self, track, timestamp):
        dt = min(self.config.max_time_gap_minutes, self._dt_minutes(timestamp, track.last_time))
        return (
            track.row + track.velocity_row * dt,
            track.column + track.velocity_column * dt,
        )

    def _association_gate_pixels(self, timestamp, previous):
        dt = min(
            self.config.max_time_gap_minutes,
            max(0.1, self._dt_minutes(timestamp, previous)),
        )
        # 1 kt = 1.852 km/h; dt is in minutes.
        max_distance_km = max(
            self.config.min_gate_distance_km,
            self.config.max_motion_kt * 1.852 * (dt / 60.0),
        )
        return min(
            self.config.max_pixel_distance,
            max_distance_km / max(self.config.grid_spacing_km, 0.01),
        )

    def _cost(self, track, obj, timestamp):
        pred_row, pred_col = self._predicted_position(track, timestamp)
        distance = hypot(obj["row_centroid"] - pred_row, obj["column_centroid"] - pred_col)
        gate_pixels = self._association_gate_pixels(timestamp, track.last_time)

        # A track must remain within a physically plausible displacement window.
        if distance > gate_pixels:
            return np.inf

        track_area = max(1.0, float(track.area_km2 or 1.0))
        obj_area = max(1.0, self._area(obj))
        size_cost = abs(log1p(obj_area) - log1p(track_area)) / 3.0

        if track.max_reflectivity_dbz is None:
            intensity_cost = 0.0
        else:
            intensity_cost = min(1.0, abs(self._z(obj) - track.max_reflectivity_dbz) / 20.0)

        area_ratio = max(obj_area / track_area, track_area / obj_area)
        if area_ratio > self.config.max_area_ratio:
            return np.inf

        position_cost = distance / max(gate_pixels, 1e-6)
        return (
            self.config.prediction_weight * position_cost
            + self.config.size_weight * size_cost
            + self.config.intensity_weight * intensity_cost
        )

    def update(self, timestamp, objects):
        """Assign current detections to active tracks using global minimum cost."""
        self._prune_stale(timestamp)
        objects = list(objects)
        if not objects:
            return []

        track_ids = sorted(self.tracks)
        assignments = {}
        used = set()
        matched_track_ids = set()

        if track_ids:
            cost = np.full((len(track_ids), len(objects)), np.inf, dtype=float)
            for ti, tid in enumerate(track_ids):
                for oi, obj in enumerate(objects):
                    cost[ti, oi] = self._cost(self.tracks[tid], obj, timestamp)

            finite = np.isfinite(cost)
            if finite.any():
                # Hungarian assignment may use the large sentinel for invalid
                # cells; only accept genuinely finite, gated pairs afterwards.
                row_ind, col_ind = linear_sum_assignment(np.where(finite, cost, 1e6))
                for r, c in zip(row_ind, col_ind):
                    if np.isfinite(cost[r, c]):
                        assignments[int(c)] = track_ids[int(r)]
                        used.add(int(c))
                        matched_track_ids.add(track_ids[int(r)])

        for object_index, tid in assignments.items():
            obj = objects[object_index]
            track = self.tracks[tid]
            dt = self._dt_minutes(timestamp, track.last_time)
            measured_row = float(obj["row_centroid"])
            measured_col = float(obj["column_centroid"])
            new_vr = (measured_row - track.row) / dt
            new_vc = (measured_col - track.column) / dt
            # Exponential smoothing prevents a single noisy centroid from
            # producing an unrealistic next-scan jump.
            alpha = 0.55 if track.age_scans < 3 else 0.35
            track.velocity_row = (1 - alpha) * track.velocity_row + alpha * new_vr
            track.velocity_column = (1 - alpha) * track.velocity_column + alpha * new_vc
            track.last_time = timestamp
            track.row = measured_row
            track.column = measured_col
            track.age_scans += 1
            track.missed_scans = 0
            track.area_km2 = self._area(obj)
            track.max_reflectivity_dbz = self._z(obj)

        for tid, track in list(self.tracks.items()):
            if tid not in matched_track_ids and tid in self.tracks:
                track.missed_scans = getattr(track, "missed_scans", 0) + 1
                if track.missed_scans > self.config.max_missed_scans:
                    del self.tracks[tid]

        for object_index, obj in enumerate(objects):
            if object_index in used:
                continue
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = Track(
                tid,
                timestamp,
                float(obj["row_centroid"]),
                float(obj["column_centroid"]),
                area_km2=self._area(obj),
                max_reflectivity_dbz=self._z(obj),
            )
            assignments[object_index] = tid

        return [{"object_id": assignments[index], **obj} for index, obj in enumerate(objects)]

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
                    "velocity_row": track.velocity_row,
                    "velocity_column": track.velocity_column,
                    "area_km2": track.area_km2,
                    "max_reflectivity_dbz": track.max_reflectivity_dbz,
                    "missed_scans": getattr(track, "missed_scans", 0),
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
                velocity_row=float(raw.get("velocity_row", 0.0)),
                velocity_column=float(raw.get("velocity_column", 0.0)),
                area_km2=raw.get("area_km2"),
                max_reflectivity_dbz=raw.get("max_reflectivity_dbz"),
                missed_scans=int(raw.get("missed_scans", 0)),
            )
        return tracker
