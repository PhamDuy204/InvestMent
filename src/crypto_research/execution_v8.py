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
