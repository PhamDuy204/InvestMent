"""Point-in-time macro event primitives for V8 forward research."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

_SCHEMA_VERSION = "v8-macro-event-1"


def normalize_scheduled_macro_event(
    *,
    event_type: str,
    source: str,
    source_id: str,
    scheduled_at: datetime,
    first_seen_at: datetime,
    source_url: str,
    time_precision: str = "EXACT",
) -> dict[str, object]:
    if scheduled_at.tzinfo is None or first_seen_at.tzinfo is None:
        raise ValueError("macro timestamps must be timezone-aware")
    if time_precision not in {"EXACT", "DATE_ONLY"}:
        raise ValueError("time_precision must be EXACT or DATE_ONLY")
    scheduled = scheduled_at.astimezone(timezone.utc)
    first_seen = first_seen_at.astimezone(timezone.utc)
    raw = {
        "event_type": event_type,
        "scheduled_at": scheduled.isoformat(),
        "time_precision": time_precision,
        "source_url": source_url,
    }
    checksum = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "event_time": scheduled.isoformat(),
        "published_at": first_seen.isoformat(),
        "first_seen_at": first_seen.isoformat(),
        "available_at": first_seen.isoformat(),
        "decision_time": first_seen.isoformat(),
        "source": source,
        "source_id": source_id,
        "symbol": "global",
        "raw_value": json.dumps(raw, sort_keys=True),
        "derived_value": 1.0,
        "data_version": _SCHEMA_VERSION,
        "checksum": checksum,
        "event_type": event_type,
        "time_precision": time_precision,
        "source_url": source_url,
        "causal_status": "FORWARD_SCHEDULE_ONLY",
    }


def major_event_within_horizon(
    events: pd.DataFrame,
    *,
    decision_time: pd.Timestamp,
    horizon_hours: int = 12,
) -> bool:
    if horizon_hours <= 0:
        raise ValueError("horizon_hours must be positive")
    required = {"event_time", "available_at", "time_precision"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"missing macro event columns: {', '.join(sorted(missing))}")
    decision = pd.Timestamp(decision_time)
    decision = decision.tz_localize("UTC") if decision.tzinfo is None else decision.tz_convert("UTC")
    scheduled = pd.to_datetime(events["event_time"], utc=True, errors="raise")
    available = pd.to_datetime(events["available_at"], utc=True, errors="raise")
    end = decision + pd.Timedelta(hours=horizon_hours)
    eligible = (
        events["time_precision"].eq("EXACT")
        & available.le(decision)
        & scheduled.ge(decision)
        & scheduled.le(end)
    )
    return bool(eligible.any())
