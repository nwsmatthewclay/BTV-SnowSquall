import unittest

from processing.tracking import ObjectTracker


class ObjectTrackerTests(unittest.TestCase):
    def test_track_identity_and_history_follow_moving_object(self):
        tracker = ObjectTracker(max_distance_km=30, max_time_gap_minutes=10)
        first = tracker.update([{
            "timestamp": "2026-01-01T00:00:00Z", "centroid_lat": 44.5,
            "centroid_lon": -73.2, "area_km2": 12,
        }])[0]
        second = tracker.update([{
            "timestamp": "2026-01-01T00:05:00Z", "centroid_lat": 44.51,
            "centroid_lon": -73.2, "area_km2": 14,
        }])[0]
        self.assertEqual(first["track_id"], second["track_id"])
        self.assertEqual(len(second["track_history"]), 2)
        self.assertNotEqual(second["track_history"][0]["lat"], second["track_history"][1]["lat"])
        self.assertGreater(second["motion_kmh"], 0)
        self.assertAlmostEqual(second["motion_bearing_deg"], 0, delta=10)
        self.assertEqual(second["area_km2"], 14)

    def test_two_objects_get_distinct_tracks(self):
        tracker = ObjectTracker(max_distance_km=20)
        first = tracker.update([
            {"timestamp": "2026-01-01T00:00:00Z", "lat": 44.5, "lon": -73.2},
            {"timestamp": "2026-01-01T00:00:00Z", "lat": 45.0, "lon": -74.0},
        ])
        second = tracker.update([
            {"timestamp": "2026-01-01T00:05:00Z", "lat": 44.51, "lon": -73.2},
            {"timestamp": "2026-01-01T00:05:00Z", "lat": 45.01, "lon": -74.0},
        ])
        self.assertEqual({x["track_id"] for x in first}, {x["track_id"] for x in second})
        self.assertEqual(len({x["track_id"] for x in second}), 2)

    def test_out_of_order_scan_does_not_rewind_state(self):
        tracker = ObjectTracker()
        tracker.update([{"timestamp": "2026-01-01T00:05:00Z", "lat": 44.5, "lon": -73.2}])
        with self.assertRaises(ValueError):
            tracker.update([{"timestamp": "2026-01-01T00:00:00Z", "lat": 44.4, "lon": -73.2}])
        result = tracker.update([{"timestamp": "2026-01-01T00:10:00Z", "lat": 44.51, "lon": -73.2}])[0]
        self.assertEqual(len(result["track_history"]), 2)
        self.assertEqual(result["track_history"][-1]["lat"], 44.51)

    def test_gap_or_distance_starts_new_track(self):
        tracker = ObjectTracker(max_distance_km=5, max_time_gap_minutes=10)
        a = tracker.update([{"timestamp": "2026-01-01T00:00:00Z", "lat": 44.5, "lon": -73.2}])[0]
        b = tracker.update([{"timestamp": "2026-01-01T00:20:00Z", "lat": 44.51, "lon": -73.2}])[0]
        self.assertNotEqual(a["track_id"], b["track_id"])


if __name__ == "__main__":
    unittest.main()
