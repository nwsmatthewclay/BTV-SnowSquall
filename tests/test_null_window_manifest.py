from datetime import timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_null_window_manifest import select_candidates


def test_select_candidates_is_reproducible():
    candidates = list(range(20))
    import random
    a = select_candidates(candidates, 5, random.Random(42))
    b = select_candidates(candidates, 5, random.Random(42))
    assert a == b
    assert len(a) == 5


def test_select_candidates_can_require_archive_coverage():
    candidates = list(range(10))
    import random
    covered = {1, 3, 7, 9}
    selected = select_candidates(
        candidates,
        3,
        random.Random(42),
        availability=lambda value: value in covered,
    )
    assert len(selected) == 3
    assert set(selected) <= covered
