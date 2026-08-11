from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


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


def _price_row(table: pd.DataFrame, timestamp: pd.Timestamp, symbol: str) -> pd.Series:
    match = table.loc[(table["timestamp"] == timestamp) & (table["symbol"] == symbol)]
    if len(match) != 1:
        raise ValueError(f"expected one market row for {symbol} at {timestamp}, found {len(match)}")
    return match.iloc[0]


def simulate_weight_schedule(
    *,
    periods: pd.DataFrame,
    market: pd.DataFrame,
    initial_equity: float,
    leverage_multiplier: float,
    exchange_leverage_setting: float,
    maintenance_margin_rate: float,
    round_trip_cost_bps: float,
    slippage_bps: float,
    liquidation_fee_rate: float,
) -> dict[str, object]:
    required_periods = {"entry_timestamp", "exit_timestamp", "weights_json"}
    required_market = {"timestamp", "symbol", "open", "high", "low", "close"}
    if missing := required_periods.difference(periods.columns):
        raise ValueError(f"periods missing columns: {sorted(missing)}")
    if missing := required_market.difference(market.columns):
        raise ValueError(f"market missing columns: {sorted(missing)}")
    if initial_equity <= 0 or leverage_multiplier < 0 or exchange_leverage_setting <= 0:
        raise ValueError("invalid equity or leverage")
    if maintenance_margin_rate < 0 or round_trip_cost_bps < 0 or slippage_bps < 0:
        raise ValueError("risk and cost inputs must be non-negative")
    if liquidation_fee_rate < 0:
        raise ValueError("liquidation_fee_rate must be non-negative")

    schedule = periods.copy()
    schedule["entry_timestamp"] = pd.to_datetime(schedule["entry_timestamp"], utc=True)
    schedule["exit_timestamp"] = pd.to_datetime(schedule["exit_timestamp"], utc=True)
    schedule = schedule.sort_values("entry_timestamp")
    if (schedule["exit_timestamp"] < schedule["entry_timestamp"]).any():
        raise ValueError("exit_timestamp cannot precede entry_timestamp")

    prices = market.copy()
    prices["timestamp"] = pd.to_datetime(prices["timestamp"], utc=True)
    if "funding_event_rate" not in prices.columns:
        prices["funding_event_rate"] = 0.0
    for column in ("open", "high", "low", "close", "funding_event_rate"):
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
    prices = prices.sort_values(["timestamp", "symbol"])

    equity = float(initial_equity)
    qty: dict[str, float] = {}
    basis: dict[str, float] = {}
    total_execution_cost = 0.0
    total_slippage_cost = 0.0
    total_funding = 0.0
    turnover_notional = 0.0
    min_margin_ratio = float("inf")
    max_effective_leverage = 0.0
    margin_infeasible = False
    account_rows: list[dict[str, object]] = []
    last_processed_timestamp: pd.Timestamp | None = None
    final_timestamp: pd.Timestamp | None = None

    one_way_rate = float(round_trip_cost_bps) / 10_000.0 / 2.0
    slippage_rate = float(slippage_bps) / 10_000.0

    for period in schedule.itertuples(index=False):
        entry = pd.Timestamp(period.entry_timestamp)
        exit_timestamp = pd.Timestamp(period.exit_timestamp)
        raw_weights = json.loads(period.weights_json)
        target_weights = {
            str(symbol): float(weight) * float(leverage_multiplier)
            for symbol, weight in raw_weights.items()
            if abs(float(weight)) > 1e-15
        }
        symbols = sorted(set(qty) | set(target_weights))
        if not symbols:
            continue

        entry_prices: dict[str, float] = {}
        for symbol in symbols:
            row = _price_row(prices, entry, symbol)
            price = float(row["open"])
            if not np.isfinite(price) or price <= 0:
                raise ValueError("entry prices must be finite and positive")
            entry_prices[symbol] = price

        gap_pnl = 0.0
        for symbol, old_qty in qty.items():
            gap_pnl += float(old_qty) * (entry_prices[symbol] - basis[symbol])
        equity += gap_pnl
        if equity <= 0:
            return {
                "account_path": pd.DataFrame(account_rows),
                "initial_equity": float(initial_equity),
                "final_equity": float(equity),
                "net_return": float(equity / initial_equity - 1.0),
                "turnover_notional": float(turnover_notional),
                "funding_cashflow": float(total_funding),
                "execution_cost": float(total_execution_cost),
                "slippage_cost": float(total_slippage_cost),
                "liquidation_count": 1,
                "liquidated": True,
                "liquidation_timestamp": entry,
                "minimum_margin_ratio": float(min_margin_ratio),
                "max_effective_leverage": float(max_effective_leverage),
                "margin_infeasible": bool(margin_infeasible),
            }

        previous_notional = {
            symbol: float(qty.get(symbol, 0.0)) * entry_prices[symbol]
            for symbol in symbols
        }
        target_notional = {
            symbol: equity * target_weights.get(symbol, 0.0)
            for symbol in symbols
        }
        traded_notional = float(
            sum(abs(target_notional[symbol] - previous_notional[symbol]) for symbol in symbols)
        )
        execution_cost = traded_notional * one_way_rate
        slippage_cost = traded_notional * slippage_rate
        turnover_notional += traded_notional
        total_execution_cost += execution_cost
        total_slippage_cost += slippage_cost
        equity -= execution_cost + slippage_cost

        gross_notional = float(sum(abs(value) for value in target_notional.values()))
        initial_margin = gross_notional / float(exchange_leverage_setting)
        margin_infeasible = margin_infeasible or initial_margin > equity + 1e-12
        if equity > 0:
            max_effective_leverage = max(max_effective_leverage, gross_notional / equity)
        if margin_infeasible and initial_margin > equity + 1e-12:
            return {
                "account_path": pd.DataFrame(account_rows),
                "initial_equity": float(initial_equity),
                "final_equity": float(equity),
                "net_return": float(equity / initial_equity - 1.0),
                "turnover_notional": float(turnover_notional),
                "funding_cashflow": float(total_funding),
                "execution_cost": float(total_execution_cost),
                "slippage_cost": float(total_slippage_cost),
                "liquidation_count": 0,
                "liquidated": False,
                "liquidation_timestamp": None,
                "minimum_margin_ratio": float(min_margin_ratio),
                "max_effective_leverage": float(max_effective_leverage),
                "margin_infeasible": True,
            }

        qty = {
            symbol: target_notional[symbol] / entry_prices[symbol]
            for symbol in symbols
            if abs(target_notional[symbol]) > 1e-15
        }
        basis = {symbol: entry_prices[symbol] for symbol in qty}
        period_start_equity = float(equity)
        period_funding = 0.0

        interval = prices.loc[
            prices["timestamp"].between(entry, exit_timestamp, inclusive="both")
            & prices["symbol"].isin(list(qty))
        ].copy()
        timestamps = sorted(interval["timestamp"].unique())
        if last_processed_timestamp is not None:
            timestamps = [timestamp for timestamp in timestamps if timestamp > last_processed_timestamp]
        if not timestamps and qty:
            raise ValueError("no market path available for scheduled position")

        close_equity = period_start_equity
        last_close: dict[str, float] = dict(basis)
        for timestamp in timestamps:
            timestamp = pd.Timestamp(timestamp)
            close_marks: dict[str, float] = {}
            adverse_marks: dict[str, float] = {}
            funding_cash = 0.0
            for symbol, position_qty in qty.items():
                row = _price_row(prices, timestamp, symbol)
                close_price = float(row["close"])
                adverse_price = float(row["low"] if position_qty > 0 else row["high"])
                if close_price <= 0 or adverse_price <= 0:
                    raise ValueError("market prices must be positive")
                close_marks[symbol] = close_price
                adverse_marks[symbol] = adverse_price
                funding_cash += position_qty * close_price * float(row["funding_event_rate"])
            period_funding += funding_cash
            total_funding += funding_cash

            adverse_pnl = float(
                sum(qty[symbol] * (adverse_marks[symbol] - basis[symbol]) for symbol in qty)
            )
            adverse_equity = period_start_equity + adverse_pnl - period_funding
            maintenance = float(
                sum(abs(qty[symbol] * adverse_marks[symbol]) for symbol in qty)
                * maintenance_margin_rate
            )
            margin_ratio = float(adverse_equity / maintenance) if maintenance > 0 else float("inf")
            min_margin_ratio = min(min_margin_ratio, margin_ratio)
            if adverse_equity <= maintenance:
                liquidation_notional = float(
                    sum(abs(qty[symbol] * adverse_marks[symbol]) for symbol in qty)
                )
                liquidation_fee = liquidation_notional * liquidation_fee_rate
                total_execution_cost += liquidation_fee
                equity = adverse_equity - liquidation_fee
                account_rows.append({"timestamp": timestamp, "equity": float(equity)})
                return {
                    "account_path": pd.DataFrame(account_rows),
                    "initial_equity": float(initial_equity),
                    "final_equity": float(equity),
                    "net_return": float(equity / initial_equity - 1.0),
                    "turnover_notional": float(turnover_notional),
                    "funding_cashflow": float(total_funding),
                    "execution_cost": float(total_execution_cost),
                    "slippage_cost": float(total_slippage_cost),
                    "liquidation_count": 1,
                    "liquidated": True,
                    "liquidation_timestamp": timestamp,
                    "minimum_margin_ratio": float(min_margin_ratio),
                    "max_effective_leverage": float(max_effective_leverage),
                    "margin_infeasible": bool(margin_infeasible),
                }

            close_pnl = float(
                sum(qty[symbol] * (close_marks[symbol] - basis[symbol]) for symbol in qty)
            )
            close_equity = period_start_equity + close_pnl - period_funding
            account_rows.append({"timestamp": timestamp, "equity": float(close_equity)})
            last_close = close_marks
            last_processed_timestamp = timestamp
            final_timestamp = timestamp

        equity = float(close_equity)
        basis = dict(last_close)

    if qty:
        final_notional = float(sum(abs(qty[symbol] * basis[symbol]) for symbol in qty))
        final_execution = final_notional * one_way_rate
        final_slippage = final_notional * slippage_rate
        turnover_notional += final_notional
        total_execution_cost += final_execution
        total_slippage_cost += final_slippage
        equity -= final_execution + final_slippage
        if final_timestamp is not None:
            account_rows.append({"timestamp": final_timestamp, "equity": float(equity)})

    return {
        "account_path": pd.DataFrame(account_rows),
        "initial_equity": float(initial_equity),
        "final_equity": float(equity),
        "net_return": float(equity / initial_equity - 1.0),
        "turnover_notional": float(turnover_notional),
        "funding_cashflow": float(total_funding),
        "execution_cost": float(total_execution_cost),
        "slippage_cost": float(total_slippage_cost),
        "liquidation_count": 0,
        "liquidated": False,
        "liquidation_timestamp": None,
        "minimum_margin_ratio": float(min_margin_ratio),
        "max_effective_leverage": float(max_effective_leverage),
        "margin_infeasible": bool(margin_infeasible),
    }
