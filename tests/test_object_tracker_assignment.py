from processing.object_tracker import CentroidTracker, TrackerConfig

def make_obj(row, column):
    return {"row_centroid": row, "column_centroid": column}

def run(order):
    tracker = CentroidTracker(TrackerConfig(max_pixel_distance=10))
    first = tracker.update("2026-09-28T12:00:00Z", [
        make_obj(0, 0), make_obj(10, 0)
    ])
    ids = {tuple((x["row_centroid"], x["column_centroid"])): x["object_id"] for x in first}
    second_objs = [make_obj(*p) for p in order]
    second = tracker.update("2026-09-28T12:05:00Z", second_objs)
    return {tuple((x["row_centroid"], x["column_centroid"])): x["object_id"] for x in second}, ids

def test_assignment_is_independent_of_current_object_order():
    a, first_a = run([(1, 0), (9, 0)])
    b, first_b = run([(9, 0), (1, 0)])
    assert a == b
    assert a[(1.0, 0.0)] == first_a[(0.0, 0.0)]
    assert a[(9.0, 0.0)] == first_a[(10.0, 0.0)]

def test_two_nearby_objects_receive_distinct_track_ids():
    tracker = CentroidTracker(TrackerConfig(max_pixel_distance=10))
    first = tracker.update("2026-09-28T12:00:00Z", [
        make_obj(0, 0), make_obj(10, 0)
    ])
    second = tracker.update("2026-09-28T12:05:00Z", [
        make_obj(4, 0), make_obj(6, 0)
    ])
    ids = [x["object_id"] for x in second]
    assert len(set(ids)) == 2
