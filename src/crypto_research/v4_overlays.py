from __future__ import annotations

import numpy as np

from crypto_research.multi_asset_v3 import _project_exposure_caps


def no_trade_band(
    previous: np.ndarray,
    target: np.ndarray,
    *,
    min_abs_change: float,
    gross_cap: float = 1.0,
    net_cap: float = 0.05,
    single_cap: float = 0.25,
) -> np.ndarray:
    """Keep inherited weights when a proposed absolute weight change is too small."""
    if min_abs_change < 0:
        raise ValueError("min_abs_change must be non-negative")
    previous = np.asarray(previous, dtype=float)
    target = np.asarray(target, dtype=float)
    if previous.shape != target.shape:
        raise ValueError("previous and target must have identical shapes")
    if min_abs_change == 0:
        return target.copy()
    candidate = np.where(np.abs(target - previous) >= min_abs_change, target, previous)
    return _project_exposure_caps(
        candidate,
        gross_cap=gross_cap,
        net_cap=net_cap,
        single_cap=single_cap,
    )


def funding_adjusted_prediction(
    prediction: np.ndarray,
    expected_funding_return: np.ndarray,
) -> np.ndarray:
    """Convert price-return expectation to net expectation using only a causal funding estimate."""
    prediction = np.asarray(prediction, dtype=float)
    funding = np.asarray(expected_funding_return, dtype=float)
    if prediction.shape != funding.shape:
        raise ValueError("prediction and expected_funding_return must have identical shapes")
    return prediction - funding
