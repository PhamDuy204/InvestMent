from __future__ import annotations

import math


def conservative_risk_scale(
    weights: dict[str, float],
    sigma12: dict[str, float],
    *,
    per_position_budget: float,
    total_risk_budget: float,
    max_multiplier: float,
    z_score: float = 1.645,
) -> float:
    if per_position_budget <= 0 or total_risk_budget <= 0 or max_multiplier <= 0 or z_score <= 0:
        raise ValueError("risk budgets, multiplier, and z_score must be positive")
    held = {symbol: abs(float(weight)) for symbol, weight in weights.items() if abs(float(weight)) > 1e-15}
    if not held:
        return 0.0
    risks = []
    for symbol, weight in held.items():
        sigma = sigma12.get(symbol)
        if sigma is None or not math.isfinite(float(sigma)) or float(sigma) <= 0:
            return 0.0
        risks.append(weight * float(sigma) * z_score)
    single_scale = per_position_budget / max(risks)
    total_scale = total_risk_budget / sum(risks)
    return float(max(0.0, min(max_multiplier, single_scale, total_scale)))


def trailing_sigma12(frame, *, window: int = 168, min_periods: int = 24):
    import pandas as pd

    required = {"timestamp", "symbol", "ret_1"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    if window <= 1 or min_periods <= 1 or min_periods > window:
        raise ValueError("invalid rolling window")
    work = frame.loc[:, ["timestamp", "symbol", "ret_1"]].copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values(["symbol", "timestamp"])
    sigma = work.groupby("symbol", sort=False)["ret_1"].rolling(window, min_periods=min_periods).std(ddof=1).reset_index(level=0, drop=True)
    work["sigma12"] = sigma.to_numpy() * math.sqrt(12.0)
    return work.loc[:, ["timestamp", "symbol", "sigma12"]]
