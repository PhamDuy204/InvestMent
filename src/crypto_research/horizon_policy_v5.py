from __future__ import annotations

import math
from collections.abc import Mapping


def choose_horizon(forecasts: Mapping[int, float], *, volatility_state: str, burst_probability: float, confidence: float, min_confidence: float = 0.5) -> int | None:
    if not 0.0 <= burst_probability <= 1.0 or not 0.0 <= confidence <= 1.0:
        raise ValueError("probabilities and confidence must be between zero and one")
    if confidence < min_confidence:
        return None
    if volatility_state not in {"low", "normal", "high"}:
        raise ValueError("unknown volatility_state")
    if burst_probability >= 0.6 and 15 in forecasts:
        candidate = 15
    elif volatility_state == "high":
        candidate = 60
    elif volatility_state == "low":
        candidate = 720
    else:
        candidate = 240
    if candidate not in forecasts:
        return None
    value = float(forecasts[candidate])
    if not math.isfinite(value) or abs(value) <= 1e-12:
        return None
    sign = 1 if value > 0 else -1
    confirmations = sum(1 for horizon, forecast in forecasts.items() if horizon != candidate and math.isfinite(float(forecast)) and abs(float(forecast)) > 1e-12 and ((float(forecast) > 0) == (sign > 0)))
    return candidate if confirmations >= 1 else None


def decide_action(previous_weight: float, net_forecasts: Mapping[int, float], chosen_horizon: int | None, *, entry_threshold: float, exit_threshold: float) -> str:
    if entry_threshold < 0 or exit_threshold < 0:
        raise ValueError("thresholds must be non-negative")
    previous = float(previous_weight)
    if chosen_horizon is None or chosen_horizon not in net_forecasts:
        return "HOLD_LONG" if previous > 0 else "HOLD_SHORT" if previous < 0 else "NO_TRADE"
    forecast = float(net_forecasts[chosen_horizon])
    if abs(previous) <= 1e-12:
        if forecast >= entry_threshold:
            return "ENTER_LONG"
        if forecast <= -entry_threshold:
            return "ENTER_SHORT"
        return "NO_TRADE"
    if previous > 0:
        if forecast <= -entry_threshold:
            return "FLIP_SHORT"
        if forecast <= exit_threshold:
            return "EXIT"
        return "HOLD_LONG"
    if forecast >= entry_threshold:
        return "FLIP_LONG"
    if forecast >= -exit_threshold:
        return "EXIT"
    return "HOLD_SHORT"
