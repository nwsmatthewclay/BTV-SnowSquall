from datetime import datetime, timezone

import pandas as pd

from scripts.build_historical_dataset import choose_case


def test_choose_case_uses_nearest_verified_onset():
    cases = pd.DataFrame([
        {
            "case_id": "A",
            "event_start_dt": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        },
        {
            "case_id": "B",
            "event_start_dt": datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        },
    ]).set_index("case_id")

    result = choose_case(datetime(2026, 1, 1, 0, 50, tzinfo=timezone.utc), cases)
    assert result[1] == "B"


def test_choose_case_rejects_distant_scan():
    cases = pd.DataFrame([
        {
            "case_id": "A",
            "event_start_dt": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        },
    ]).set_index("case_id")

    assert choose_case(datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc), cases) is None
