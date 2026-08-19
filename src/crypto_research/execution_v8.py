"""Offline V8 research helpers. No exchange, order, credential, or network operations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_KEYS = ["decision_timestamp", "symbol"]
_EPS = 1e-12


@dataclass(frozen=True)
class DelayDamageFit:
    baseline_intercept: float
    baseline_lag_rv_slope: float
    augmented_intercept: float
    augmented_lag_rv_slope: float
    impact_slope: float
    anchor_damage: float


def lagged_impact_feature(frame: pd.DataFrame) -> pd.Series:
    returns = pd.to_numeric(frame["lag_return_1h"], errors="coerce")
    quote_volume = pd.to_numeric(frame["lag_quote_volume"], errors="coerce")
    valid = returns.notna() & quote_volume.notna() & (quote_volume > 0.0)
    raw = returns.abs().div(quote_volume.where(valid)).clip(lower=1e-18)
    return np.log10(raw).where(valid)


def build_delay_damage_labels(immediate: pd.DataFrame, delayed: pd.DataFrame) -> pd.DataFrame:
    if immediate.duplicated(_KEYS).any() or delayed.duplicated(_KEYS).any():
        raise ValueError("inputs must be one-to-one by decision_timestamp and symbol")
    left = immediate[
        _KEYS
        + ["previous_weight", "target_weight", "holding_return_label", "funding_sum_label"]
    ].copy()
    right = delayed[_KEYS + ["holding_return_label", "funding_sum_label"]].copy().rename(
        columns={
            "holding_return_label": "delayed_holding_return_label",
            "funding_sum_label": "delayed_funding_sum_label",
        }
    )
    out = left.merge(right, on=_KEYS, how="left", validate="one_to_one")
    numeric = [
        "previous_weight",
        "target_weight",
        "holding_return_label",
        "funding_sum_label",
        "delayed_holding_return_label",
        "delayed_funding_sum_label",
    ]
    out[numeric] = out[numeric].apply(pd.to_numeric, errors="coerce")
    previous = out["previous_weight"].fillna(0.0)
    target = out["target_weight"].fillna(0.0)
    sign_flip = previous.mul(target) < 0.0
    exposure_increase = sign_flip | (target.abs() > previous.abs() + _EPS)
    immediate_edge = out["holding_return_label"] + out["funding_sum_label"]
    delayed_edge = out["delayed_holding_return_label"] + out["delayed_funding_sum_label"]
    signed_delay_cost = np.sign(target) * (immediate_edge - delayed_edge)
    out["exposure_increase"] = exposure_increase
    out["delay_damage_per_unit"] = signed_delay_cost.clip(lower=0.0).where(
        exposure_increase, 0.0
    )
    return out[_KEYS + ["exposure_increase", "delay_damage_per_unit"]]


def fit_delay_damage_models(selection: pd.DataFrame) -> DelayDamageFit:
    work = selection.loc[
        selection["exposure_increase"].astype(bool),
        ["lag_rv12", "log_impact_1h", "delay_damage_per_unit"],
    ].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < 5:
        raise ValueError("delay-damage selection data insufficient")
    y = work["delay_damage_per_unit"].to_numpy(dtype=float)
    rv = work["lag_rv12"].to_numpy(dtype=float)
    impact = work["log_impact_1h"].to_numpy(dtype=float)
    base, *_ = np.linalg.lstsq(np.column_stack((np.ones(len(work)), rv)), y, rcond=None)
    aug, *_ = np.linalg.lstsq(
        np.column_stack((np.ones(len(work)), rv, impact)), y, rcond=None
    )
    positive = y[y > 0.0]
    if not len(positive):
        raise ValueError("delay-damage anchor requires positive selection damage")
    anchor = float(np.median(positive))
    return DelayDamageFit(
        baseline_intercept=float(base[0]),
        baseline_lag_rv_slope=float(base[1]),
        augmented_intercept=float(aug[0]),
        augmented_lag_rv_slope=float(aug[1]),
        impact_slope=float(aug[2]),
        anchor_damage=anchor,
    )


def apply_execution_fragility_scale(frame: pd.DataFrame, fit: DelayDamageFit) -> pd.DataFrame:
    """Simulate an offline no-boost scale on historical target weights."""
    out = frame.copy()
    scaled_targets: list[float] = []
    scales: list[float] = []
    for _, row in out.iterrows():
        previous = float(row["previous_weight"])
        target = float(row["target_weight"])
        sign_flip = previous * target < 0.0
        increase = sign_flip or abs(target) > abs(previous) + _EPS
        rv = float(row["lag_rv12"])
        impact = float(row["log_impact_1h"])
        pred_base = fit.baseline_intercept + fit.baseline_lag_rv_slope * rv
        pred_aug = (
            fit.augmented_intercept
            + fit.augmented_lag_rv_slope * rv
            + fit.impact_slope * impact
        )
        excess = max(0.0, pred_aug - pred_base) if np.isfinite(pred_aug - pred_base) else 0.0
        scale = fit.anchor_damage / (fit.anchor_damage + excess) if increase else 1.0
        scale = float(np.clip(scale, 0.0, 1.0))
        if sign_flip:
            simulated = target * scale
        elif increase:
            simulated = previous + scale * (target - previous)
        else:
            simulated = target
        scaled_targets.append(float(simulated))
        scales.append(scale)
    out["base_target_weight"] = out["target_weight"]
    out["target_weight"] = scaled_targets
    out["execution_fragility_scale"] = scales
    return out


def gross_exposure_stats(decisions: pd.DataFrame) -> dict[str, float]:
    """Summarize historical simulated gross exposure by decision timestamp."""
    if decisions.empty:
        return {
            "mean_gross_exposure": 0.0,
            "median_gross_exposure": 0.0,
            "max_gross_exposure": 0.0,
        }
    work = decisions[["decision_timestamp", "proposed_target_weight"]].copy()
    work["decision_timestamp"] = pd.to_datetime(work["decision_timestamp"], utc=True)
    work["proposed_target_weight"] = pd.to_numeric(
        work["proposed_target_weight"], errors="coerce"
    ).fillna(0.0)
    gross = (
        work.assign(abs_weight=work["proposed_target_weight"].abs())
        .groupby("decision_timestamp")["abs_weight"]
        .sum()
    )
    return {
        "mean_gross_exposure": float(gross.mean()),
        "median_gross_exposure": float(gross.median()),
        "max_gross_exposure": float(gross.max()),
    }


@dataclass(frozen=True)
class ExecutionResultV8:
    side: str
    target_notional: float
    filled_notional: float
    filled_base_quantity: float
    unfilled_notional: float
    arrival_mid: float
    best_quote: float
    vwap: float
    spread_cost_bps: float
    slippage_bps: float
    latency_cost_bps: float
    implementation_shortfall_bps: float
    fee_bps: float
    total_cost_bps: float
    depth_consumed_levels: int
    latency_ms: int
    unmodeled_tail: bool


class ExecutionSimulatorV8:
    """Local market-order book walk. It never extrapolates beyond observed depth."""

    def __init__(self, *, fee_bps: float = 0.0) -> None:
        if fee_bps < 0.0:
            raise ValueError("fee_bps must be non-negative")
        self.fee_bps = float(fee_bps)

    @staticmethod
    def _levels(book: dict[str, object], side: str) -> tuple[list[tuple[float, float]], float, float]:
        bids = sorted(
            ((float(level[0]), float(level[1])) for level in book.get("bids", [])),
            key=lambda item: item[0],
            reverse=True,
        )
        asks = sorted(
            ((float(level[0]), float(level[1])) for level in book.get("asks", [])),
            key=lambda item: item[0],
        )
        bids = [(price, qty) for price, qty in bids if price > 0.0 and qty > 0.0]
        asks = [(price, qty) for price, qty in asks if price > 0.0 and qty > 0.0]
        if not bids or not asks:
            raise ValueError("book requires positive bid and ask depth")
        if bids[0][0] >= asks[0][0]:
            raise ValueError("crossed book is not executable")
        return (asks if side == "buy" else bids), bids[0][0], asks[0][0]

    def simulate_market_order(
        self,
        *,
        target_notional: float,
        side: str,
        book: dict[str, object],
        decision_mid: float | None = None,
        latency_ms: int = 0,
    ) -> ExecutionResultV8:
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if target_notional <= 0.0 or not np.isfinite(target_notional):
            raise ValueError("target_notional must be finite and positive")
        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")

        levels, best_bid, best_ask = self._levels(book, side)
        arrival_mid = (best_bid + best_ask) / 2.0
        reference_mid = arrival_mid if decision_mid is None else float(decision_mid)
        if reference_mid <= 0.0 or not np.isfinite(reference_mid):
            raise ValueError("decision_mid must be finite and positive")

        remaining = float(target_notional)
        filled_notional = 0.0
        filled_base = 0.0
        consumed = 0
        for price, quantity in levels:
            available_notional = price * quantity
            take_notional = min(remaining, available_notional)
            if take_notional <= 0.0:
                continue
            filled_notional += take_notional
            filled_base += take_notional / price
            remaining -= take_notional
            consumed += 1
            if remaining <= _EPS:
                remaining = 0.0
                break

        if filled_base <= 0.0:
            raise ValueError("book contains no executable depth")
        vwap = filled_notional / filled_base
        best_quote = best_ask if side == "buy" else best_bid
        direction = 1.0 if side == "buy" else -1.0
        spread_cost_bps = direction * (best_quote - arrival_mid) / arrival_mid * 10_000.0
        slippage_bps = direction * (vwap - best_quote) / best_quote * 10_000.0
        latency_cost_bps = direction * (arrival_mid - reference_mid) / reference_mid * 10_000.0
        shortfall_bps = direction * (vwap - reference_mid) / reference_mid * 10_000.0
        total_cost_bps = shortfall_bps + self.fee_bps

        return ExecutionResultV8(
            side=side,
            target_notional=float(target_notional),
            filled_notional=float(filled_notional),
            filled_base_quantity=float(filled_base),
            unfilled_notional=float(max(0.0, remaining)),
            arrival_mid=float(arrival_mid),
            best_quote=float(best_quote),
            vwap=float(vwap),
            spread_cost_bps=float(spread_cost_bps),
            slippage_bps=float(slippage_bps),
            latency_cost_bps=float(latency_cost_bps),
            implementation_shortfall_bps=float(shortfall_bps),
            fee_bps=self.fee_bps,
            total_cost_bps=float(total_cost_bps),
            depth_consumed_levels=consumed,
            latency_ms=int(latency_ms),
            unmodeled_tail=remaining > _EPS,
        )
