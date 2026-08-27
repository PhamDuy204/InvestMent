"""Pure, simulated-only cross-exchange arbitrage decisions for V12."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from crypto_research.execution_v8 import ExecutionSimulatorV8

_EPS = 1e-9


@dataclass(frozen=True)
class VenueBook:
    name: str
    book: dict[str, object]
    fee_bps: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("venue name must be non-empty")
        if self.fee_bps < 0.0:
            raise ValueError("fee_bps must be non-negative")


@dataclass(frozen=True)
class ArbitrageOpportunity:
    symbol: str
    buy_venue: str
    sell_venue: str
    target_notional: float
    buy_vwap: float
    sell_vwap: float
    gross_edge_bps: float
    total_fee_bps: float
    safety_buffer_bps: float
    net_edge_bps: float


def evaluate_pair(
    symbol: str,
    buy: VenueBook,
    sell: VenueBook,
    *,
    target_notional: float,
    safety_buffer_bps: float = 0.0,
) -> ArbitrageOpportunity | None:
    """Return the executable paper edge for one ordered venue pair, or reject it."""
    if buy.name == sell.name:
        return None
    if target_notional <= 0.0:
        raise ValueError("target_notional must be positive")
    if safety_buffer_bps < 0.0:
        raise ValueError("safety_buffer_bps must be non-negative")

    try:
        buy_fill = ExecutionSimulatorV8(fee_bps=buy.fee_bps).simulate_market_order(
            target_notional=target_notional,
            side="buy",
            book=buy.book,
        )
        sell_fill = ExecutionSimulatorV8(fee_bps=sell.fee_bps).simulate_market_order(
            target_notional=target_notional,
            side="sell",
            book=sell.book,
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    if buy_fill.unfilled_notional > _EPS or sell_fill.unfilled_notional > _EPS:
        return None

    midpoint = (buy_fill.vwap + sell_fill.vwap) / 2.0
    if midpoint <= 0.0:
        return None
    gross_edge_bps = (sell_fill.vwap - buy_fill.vwap) / midpoint * 10_000.0

    # Opening and closing both hedged legs means four taker executions.
    total_fee_bps = 2.0 * (buy.fee_bps + sell.fee_bps)
    net_edge_bps = gross_edge_bps - total_fee_bps - safety_buffer_bps
    if net_edge_bps <= 0.0:
        return None

    return ArbitrageOpportunity(
        symbol=symbol,
        buy_venue=buy.name,
        sell_venue=sell.name,
        target_notional=float(target_notional),
        buy_vwap=float(buy_fill.vwap),
        sell_vwap=float(sell_fill.vwap),
        gross_edge_bps=float(gross_edge_bps),
        total_fee_bps=float(total_fee_bps),
        safety_buffer_bps=float(safety_buffer_bps),
        net_edge_bps=float(net_edge_bps),
    )


def best_opportunity(
    symbol: str,
    venues: list[VenueBook],
    *,
    target_notional: float,
    min_net_edge_bps: float,
    safety_buffer_bps: float = 0.0,
) -> ArbitrageOpportunity | None:
    """Choose the best executable ordered venue pair above the requested edge floor."""
    if min_net_edge_bps < 0.0:
        raise ValueError("min_net_edge_bps must be non-negative")

    candidates = [
        opportunity
        for buy, sell in permutations(venues, 2)
        if (
            opportunity := evaluate_pair(
                symbol,
                buy,
                sell,
                target_notional=target_notional,
                safety_buffer_bps=safety_buffer_bps,
            )
        )
        is not None
        and opportunity.net_edge_bps >= min_net_edge_bps
    ]
    return max(candidates, key=lambda item: item.net_edge_bps, default=None)
