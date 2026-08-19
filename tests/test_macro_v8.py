from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from crypto_research.macro_v8 import (
    major_event_within_horizon,
    normalize_scheduled_macro_event,
)


def test_macro_event_flag_requires_calendar_to_be_seen_before_decision() -> None:
    decision = pd.Timestamp("2026-09-04T10:00:00Z")
    scheduled = datetime(2026, 9, 4, 12, 30, tzinfo=timezone.utc)
    early = normalize_scheduled_macro_event(
        event_type="NFP",
        source="BLS",
        source_id="bls-empsit-2026-09-04",
        scheduled_at=scheduled,
        first_seen_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
        source_url="https://www.bls.gov/schedule/news_release/empsit.htm",
    )
    late = dict(early)
    late["source_id"] = "late-copy"
    late["first_seen_at"] = "2026-09-04T11:00:00+00:00"
    late["available_at"] = "2026-09-04T11:00:00+00:00"

    assert major_event_within_horizon(pd.DataFrame([early]), decision_time=decision, horizon_hours=12)
    assert not major_event_within_horizon(pd.DataFrame([late]), decision_time=decision, horizon_hours=12)


def test_macro_date_only_event_is_not_used_as_precise_h12_flag() -> None:
    event = normalize_scheduled_macro_event(
        event_type="FOMC_MEETING",
        source="Federal Reserve",
        source_id="fomc-2026-09-16",
        scheduled_at=datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
        first_seen_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        time_precision="DATE_ONLY",
    )

    assert not major_event_within_horizon(
        pd.DataFrame([event]),
        decision_time=pd.Timestamp("2026-09-15T20:00:00Z"),
        horizon_hours=12,
    )
