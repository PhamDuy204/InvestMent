from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ResearchOrder:
    order_type: str
    side: int
    limit_price: float | None = None
    trigger_price: float | None = None
    trailing_fraction: float | None = None
    initial_reference: float | None = None

    def __post_init__(self):
        if self.side not in {-1, 1}:
            raise ValueError("side must be -1 or 1")
        if self.order_type not in {"MARKET", "LIMIT", "POST_ONLY", "TRIGGER_MARKET", "TRAILING_STOP"}:
            raise ValueError("unsupported research order type")


@dataclass(frozen=True)
class FillResult:
    filled: bool
    fill_price: float | None
    fill_timestamp: pd.Timestamp | None
    maker: bool
    reason: str


def _adverse(price: float, side: int, slippage_bps: float) -> float:
    if slippage_bps < 0:
        raise ValueError("slippage_bps must be non-negative")
    return float(price) * (1.0 + float(side) * float(slippage_bps) / 10_000.0)


def _limit_fill(order: ResearchOrder, bars: pd.DataFrame, passive_cross_bps: float) -> FillResult:
    if order.limit_price is None or order.limit_price <= 0:
        raise ValueError("limit price must be positive")
    if passive_cross_bps < 0:
        raise ValueError("passive_cross_bps must be non-negative")
    limit = float(order.limit_price)
    buffer = passive_cross_bps / 10_000.0
    for row in bars.itertuples(index=False):
        crossed = float(row.low) <= limit * (1.0 - buffer) if order.side > 0 else float(row.high) >= limit * (1.0 + buffer)
        if crossed:
            return FillResult(True, limit, pd.Timestamp(row.timestamp), True, "PASSIVE_FILL")
    return FillResult(False, None, None, True, "PASSIVE_NOT_FILLED")


def simulate_order(order: ResearchOrder, bars: pd.DataFrame, *, slippage_bps: float = 0.0, passive_cross_bps: float = 0.0) -> FillResult:
    required = {"timestamp", "open", "high", "low"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"missing execution bars: {sorted(missing)}")
    if bars.empty:
        return FillResult(False, None, None, False, "NO_BARS")
    work = bars.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values("timestamp")
    first = work.iloc[0]
    if order.order_type == "MARKET":
        return FillResult(True, _adverse(float(first["open"]), order.side, slippage_bps), pd.Timestamp(first["timestamp"]), False, "MARKET_FILL")
    if order.order_type in {"LIMIT", "POST_ONLY"}:
        if order.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if order.order_type == "POST_ONLY":
            marketable = (order.side > 0 and float(order.limit_price) >= float(first["open"])) or (order.side < 0 and float(order.limit_price) <= float(first["open"]))
            if marketable:
                return FillResult(False, None, None, True, "POST_ONLY_MARKETABLE_CANCEL")
        return _limit_fill(order, work, passive_cross_bps)
    if order.order_type == "TRIGGER_MARKET":
        if order.trigger_price is None or order.trigger_price <= 0:
            raise ValueError("trigger order requires positive trigger_price")
        trigger = float(order.trigger_price)
        for row in work.itertuples(index=False):
            if order.side > 0 and float(row.high) >= trigger:
                return FillResult(True, _adverse(max(trigger, float(row.open)), 1, slippage_bps), pd.Timestamp(row.timestamp), False, "TRIGGER_FILL")
            if order.side < 0 and float(row.low) <= trigger:
                return FillResult(True, _adverse(min(trigger, float(row.open)), -1, slippage_bps), pd.Timestamp(row.timestamp), False, "TRIGGER_FILL")
        return FillResult(False, None, None, False, "TRIGGER_NOT_HIT")
    if order.trailing_fraction is None or not 0 < order.trailing_fraction < 1:
        raise ValueError("trailing stop requires trailing_fraction between zero and one")
    if order.initial_reference is None or order.initial_reference <= 0:
        raise ValueError("trailing stop requires positive initial_reference")
    reference = float(order.initial_reference)
    trail = float(order.trailing_fraction)
    for row in work.itertuples(index=False):
        if order.side < 0:
            trigger = reference * (1.0 - trail)
            if float(row.low) <= trigger:
                return FillResult(True, _adverse(min(trigger, float(row.open)), -1, slippage_bps), pd.Timestamp(row.timestamp), False, "TRAILING_TRIGGER")
            reference = max(reference, float(row.high))
        else:
            trigger = reference * (1.0 + trail)
            if float(row.high) >= trigger:
                return FillResult(True, _adverse(max(trigger, float(row.open)), 1, slippage_bps), pd.Timestamp(row.timestamp), False, "TRAILING_TRIGGER")
            reference = min(reference, float(row.low))
    return FillResult(False, None, None, False, "TRAILING_NOT_HIT")
