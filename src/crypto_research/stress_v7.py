from __future__ import annotations

from typing import Any

import pandas as pd

from crypto_research.run_leverage_v3 import run_grid, shock_grid


def _one_x(
    periods: pd.DataFrame,
    market: pd.DataFrame,
    *,
    round_trip_cost_bps: float = 10.0,
    slippage_bps: float = 0.0,
    funding_multiplier: float = 1.0,
    maintenance_margin_rate: float = 0.01,
) -> dict[str, Any]:
    result = run_grid(
        periods,
        market,
        leverages=(1,),
        maintenance_margin_rate=maintenance_margin_rate,
        round_trip_cost_bps=round_trip_cost_bps,
        slippage_bps=slippage_bps,
        funding_multiplier=funding_multiplier,
    )
    return dict(result["1"])


def run_v7_stress_suite(
    periods: pd.DataFrame,
    market: pd.DataFrame,
    *,
    delay_periods: pd.DataFrame | None = None,
) -> dict[str, Any]:
    base = _one_x(periods, market, round_trip_cost_bps=10.0)
    cost20 = _one_x(periods, market, round_trip_cost_bps=20.0)
    funding3 = _one_x(periods, market, funding_multiplier=3.0)
    slippage5 = _one_x(periods, market, slippage_bps=5.0)
    maintenance2 = _one_x(periods, market, maintenance_margin_rate=0.02)
    maintenance5 = _one_x(periods, market, maintenance_margin_rate=0.05)
    shock = shock_grid(periods, leverages=(1,), maintenance_margin_rate=0.01)

    if delay_periods is None:
        delay: dict[str, Any] = {"status": "NOT_EVALUATED_NO_DELAY_PERIODS"}
    else:
        delay = _one_x(delay_periods, market, round_trip_cost_bps=10.0)
        delay["status"] = "EVALUATED"

    return {
        "base_10bps": base,
        "cost_20bps": cost20,
        "delay_1h": delay,
        "funding_x3": funding3,
        "slippage_5bps_one_way": slippage5,
        "maintenance_2pct": maintenance2,
        "maintenance_5pct": maintenance5,
        "correlation_one_adverse_shock": shock,
    }
