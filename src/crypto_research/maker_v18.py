"""Actual post-fill EV and paper leverage policy for V18."""

from __future__ import annotations

import math
from typing import Any


def post_fill_entry_ev(
    *,
    long_entry_price: float,
    short_entry_price: float,
    baseline_60m_bps: float,
    baseline_15m_bps: float,
    long_entry_fee_bps: float,
    short_entry_fee_bps: float,
    expected_exit_fee_bps: float,
    expected_exit_price_improvement_bps: float,
    adverse_selection_bps: float,
    route_sigma_bps: float,
    price_volatility_bps: float,
    safety_buffer_bps: float,
    placement_capture_bps: float,
) -> dict[str, float | bool | str]:
    values = (
        long_entry_price,
        short_entry_price,
        long_entry_fee_bps,
        short_entry_fee_bps,
        expected_exit_fee_bps,
        expected_exit_price_improvement_bps,
        adverse_selection_bps,
        route_sigma_bps,
        price_volatility_bps,
        safety_buffer_bps,
        placement_capture_bps,
    )
    if not all(math.isfinite(float(value)) and float(value) >= 0.0 for value in values):
        raise ValueError("post-fill EV inputs must be finite and non-negative")
    if long_entry_price <= 0.0 or short_entry_price <= 0.0:
        raise ValueError("entry prices must be positive")
    if not all(math.isfinite(float(value)) for value in (baseline_60m_bps, baseline_15m_bps)):
        raise ValueError("route baselines must be finite")

    midpoint = (float(long_entry_price) + float(short_entry_price)) / 2.0
    gross = (float(short_entry_price) - float(long_entry_price)) / midpoint * 10_000.0
    capture = gross - max(float(baseline_60m_bps), float(baseline_15m_bps))
    entry_fees = float(long_entry_fee_bps) + float(short_entry_fee_bps)
    expected_value = (
        capture
        + float(expected_exit_price_improvement_bps)
        - float(expected_exit_fee_bps)
        - entry_fees
        - float(adverse_selection_bps)
        - float(safety_buffer_bps)
    )
    minimum = max(0.25, 0.05 * float(route_sigma_bps) + 0.02 * float(price_volatility_bps))
    tradeable = expected_value >= minimum
    return {
        "actual_gross_spread_bps": gross,
        "actual_capture_bps": capture,
        "actual_entry_fee_bps": entry_fees,
        "post_fill_expected_value_bps": expected_value,
        "minimum_required_ev_bps": minimum,
        "placement_capture_bps": float(placement_capture_bps),
        "tradeable": tradeable,
        "decision": "POST_FILL_EV_ACCEPTED" if tradeable else "POST_FILL_EV_REJECTED",
    }


def select_v18_profile(decision: dict[str, Any]) -> dict[str, float]:
    """Use 10% pair margin with 20x, 30x, or 40x simulated leverage."""

    expected_value_raw = decision.get("expected_value_bps")
    if expected_value_raw is None:
        expected_value_raw = decision["excess_after_cost_bps"]
    expected_value = float(expected_value_raw)
    z_score = float(decision["z_score"])
    route_sigma = float(decision["route_sigma_bps"])
    volatility = float(decision["price_volatility_bps"])
    if not all(math.isfinite(value) for value in (expected_value, z_score, route_sigma, volatility)):
        raise ValueError("profile inputs must be finite")

    if volatility >= 35.0 or route_sigma >= 8.0 or expected_value < 5.0:
        leverage = 20.0
    elif expected_value >= 15.0 and z_score >= 2.5 and route_sigma <= 5.0 and volatility <= 20.0:
        leverage = 40.0
    else:
        leverage = 30.0

    pair_margin_fraction = 0.10
    return {
        "leverage": leverage,
        "pair_margin_fraction": pair_margin_fraction,
        "pair_gross_fraction": leverage * pair_margin_fraction,
    }
