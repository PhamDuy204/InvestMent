from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ReliabilityGateConfig:
    qh_abs_threshold: float | None
    dispersion_threshold: float | None
    weak_score_threshold: float | None
    weak_score_veto_enabled: bool
    high_dispersion_scale: float = 0.5

    def __post_init__(self) -> None:
        for value, name in (
            (self.qh_abs_threshold, "qh_abs_threshold"),
            (self.dispersion_threshold, "dispersion_threshold"),
            (self.weak_score_threshold, "weak_score_threshold"),
        ):
            if value is not None and (not np.isfinite(float(value)) or float(value) < 0):
                raise ValueError(f"{name} must be finite and non-negative")
        if not 0.0 <= float(self.high_dispersion_scale) <= 1.0:
            raise ValueError("high_dispersion_scale must be in [0, 1]")


def _finite_quantile(series: pd.Series, quantile: float) -> float | None:
    values = pd.to_numeric(series, errors="coerce")
    values = values[np.isfinite(values)]
    if values.empty:
        return None
    return float(values.quantile(quantile))


def fit_reliability_gates(
    train: pd.DataFrame,
    *,
    score_col: str = "effective_score",
) -> ReliabilityGateConfig:
    required = {
        "qh_abs_order_imbalance",
        "dispersion_iqr",
        score_col,
        "realized_net_contribution",
    }
    if missing := required.difference(train.columns):
        raise ValueError(f"train missing columns: {sorted(missing)}")

    qh_threshold = _finite_quantile(train["qh_abs_order_imbalance"], 0.50)
    dispersion_threshold = _finite_quantile(train["dispersion_iqr"], 0.80)
    score = pd.to_numeric(train[score_col], errors="coerce")
    weak_score_threshold = _finite_quantile(score.abs(), 0.20)

    weak_score_veto_enabled = False
    if weak_score_threshold is not None:
        net = pd.to_numeric(train["realized_net_contribution"], errors="coerce")
        mask = score.abs().le(weak_score_threshold) & score.notna() & net.notna()
        if mask.any():
            weak_score_veto_enabled = bool(float(net.loc[mask].mean()) <= 0.0)

    return ReliabilityGateConfig(
        qh_abs_threshold=qh_threshold,
        dispersion_threshold=dispersion_threshold,
        weak_score_threshold=weak_score_threshold,
        weak_score_veto_enabled=weak_score_veto_enabled,
    )


def _get(row: Any, key: str, default: float = float("nan")) -> float:
    if isinstance(row, dict):
        value = row.get(key, default)
    elif hasattr(row, "get"):
        value = row.get(key, default)
    else:
        value = getattr(row, key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _is_increase(previous: float, target: float) -> bool:
    eps = 1e-12
    if abs(target) <= eps:
        return False
    if abs(previous) <= eps:
        return True
    if previous * target < 0:
        return True
    return abs(target) > abs(previous) + eps


def _veto_increase(previous: float, target: float) -> float:
    if not _is_increase(previous, target):
        return target
    if abs(previous) <= 1e-12 or previous * target < 0:
        return 0.0
    return previous


def _scale_increase(previous: float, target: float, scale: float) -> float:
    if not _is_increase(previous, target):
        return target
    if abs(previous) <= 1e-12 or previous * target < 0:
        return float(np.sign(target) * abs(target) * scale)
    increment = abs(target) - abs(previous)
    new_abs = abs(previous) + scale * increment
    return float(np.sign(target) * new_abs)


def apply_reliability_gates(
    row: Any,
    previous_weight: float,
    base_target_weight: float,
    config: ReliabilityGateConfig,
) -> dict[str, object]:
    previous = float(previous_weight)
    target = float(base_target_weight)
    base_sign = float(np.sign(target))

    qh = _get(row, "qh_order_imbalance")
    score = _get(row, "effective_score")
    dispersion = _get(row, "dispersion_iqr")

    h1_veto = False
    if (
        config.qh_abs_threshold is not None
        and np.isfinite(qh)
        and np.isfinite(score)
        and abs(qh) > config.qh_abs_threshold
        and np.sign(qh) != 0
        and np.sign(score) != 0
        and np.sign(qh) != np.sign(score)
        and _is_increase(previous, target)
    ):
        target = _veto_increase(previous, target)
        h1_veto = True

    h2_scaled = False
    if (
        config.dispersion_threshold is not None
        and np.isfinite(dispersion)
        and dispersion > config.dispersion_threshold
        and _is_increase(previous, target)
    ):
        target = _scale_increase(previous, target, config.high_dispersion_scale)
        h2_scaled = True

    h3_veto = False
    if (
        config.weak_score_veto_enabled
        and config.weak_score_threshold is not None
        and np.isfinite(score)
        and abs(score) <= config.weak_score_threshold
        and _is_increase(previous, target)
    ):
        target = _veto_increase(previous, target)
        h3_veto = True

    if base_sign and np.sign(target) not in (0.0, base_sign) and not (
        previous * base_target_weight < 0 and target == previous
    ):
        raise RuntimeError("V7 reliability gate attempted to create opposite direction")

    return {
        "target_weight": float(target),
        "h1_veto": h1_veto,
        "h2_scaled": h2_scaled,
        "h3_veto": h3_veto,
    }
