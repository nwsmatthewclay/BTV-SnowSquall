"""Deterministic scan-to-scan association for geographic radar objects.
Inputs require a timestamp and geographic centroid. Original fields are preserved.
"""
from datetime import datetime, timezone
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from collections.abc import Mapping


def _timestamp(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError(f"Unsupported scan timestamp: {value!r}")
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _coordinates(detection):
    centroid = detection.get("centroid")
    if isinstance(centroid, Mapping):
        lat, lon = centroid.get("lat"), centroid.get("lon")
    else:
        lat = detection.get("centroid_lat", detection.get("lat"))
        lon = detection.get("centroid_lon", detection.get("lon"))
    if lat is None or lon is None:
        raise ValueError("Detection requires centroid_lat/centroid_lon, lat/lon, or centroid.lat/lon")
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Invalid geographic centroid: {(lat, lon)!r}")
    return lat, lon


def _distance_km(a, b):
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1.0, sqrt(h)))


class ObjectTracker:
    """Associate detections to persistent track IDs across consecutive scans."""

    def __init__(self, max_distance_km=30.0, max_time_gap_minutes=10, history_limit=24):
        if max_distance_km <= 0 or max_time_gap_minutes <= 0 or history_limit < 2:
            raise ValueError("Distance/time limits must be positive and history_limit >= 2")
        self.max_distance_km = float(max_distance_km)
        self.max_time_gap_minutes = float(max_time_gap_minutes)
        self.history_limit = int(history_limit)
        self._tracks = {}
        self._next_id = 1
        self._last_scan_time = None

    def reset(self):
        self._tracks.clear()
        self._next_id = 1
        self._last_scan_time = None

    def update(self, detections):
        detections = [dict(item) for item in detections]
        if not detections:
            return []
        prepared = []
        for item in detections:
            value = item.get("timestamp", item.get("scan_time", item.get("observed_at")))
            if value is None:
                raise ValueError("Each detection must include timestamp, scan_time, or observed_at")
            prepared.append((_timestamp(value), _coordinates(item), item))
        times = {row[0] for row in prepared}
        if len(times) != 1:
            raise ValueError("All detections in one update must share a scan timestamp")
        scan_time = next(iter(times))
        if self._last_scan_time is not None and scan_time <= self._last_scan_time:
            raise ValueError("Duplicate or out-of-order scan timestamp; tracker state unchanged")

        candidates = []
        for di, (_, coords, _) in enumerate(prepared):
            for track_id, track in self._tracks.items():
                previous = track["history"][-1]
                elapsed = (scan_time - previous["timestamp"]).total_seconds() / 60
                if elapsed <= 0 or elapsed > self.max_time_gap_minutes:
                    continue
                distance = _distance_km((previous["lat"], previous["lon"]), coords)
                if distance <= self.max_distance_km:
                    candidates.append((distance, track_id, di))
        candidates.sort()
        assigned_detections, assigned_tracks, associations = set(), set(), {}
        for distance, track_id, di in candidates:
            if di not in assigned_detections and track_id not in assigned_tracks:
                associations[di] = track_id
                assigned_detections.add(di)
                assigned_tracks.add(track_id)

        output = []
        for index, (when, (lat, lon), item) in enumerate(prepared):
            track_id = associations.get(index)
            if track_id is None:
                track_id = f"SSQ-{self._next_id:06d}"
                self._next_id += 1
                self._tracks[track_id] = {"history": []}
            history = self._tracks[track_id]["history"]
            prior = history[-1] if history else None
            speed, bearing = None, None
            if prior:
                hours = (when - prior["timestamp"]).total_seconds() / 3600
                distance = _distance_km((prior["lat"], prior["lon"]), (lat, lon))
                speed = distance / hours if hours > 0 else None
                p1, p2, dl = radians(prior["lat"]), radians(lat), radians(lon - prior["lon"])
                y = sin(dl) * cos(p2)
                x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
                bearing = (degrees(atan2(y, x)) + 360) % 360
            history.append({"timestamp": when, "lat": lat, "lon": lon})
            history[:] = history[-self.history_limit:]
            item["track_id"] = track_id
            item["track_history"] = [
                {"timestamp": p["timestamp"].isoformat().replace("+00:00", "Z"),
                 "lat": p["lat"], "lon": p["lon"]} for p in history
            ]
            item["motion_kmh"] = speed
            item["motion_bearing_deg"] = bearing
            output.append(item)
        self._last_scan_time = scan_time
        return output
