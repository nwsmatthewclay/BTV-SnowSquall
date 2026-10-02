"""Deterministic radar-object tracker with motion-aware association diagnostics.

The tracker is deliberately conservative: a candidate must satisfy a physical
distance gate and a morphology/intensity consistency gate before Hungarian
assignment is allowed. Radar-derived bulk motion is used as a prior, never as
a substitute for the observed object displacement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp, hypot, log1p

import numpy as np
from scipy.optimize import linear_sum_assignment


KM_PER_MIN_TO_KT = 60.0 / 1.852


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
    max_pixel_distance: float = 18.0
    grid_spacing_km: float = 1.0
    max_motion_kt: float = 75.0
    min_gate_distance_km: float = 4.0
    max_time_gap_minutes: float = 10.0
    max_missed_scans: int = 1
    max_area_ratio: float = 16.0
    max_association_cost: float = 0.92

    # Association cost weights. Position remains dominant, while velocity
    # consistency helps stop nearby objects from swapping identities.
    prediction_weight: float = 0.60
    size_weight: float = 0.10
    intensity_weight: float = 0.08
    velocity_weight: float = 0.12
    radar_motion_cost_weight: float = 0.10

    # Radar motion is trusted more when correlation confidence is high.
    radar_motion_weight: float = 0.30
    radar_velocity_scale_kt: float = 50.0
    velocity_mismatch_scale_kt: float = 45.0

    # Ambiguity diagnostics are intentionally recorded instead of silently
    # deleting difficult cases. The downstream quality gate decides whether a
    # track is suitable for training.
    ambiguous_margin: float = 0.12


class CentroidTracker:
    def __init__(self, config=TrackerConfig()):
        self.config = config
        self.tracks: dict[int, Track] = {}
        self.next_id = 1

    @staticmethod
    def _as_datetime(value):
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _minutes_since(self, timestamp, previous):
        try:
            return abs(
                (
                    self._as_datetime(timestamp)
                    - self._as_datetime(previous)
                ).total_seconds()
            ) / 60.0
        except (AttributeError, TypeError, ValueError):
            return float("inf")

    def _dt_minutes(self, timestamp, previous):
        try:
            return max(
                0.1,
                (
                    self._as_datetime(timestamp)
                    - self._as_datetime(previous)
                ).total_seconds()
                / 60.0,
            )
        except (AttributeError, TypeError, ValueError):
            return 1.0

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

    @staticmethod
    def _area(obj):
        try:
            value = obj.get("area_km2", obj.get("pixel_count"))
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _z(obj):
        try:
            return float(obj.get("max_reflectivity_dbz"))
        except (TypeError, ValueError):
            return 0.0

    def _radar_velocity(self, radar_motion):
        if not radar_motion:
            return None
        try:
            confidence = float(
                radar_motion.get("radar_motion_confidence", 0.0)
            )
            vr = float(radar_motion.get("radar_motion_row_per_min"))
            vc = float(radar_motion.get("radar_motion_column_per_min"))
        except (TypeError, ValueError):
            return None

        values = np.asarray([confidence, vr, vc], dtype=float)
        if not np.all(np.isfinite(values)) or confidence <= 0:
            return None

        confidence = float(np.clip(confidence, 0.0, 1.0))
        speed_kt = hypot(vr, vc) * self.config.grid_spacing_km * KM_PER_MIN_TO_KT
        if speed_kt > self.config.max_motion_kt:
            return None

        return vr, vc, confidence

    def _predicted_position(self, track, timestamp, radar_motion=None):
        dt = min(
            self.config.max_time_gap_minutes,
            self._dt_minutes(timestamp, track.last_time),
        )
        vr, vc = track.velocity_row, track.velocity_column

        radar_velocity = self._radar_velocity(radar_motion)
        if radar_velocity is not None:
            radar_vr, radar_vc, confidence = radar_velocity
            weight = self.config.radar_motion_weight * confidence
            vr = (1.0 - weight) * vr + weight * radar_vr
            vc = (1.0 - weight) * vc + weight * radar_vc

        return track.row + vr * dt, track.column + vc * dt

    def _association_gate_pixels(self, timestamp, previous):
        dt = min(
            self.config.max_time_gap_minutes,
            max(0.1, self._dt_minutes(timestamp, previous)),
        )
        max_distance_km = max(
            self.config.min_gate_distance_km,
            self.config.max_motion_kt * 1.852 * (dt / 60.0),
        )
        return min(
            self.config.max_pixel_distance,
            max_distance_km / max(self.config.grid_spacing_km, 0.01),
        )

    def _observed_velocity(self, track, obj, timestamp):
        dt = self._dt_minutes(timestamp, track.last_time)
        vr = (float(obj["row_centroid"]) - track.row) / dt
        vc = (float(obj["column_centroid"]) - track.column) / dt
        return vr, vc

    def _velocity_mismatch_kt(self, track, obj, timestamp):
        observed_vr, observed_vc = self._observed_velocity(track, obj, timestamp)
        delta = hypot(
            observed_vr - track.velocity_row,
            observed_vc - track.velocity_column,
        )
        return delta * self.config.grid_spacing_km * KM_PER_MIN_TO_KT

    def _radar_mismatch_kt(self, obj, radar_motion):
        if radar_motion is None:
            return None
        radar_velocity = self._radar_velocity(radar_motion)
        if radar_velocity is None:
            return None
        radar_vr, radar_vc, _ = radar_velocity
        observed_vr, observed_vc = (
            float(obj.get("_observed_velocity_row_per_min", 0.0)),
            float(obj.get("_observed_velocity_column_per_min", 0.0)),
        )
        delta = hypot(observed_vr - radar_vr, observed_vc - radar_vc)
        return delta * self.config.grid_spacing_km * KM_PER_MIN_TO_KT

    def _cost(self, track, obj, timestamp, radar_motion=None):
        pred_row, pred_col = self._predicted_position(
            track, timestamp, radar_motion
        )
        distance = hypot(
            float(obj["row_centroid"]) - pred_row,
            float(obj["column_centroid"]) - pred_col,
        )
        gate_pixels = self._association_gate_pixels(
            timestamp, track.last_time
        )
        if distance > gate_pixels:
            return np.inf

        track_area = max(1.0, float(track.area_km2 or 1.0))
        obj_area = max(1.0, self._area(obj))
        size_cost = min(
            1.0,
            abs(log1p(obj_area) - log1p(track_area)) / 3.0,
        )

        intensity_cost = 0.0
        if track.max_reflectivity_dbz is not None:
            intensity_cost = min(
                1.0,
                abs(self._z(obj) - track.max_reflectivity_dbz) / 20.0,
            )

        area_ratio = max(obj_area / track_area, track_area / obj_area)
        if area_ratio > self.config.max_area_ratio:
            return np.inf

        position_cost = distance / max(gate_pixels, 1e-6)

        # For the first possible match, the stored velocity is only a radar
        # prior (or zero), so velocity consistency is deliberately disabled.
        velocity_cost = 0.0
        active_weights = (
            self.config.prediction_weight
            + self.config.size_weight
            + self.config.intensity_weight
        )
        if track.age_scans >= 2:
            velocity_mismatch = self._velocity_mismatch_kt(
                track, obj, timestamp
            )
            velocity_cost = min(
                1.0,
                velocity_mismatch / self.config.velocity_mismatch_scale_kt,
            )
            active_weights += self.config.velocity_weight

        radar_cost = 0.0
        radar_velocity = self._radar_velocity(radar_motion)
        if radar_velocity is not None and track.age_scans >= 2:
            observed_vr, observed_vc = self._observed_velocity(
                track, obj, timestamp
            )
            obj["_observed_velocity_row_per_min"] = observed_vr
            obj["_observed_velocity_column_per_min"] = observed_vc
            radar_vr, radar_vc, radar_confidence = radar_velocity
            radar_mismatch = (
                hypot(observed_vr - radar_vr, observed_vc - radar_vc)
                * self.config.grid_spacing_km
                * KM_PER_MIN_TO_KT
            )
            radar_cost = min(
                1.0,
                radar_mismatch / self.config.radar_velocity_scale_kt,
            )
            active_weights += (
                self.config.radar_motion_cost_weight * radar_confidence
            )

        weighted = (
            self.config.prediction_weight * position_cost
            + self.config.size_weight * size_cost
            + self.config.intensity_weight * intensity_cost
            + self.config.velocity_weight * velocity_cost
            + self.config.radar_motion_cost_weight
            * (
                radar_cost
                * (
                    radar_velocity[2]
                    if radar_velocity is not None
                    else 0.0
                )
            )
        )
        normalized = weighted / max(active_weights, 1e-6)
        return float(normalized)

    def _candidate_matrix(
        self, track_ids, objects, timestamp, radar_motion=None
    ):
        cost = np.full(
            (len(track_ids), len(objects)),
            np.inf,
            dtype=float,
        )
        for ti, tid in enumerate(track_ids):
            for oi, obj in enumerate(objects):
                cost[ti, oi] = self._cost(
                    self.tracks[tid],
                    obj,
                    timestamp,
                    radar_motion,
                )
        return cost

    @staticmethod
    def _candidate_stats(cost):
        object_counts = np.sum(np.isfinite(cost), axis=0).astype(int)
        track_counts = np.sum(np.isfinite(cost), axis=1).astype(int)
        return object_counts, track_counts

    def _association_confidence(self, chosen_cost, alternatives, chosen_index=None):
        finite = [
            float(value)
            for i, value in enumerate(np.asarray(alternatives).ravel())
            if np.isfinite(value) and (chosen_index is None or i != chosen_index)
        ]
        second = min(finite) if finite else None
        margin = (
            float(second - chosen_cost)
            if second is not None
            else 1.0
        )
        margin_score = (
            1.0
            if second is None
            else float(
                np.clip(
                    margin / max(self.config.ambiguous_margin * 4.0, 0.05),
                    0.0,
                    1.0,
                )
            )
        )
        fit_score = float(np.clip(exp(-max(chosen_cost, 0.0)), 0.0, 1.0))
        confidence = 0.65 * fit_score + 0.35 * margin_score
        return confidence, margin

    def update(self, timestamp, objects, radar_motion=None):
        self._prune_stale(timestamp)
        objects = list(objects)
        if not objects:
            return []

        track_ids = sorted(self.tracks)
        assignments: dict[int, int] = {}
        used: set[int] = set()
        matched_track_ids: set[int] = set()

        candidate_counts = np.zeros(len(objects), dtype=int)
        candidate_track_counts = (
            np.zeros(len(track_ids), dtype=int)
            if track_ids
            else np.zeros(0, dtype=int)
        )

        cost = (
            self._candidate_matrix(
                track_ids, objects, timestamp, radar_motion
            )
            if track_ids
            else np.empty((0, len(objects)))
        )

        if track_ids:
            (
                candidate_counts,
                candidate_track_counts,
            ) = self._candidate_stats(cost)
            finite = np.isfinite(cost)
            if finite.any():
                rows, cols = linear_sum_assignment(
                    np.where(finite, cost, 1e6)
                )
                for row_index, column_index in zip(rows, cols):
                    value = cost[row_index, column_index]
                    if not np.isfinite(value):
                        continue
                    if value > self.config.max_association_cost:
                        continue
                    assignments[int(column_index)] = track_ids[
                        int(row_index)
                    ]
                    used.add(int(column_index))
                    matched_track_ids.add(track_ids[int(row_index)])

        for object_index, tid in assignments.items():
            obj = objects[object_index]
            track = self.tracks[tid]
            dt = self._dt_minutes(timestamp, track.last_time)
            old_row, old_col = track.row, track.column
            measured_row = float(obj["row_centroid"])
            measured_col = float(obj["column_centroid"])

            association_distance = hypot(
                measured_row - old_row,
                measured_col - old_col,
            )
            gate = self._association_gate_pixels(
                timestamp, track.last_time
            )
            cost_value = float(cost[track_ids.index(tid), object_index])

            observed_vr = (measured_row - old_row) / dt
            observed_vc = (measured_col - old_col) / dt
            velocity_mismatch = hypot(
                observed_vr - track.velocity_row,
                observed_vc - track.velocity_column,
            ) * self.config.grid_spacing_km * KM_PER_MIN_TO_KT

            alpha = 0.55 if track.age_scans < 3 else 0.35
            measured_track_vr = (
                (1.0 - alpha) * track.velocity_row
                + alpha * observed_vr
            )
            measured_track_vc = (
                (1.0 - alpha) * track.velocity_column
                + alpha * observed_vc
            )

            radar_velocity = self._radar_velocity(radar_motion)
            if radar_velocity is not None:
                radar_vr, radar_vc, radar_conf = radar_velocity
                motion_weight = (
                    self.config.radar_motion_weight * radar_conf
                )
                track.velocity_row = (
                    (1.0 - motion_weight) * measured_track_vr
                    + motion_weight * radar_vr
                )
                track.velocity_column = (
                    (1.0 - motion_weight) * measured_track_vc
                    + motion_weight * radar_vc
                )
                obj["track_motion_source"] = "object_radar_blend"
                obj["track_motion_radar_weight"] = float(motion_weight)
            else:
                track.velocity_row = measured_track_vr
                track.velocity_column = measured_track_vc
                obj["track_motion_source"] = "object_only"
                obj["track_motion_radar_weight"] = 0.0

            alternatives = (
                cost[:, object_index]
                if cost.size
                else np.asarray([])
            )
            confidence, margin = self._association_confidence(
                cost_value,
                alternatives,
                chosen_index=track_ids.index(tid),
            )
            object_competition = int(candidate_counts[object_index])
            track_competition = int(
                candidate_track_counts[track_ids.index(tid)]
            )

            recovered = int(track.missed_scans)
            track.last_time = timestamp
            track.row = measured_row
            track.column = measured_col
            track.age_scans += 1
            track.missed_scans = 0
            track.area_km2 = self._area(obj)
            track.max_reflectivity_dbz = self._z(obj)

            obj["track_association_status"] = (
                "recovered_after_gap" if recovered else "matched"
            )
            obj["track_competing_track_count"] = object_competition
            obj["track_competing_object_count"] = track_competition
            obj["track_merge_candidate"] = object_competition > 1
            obj["track_split_candidate"] = track_competition > 1
            obj["track_association_distance_px"] = float(
                association_distance
            )
            obj["track_association_gate_px"] = float(gate)
            obj["track_association_cost"] = cost_value
            obj["track_association_normalized_distance"] = float(
                association_distance / max(gate, 1e-6)
            )
            obj["track_association_margin"] = float(margin)
            obj["track_association_confidence"] = float(confidence)
            obj["track_association_ambiguous"] = bool(
                object_competition > 1
                and margin < self.config.ambiguous_margin
            )
            obj["track_velocity_mismatch_kt"] = float(velocity_mismatch)
            obj["track_time_since_previous_min"] = float(dt)
            obj["track_gap_recovered"] = bool(recovered > 0)
            obj["track_age_scans"] = int(track.age_scans)
            obj["track_missed_scans"] = 0
            obj["track_velocity_row_per_min"] = float(
                track.velocity_row
            )
            obj["track_velocity_column_per_min"] = float(
                track.velocity_column
            )

            if radar_velocity is not None:
                radar_vr, radar_vc, _ = radar_velocity
                obj["track_radar_motion_mismatch_kt"] = float(
                    hypot(
                        observed_vr - radar_vr,
                        observed_vc - radar_vc,
                    )
                    * self.config.grid_spacing_km
                    * KM_PER_MIN_TO_KT
                )
            else:
                obj["track_radar_motion_mismatch_kt"] = np.nan

            if radar_motion:
                obj["radar_motion_speed_kt"] = radar_motion.get(
                    "radar_motion_speed_kt"
                )
                obj["radar_motion_direction_deg"] = radar_motion.get(
                    "radar_motion_direction_deg"
                )
                obj["radar_motion_confidence"] = radar_motion.get(
                    "radar_motion_confidence"
                )

        for tid, track in list(self.tracks.items()):
            if tid not in matched_track_ids:
                track.missed_scans += 1
                if track.missed_scans > self.config.max_missed_scans:
                    del self.tracks[tid]

        for oi, obj in enumerate(objects):
            if oi in used:
                continue

            tid = self.next_id
            self.next_id += 1

            initial_vr = 0.0
            initial_vc = 0.0
            radar_velocity = self._radar_velocity(radar_motion)
            if radar_velocity is not None:
                initial_vr, initial_vc, _ = radar_velocity
                motion_source = "radar_prior"
                radar_weight = 1.0
            else:
                motion_source = "object_only"
                radar_weight = 0.0

            self.tracks[tid] = Track(
                tid,
                timestamp,
                float(obj["row_centroid"]),
                float(obj["column_centroid"]),
                velocity_row=initial_vr,
                velocity_column=initial_vc,
                area_km2=self._area(obj),
                max_reflectivity_dbz=self._z(obj),
            )

            obj["track_association_status"] = "new"
            obj["track_association_distance_px"] = np.nan
            obj["track_association_gate_px"] = np.nan
            obj["track_association_cost"] = np.nan
            obj["track_association_normalized_distance"] = np.nan
            obj["track_association_margin"] = np.nan
            obj["track_association_confidence"] = 0.45
            obj["track_association_ambiguous"] = False
            obj["track_velocity_mismatch_kt"] = np.nan
            obj["track_radar_motion_mismatch_kt"] = np.nan
            obj["track_time_since_previous_min"] = np.nan
            obj["track_gap_recovered"] = False
            obj["track_age_scans"] = 1
            obj["track_missed_scans"] = 0
            obj["track_motion_source"] = motion_source
            obj["track_motion_radar_weight"] = float(radar_weight)
            obj["track_velocity_row_per_min"] = float(initial_vr)
            obj["track_velocity_column_per_min"] = float(initial_vc)
            obj["track_competing_track_count"] = (
                int(candidate_counts[oi])
                if oi < len(candidate_counts)
                else 0
            )
            obj["track_competing_object_count"] = 0
            obj["track_merge_candidate"] = (
                obj["track_competing_track_count"] > 1
            )
            obj["track_split_candidate"] = False
            if radar_motion:
                obj["radar_motion_speed_kt"] = radar_motion.get(
                    "radar_motion_speed_kt"
                )
                obj["radar_motion_direction_deg"] = radar_motion.get(
                    "radar_motion_direction_deg"
                )
                obj["radar_motion_confidence"] = radar_motion.get(
                    "radar_motion_confidence"
                )
            assignments[oi] = tid

        for obj in objects:
            obj.pop("_observed_velocity_row_per_min", None)
            obj.pop("_observed_velocity_column_per_min", None)

        return [
            {"object_id": assignments[i], **obj}
            for i, obj in enumerate(objects)
        ]

    def to_state(self):
        return {
            "next_id": self.next_id,
            "tracks": {
                str(tid): {
                    "object_id": track.object_id,
                    "last_time": self._as_datetime(
                        track.last_time
                    ).isoformat(),
                    "row": track.row,
                    "column": track.column,
                    "age_scans": track.age_scans,
                    "velocity_row": track.velocity_row,
                    "velocity_column": track.velocity_column,
                    "area_km2": track.area_km2,
                    "max_reflectivity_dbz": track.max_reflectivity_dbz,
                    "missed_scans": track.missed_scans,
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
