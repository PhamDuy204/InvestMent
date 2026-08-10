from __future__ import annotations

from crypto_research.risk_sizing_v3 import conservative_risk_scale


def allocate_equity(*, current_equity: float, peak_equity: float, weights: dict[str, float], sigma12: dict[str, float], per_position_budget: float, total_risk_budget: float, max_multiplier: float, reserve_fraction: float = 0.2, drawdown_threshold: float = 0.1, drawdown_multiplier: float = 0.5, z_score: float = 1.645) -> dict[str, object]:
    if current_equity <= 0 or peak_equity <= 0 or peak_equity + 1e-12 < current_equity:
        raise ValueError("equity inputs must be positive and peak_equity >= current_equity")
    if not 0.0 <= reserve_fraction < 1.0:
        raise ValueError("reserve_fraction must be in [0, 1)")
    if not 0.0 <= drawdown_threshold < 1.0:
        raise ValueError("drawdown_threshold must be in [0, 1)")
    if not 0.0 < drawdown_multiplier <= 1.0:
        raise ValueError("drawdown_multiplier must be in (0, 1]")
    base_scale = conservative_risk_scale(weights, sigma12, per_position_budget=per_position_budget, total_risk_budget=total_risk_budget, max_multiplier=max_multiplier, z_score=z_score)
    drawdown = max(0.0, 1.0 - current_equity / peak_equity)
    risk_multiplier = base_scale * (drawdown_multiplier if drawdown >= drawdown_threshold else 1.0)
    reserve_cash = current_equity * reserve_fraction
    deployable_equity = current_equity - reserve_cash
    target_notionals = {symbol: deployable_equity * risk_multiplier * float(weight) for symbol, weight in weights.items()}
    total_stressed_risk = sum(abs(target_notionals[symbol]) * float(sigma12[symbol]) * z_score for symbol in target_notionals if abs(target_notionals[symbol]) > 1e-15)
    gross_notional = sum(abs(value) for value in target_notionals.values())
    return {"current_equity": float(current_equity), "peak_equity": float(peak_equity), "drawdown": float(drawdown), "reserve_cash": float(reserve_cash), "deployable_equity": float(deployable_equity), "risk_multiplier": float(risk_multiplier), "target_notionals": target_notionals, "gross_notional": float(gross_notional), "effective_leverage": float(gross_notional / current_equity), "correlation_one_risk_fraction": float(total_stressed_risk / current_equity)}
