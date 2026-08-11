from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BasisVolFit:
    baseline_intercept: float
    baseline_lag_coefficient: float
    augmented_intercept: float
    augmented_lag_coefficient: float
    basis_coefficient: float
    anchor_vol: float


def _design(*columns: np.ndarray) -> np.ndarray:
    return np.column_stack((np.ones(len(columns[0])), *columns))


def fit_basis_vol_model(train: pd.DataFrame) -> BasisVolFit:
    required = {'lag_rv12', 'abs_basis', 'future_rv12'}
    if missing := required.difference(train.columns):
        raise ValueError(f'basis training data missing columns: {sorted(missing)}')
    work = train.copy()
    for column in required:
        work[column] = pd.to_numeric(work[column], errors='coerce')
    work = work.dropna(subset=sorted(required))
    if len(work) < 4:
        raise ValueError('basis training data requires at least four complete rows')
    if (work[['lag_rv12', 'abs_basis', 'future_rv12']] < 0).any().any():
        raise ValueError('volatility and absolute basis inputs must be non-negative')

    lag = work['lag_rv12'].to_numpy(dtype=float)
    basis = work['abs_basis'].to_numpy(dtype=float)
    target = work['future_rv12'].to_numpy(dtype=float)
    baseline_coef, *_ = np.linalg.lstsq(_design(lag), target, rcond=None)
    augmented_coef, *_ = np.linalg.lstsq(_design(lag, basis), target, rcond=None)
    anchor = float(np.median(target))
    if not np.isfinite(anchor) or anchor <= 0:
        raise ValueError('selection median future volatility must be positive')
    return BasisVolFit(
        baseline_intercept=float(baseline_coef[0]),
        baseline_lag_coefficient=float(baseline_coef[1]),
        augmented_intercept=float(augmented_coef[0]),
        augmented_lag_coefficient=float(augmented_coef[1]),
        basis_coefficient=float(augmented_coef[2]),
        anchor_vol=anchor,
    )


def predict_lag_only_vol(row: pd.Series, fit: BasisVolFit) -> float:
    return float(fit.baseline_intercept + fit.baseline_lag_coefficient * float(row['lag_rv12']))


def predict_basis_vol(row: pd.Series, fit: BasisVolFit) -> float:
    return float(
        fit.augmented_intercept
        + fit.augmented_lag_coefficient * float(row['lag_rv12'])
        + fit.basis_coefficient * float(row['abs_basis'])
    )


def apply_basis_vol_scale(
    *,
    base_target_weight: float,
    predicted_vol: float,
    anchor_vol: float,
) -> dict[str, float]:
    target = float(base_target_weight)
    predicted = float(predicted_vol)
    anchor = float(anchor_vol)
    if not np.isfinite(anchor) or anchor <= 0:
        raise ValueError('anchor_vol must be positive and finite')
    if not np.isfinite(predicted) or predicted <= 0:
        scale = 1.0
    else:
        scale = min(1.0, anchor / predicted)
    return {'target_weight': float(target * scale), 'basis_scale': float(scale)}


def wrong_side_damage(
    decisions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    round_trip_cost_bps: float = 10.0,
) -> float:
    required_decisions = {
        'decision_timestamp',
        'symbol',
        'current_weight',
        'proposed_target_weight',
    }
    required_labels = {
        'decision_timestamp',
        'symbol',
        'holding_return_label',
        'funding_sum_label',
    }
    if missing := required_decisions.difference(decisions.columns):
        raise ValueError(f'decisions missing columns: {sorted(missing)}')
    if missing := required_labels.difference(labels.columns):
        raise ValueError(f'labels missing columns: {sorted(missing)}')
    if round_trip_cost_bps < 0:
        raise ValueError('round_trip_cost_bps must be non-negative')

    left = decisions.copy()
    right = labels.copy()
    for frame in (left, right):
        frame['decision_timestamp'] = pd.to_datetime(frame['decision_timestamp'], utc=True)
    merged = left.merge(
        right[list(required_labels)],
        on=['decision_timestamp', 'symbol'],
        how='left',
        validate='one_to_one',
    )
    if merged[['holding_return_label', 'funding_sum_label']].isna().any().any():
        raise ValueError('wrong-side damage labels are incomplete')
    one_way_cost = float(round_trip_cost_bps) / 2.0 / 10_000.0
    damage = 0.0
    for row in merged.itertuples(index=False):
        target = float(row.proposed_target_weight)
        current = float(row.current_weight)
        asset_edge = float(row.holding_return_label) - float(row.funding_sum_label)
        if abs(target) <= 1e-12 or target * asset_edge >= 0:
            continue
        contribution = target * asset_edge - abs(target - current) * one_way_cost
        damage += max(0.0, -float(contribution))
    return float(damage)
