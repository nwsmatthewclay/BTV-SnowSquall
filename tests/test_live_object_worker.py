from datetime import datetime, timedelta, timezone

from scripts.live_object_worker import select_volumes


def _scans(count=6):
    start = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
    return [
        (f"scan-{i}", start + timedelta(minutes=5 * i))
        for i in range(1, count + 1)
    ]


def test_recovery_selects_newest_bounded_batch_in_chronological_order():
    scans = _scans(6)
    since = scans[0][1] - timedelta(minutes=5)

    selected = select_volumes(scans, since, max_volumes_per_run=2)

    assert selected == scans[-2:]
    assert selected[0][1] < selected[1][1]


def test_normal_operation_selects_oldest_unprocessed_batch():
    scans = _scans(2)
    since = scans[0][1] - timedelta(minutes=5)

    selected = select_volumes(scans, since, max_volumes_per_run=2)

    assert selected == scans


def test_fresh_state_seeds_history_with_newest_bounded_batch():
    scans = _scans(6)

    selected = select_volumes(scans, None, max_volumes_per_run=3)

    assert selected == scans[-3:]


def test_explicit_prefer_latest_remains_available_for_manual_latency_mode():
    scans = _scans(6)

    selected = select_volumes(scans, scans[0][1], max_volumes_per_run=3, prefer_latest=True)

    assert selected == [scans[-1]]
