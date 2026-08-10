from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pandas as pd

HORIZON = 12
BASE_COST_BPS = 10.0


@dataclass(frozen=True)
class V3Config:
    gamma: float
    kappa: float
    covariance_lookback: int
    gross_cap: float = 1.0
    net_cap: float = 0.05
    single_asset_cap: float = 0.25


def v3_cost_configs() -> list[V3Config]:
    return [
        V3Config(gamma=g, kappa=k, covariance_lookback=lb)
        for g, k, lb in product(
            (30.0, 100.0, 300.0, 1000.0),
            (0.0, 0.001, 0.003, 0.01),
            (168, 720),
        )
    ]


def uncertainty_configs() -> list[dict[str, float | int | None]]:
    configs: list[dict[str, float | int | None]] = [
        {"quantile": None, "window": None, "min_history": 0}
    ]
    for q, w in product((0.5, 0.8, 0.9), (20, 60)):
        configs.append({"quantile": q, "window": w, "min_history": 10})
    return configs


def select_inner_trial(
    trials: pd.DataFrame,
    *,
    score_col: str = "net_return",
    trade_count_col: str = "trade_count",
    min_trades: int = 200,
) -> pd.Series:
    """Select only among sufficiently sampled inner-validation trials."""
    eligible = trials[trials[trade_count_col] >= min_trades]
    if eligible.empty:
        raise ValueError("no inner trial meets minimum trade count")
    idx = eligible[score_col].astype(float).idxmax()
    return eligible.loc[idx]


def evaluate_frozen_configs(evaluator, configs, datasets):
    """Apply already chosen configs to stress datasets without OOS reselection."""
    rows = []
    for name, dataset in datasets.items():
        for config in configs:
            result = evaluator(dataset, config)
            rows.append({"stress": name, "config": config, **result})
    return pd.DataFrame(rows)
