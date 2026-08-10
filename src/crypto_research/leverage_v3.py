from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class CrossMarginResult:
    final_equity: float
    liquidated: bool
    liquidation_step: int | None
    min_margin_ratio: float
    funding_paid: float
    execution_cost: float


def simulate_cross_margin_period(
    *,
    initial_equity: float,
    weights: np.ndarray,
    entry_prices: np.ndarray,
    mark_prices: Iterable[np.ndarray],
    exchange_leverage: float,
    maintenance_margin_rate: float = 0.005,
    round_trip_bps: float = 10.0,
    funding_rates: Iterable[np.ndarray] | None = None,
    liquidation_fee_rate: float = 0.005,
) -> CrossMarginResult:
    """Account-level cross-margin primitive; no return×leverage shortcut."""
    if initial_equity <= 0 or exchange_leverage <= 0:
        raise ValueError("initial_equity and exchange_leverage must be positive")
    weights = np.asarray(weights, dtype=float)
    entry_prices = np.asarray(entry_prices, dtype=float)
    if weights.shape != entry_prices.shape or np.any(entry_prices <= 0):
        raise ValueError("weights/entry_prices shape or value error")

    notional = initial_equity * weights
    qty = notional / entry_prices
    initial_margin = np.abs(notional).sum() / exchange_leverage
    if initial_margin > initial_equity + 1e-12:
        raise ValueError("position exceeds initial-margin capacity")

    one_way_rate = round_trip_bps * 1e-4 / 2.0
    execution_cost = float(np.abs(notional).sum() * one_way_rate)
    cash_equity = initial_equity - execution_cost
    min_margin_ratio = float("inf")
    total_funding = 0.0
    marks = [np.asarray(x, dtype=float) for x in mark_prices]
    funding = list(funding_rates) if funding_rates is not None else [np.zeros_like(weights) for _ in marks]
    if len(funding) != len(marks):
        raise ValueError("funding_rates length must match mark_prices")

    for step, (mark, rate) in enumerate(zip(marks, funding)):
        if mark.shape != weights.shape or np.any(mark <= 0):
            raise ValueError("invalid mark path")
        pnl = float(np.dot(qty, mark - entry_prices))
        rate = np.asarray(rate, dtype=float)
        funding_cash = float(np.dot(notional, rate))
        total_funding += funding_cash
        equity = cash_equity + pnl - total_funding
        current_notional = np.abs(qty * mark)
        maintenance = float(current_notional.sum() * maintenance_margin_rate)
        margin_ratio = float(equity / maintenance) if maintenance > 0 else float("inf")
        min_margin_ratio = min(min_margin_ratio, margin_ratio)
        if equity <= maintenance:
            fee = float(current_notional.sum() * liquidation_fee_rate)
            return CrossMarginResult(
                final_equity=equity - fee,
                liquidated=True,
                liquidation_step=step,
                min_margin_ratio=min_margin_ratio,
                funding_paid=total_funding,
                execution_cost=execution_cost + fee,
            )

    final_mark = marks[-1] if marks else entry_prices
    final_pnl = float(np.dot(qty, final_mark - entry_prices))
    exit_cost = float(np.abs(qty * final_mark).sum() * one_way_rate)
    final_equity = cash_equity + final_pnl - total_funding - exit_cost
    return CrossMarginResult(
        final_equity=final_equity,
        liquidated=False,
        liquidation_step=None,
        min_margin_ratio=min_margin_ratio,
        funding_paid=total_funding,
        execution_cost=execution_cost + exit_cost,
    )
