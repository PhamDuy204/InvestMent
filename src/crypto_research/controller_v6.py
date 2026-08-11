from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControllerConfig:
    base_target_weight: float = 0.30
    entry_score_threshold: float = 0.0
    no_trade_band: float = 0.005
    high_vol_scale: float = 0.75
    burst_high_scale: float = 0.75
    flow_conflict_scale: float = 1.0
    low_vol_vn_horizon_minutes: int = 180
    low_vol_other_horizon_minutes: int = 720
    normal_horizon_minutes: int = 720
    high_risk_horizon_minutes: int = 60
    execution_mode: str = "MARKET"
    effective_leverage: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.base_target_weight <= 1.0:
            raise ValueError("base_target_weight must be in [0, 1]")
        if self.entry_score_threshold < 0 or self.no_trade_band < 0:
            raise ValueError("thresholds must be non-negative")
        for value in (self.high_vol_scale, self.burst_high_scale, self.flow_conflict_scale):
            if not 0.0 <= value <= 1.0:
                raise ValueError("risk scales must be in [0, 1]")
        if self.effective_leverage < 0:
            raise ValueError("effective_leverage must be non-negative")


def _decision(previous: float, target: float) -> str:
    eps = 1e-12
    if abs(previous) <= eps and abs(target) <= eps:
        return "NO_TRADE"
    if abs(previous) <= eps:
        return "ENTER_LONG" if target > 0 else "ENTER_SHORT"
    if abs(target) <= eps:
        return "EXIT"
    if previous * target < 0:
        return "FLIP"
    if abs(target - previous) <= eps:
        return "HOLD_LONG" if target > 0 else "HOLD_SHORT"
    if abs(target) < abs(previous):
        return "REDUCE"
    return "HOLD_LONG" if target > 0 else "HOLD_SHORT"


def decide_v6(
    previous_weight: float,
    h12_score: float,
    state: dict[str, object],
    config: ControllerConfig,
) -> dict[str, object]:
    previous = float(previous_weight)
    score = float(h12_score)
    if abs(score) <= config.entry_score_threshold:
        raw_target = 0.0 if abs(previous) <= 1e-12 else previous
    else:
        raw_target = config.base_target_weight if score > 0 else -config.base_target_weight

    scale = 1.0
    vol_state = str(state.get("vol_state", "mid"))
    burst_probability = float(state.get("burst_probability", 0.0) or 0.0)
    if vol_state == "high":
        scale *= config.high_vol_scale
    if burst_probability >= 0.65:
        scale *= config.burst_high_scale

    flow_state = str(state.get("flow_state", "unknown"))
    if raw_target > 0 and flow_state == "sell":
        scale *= config.flow_conflict_scale
    elif raw_target < 0 and flow_state == "buy":
        scale *= config.flow_conflict_scale

    target = raw_target * scale
    if previous * target > 0 and abs(target - previous) < config.no_trade_band:
        target = previous

    if vol_state == "high" or burst_probability >= 0.65:
        horizon = config.high_risk_horizon_minutes
    elif vol_state == "low" and bool(state.get("vn_day_session", False)):
        horizon = config.low_vol_vn_horizon_minutes
    elif vol_state == "low":
        horizon = config.low_vol_other_horizon_minutes
    else:
        horizon = config.normal_horizon_minutes

    return {
        "decision": _decision(previous, target),
        "current_weight": previous,
        "target_weight": float(target),
        "chosen_horizon": int(horizon),
        "risk_scale": float(scale),
        "effective_leverage": float(config.effective_leverage * scale),
        "execution_mode": config.execution_mode,
    }
