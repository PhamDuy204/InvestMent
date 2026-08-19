"""Minimal causal point-in-time contract shared by V8 feature sources."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

_REQUIRED = (
    "event_time",
    "published_at",
    "first_seen_at",
    "available_at",
    "decision_time",
    "source",
    "source_id",
    "symbol",
    "raw_value",
    "derived_value",
    "data_version",
    "checksum",
)
_TIME_COLUMNS = ("event_time", "published_at", "first_seen_at", "available_at", "decision_time")


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing point-in-time columns: {', '.join(missing)}")


def _normalized(frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(frame, _REQUIRED)
    out = frame.copy()
    for column in _TIME_COLUMNS:
        out[column] = pd.to_datetime(out[column], utc=True, errors="raise")
    return out


def validate_point_in_time_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the causal contract and return a UTC-normalized copy."""
    out = _normalized(frame)
    late = out["available_at"] > out["decision_time"]
    if bool(late.any()):
        raise ValueError("available_at must be <= decision_time for causal backtest rows")
    return out


def causal_events_for_decision(
    frame: pd.DataFrame,
    *,
    decision_time: pd.Timestamp,
    symbol: str | None = None,
) -> pd.DataFrame:
    """Return only observations actually available at one historical decision."""
    out = _normalized(frame)
    decision = pd.Timestamp(decision_time)
    decision = decision.tz_localize("UTC") if decision.tzinfo is None else decision.tz_convert("UTC")
    mask = out["available_at"] <= decision
    if symbol is not None:
        scope = out["symbol"].astype(str)
        mask &= scope.eq(symbol) | scope.str.lower().eq("global")
    return out.loc[mask].sort_values(["available_at", "source_id"]).reset_index(drop=True)
