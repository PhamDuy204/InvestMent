from __future__ import annotations

import pandas as pd

from .multi_asset_v3 import PortfolioCaps, cost_aware_cross_sectional_backtest


def evaluate_horizons(
    frames: dict[int, pd.DataFrame],
    symbols: list[str],
    *,
    gamma: float = 100.0,
    kappa: float = 0.01,
    covariance_lookback: int = 168,
    round_trip_bps: float = 10.0,
    caps: PortfolioCaps = PortfolioCaps(),
) -> dict[int, pd.DataFrame]:
    """Evaluate already-causally-constructed horizon datasets with one engine."""
    return {
        horizon: cost_aware_cross_sectional_backtest(
            frame,
            symbols,
            gamma=gamma,
            kappa=kappa,
            covariance_lookback=covariance_lookback,
            round_trip_bps=round_trip_bps,
            caps=caps,
        )
        for horizon, frame in frames.items()
    }
