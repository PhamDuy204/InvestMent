from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier


@dataclass(frozen=True)
class ReliabilityModelConfig:
    feature_names: tuple[str, ...]
    max_iter: int = 100
    max_leaf_nodes: int = 15
    learning_rate: float = 0.05
    random_state: int = 42
    probability_threshold: float = 0.50

    def __post_init__(self) -> None:
        if not self.feature_names:
            raise ValueError("feature_names must be non-empty")
        if self.max_iter != 100 or self.max_leaf_nodes != 15:
            raise ValueError("V7 nonlinear model structure is fixed")
        if abs(float(self.learning_rate) - 0.05) > 1e-12 or self.random_state != 42:
            raise ValueError("V7 nonlinear model hyperparameters are fixed")
        if abs(float(self.probability_threshold) - 0.50) > 1e-12:
            raise ValueError("V7 probability threshold is fixed at 0.50")


def build_reliability_target(
    frame: pd.DataFrame,
    *,
    contribution_col: str = "realized_net_contribution",
) -> np.ndarray:
    if contribution_col not in frame.columns:
        raise ValueError(f"missing contribution column: {contribution_col}")
    contribution = pd.to_numeric(frame[contribution_col], errors="coerce")
    return contribution.gt(0.0).fillna(False).astype(int).to_numpy(dtype=int)


def _feature_matrix(frame: pd.DataFrame, config: ReliabilityModelConfig) -> pd.DataFrame:
    missing = set(config.feature_names).difference(frame.columns)
    if missing:
        raise ValueError(f"frame missing model features: {sorted(missing)}")
    return frame.loc[:, list(config.feature_names)].apply(pd.to_numeric, errors="coerce")


def fit_reliability_model(
    train: pd.DataFrame,
    config: ReliabilityModelConfig,
    *,
    admitted_features: set[str],
) -> HistGradientBoostingClassifier:
    unapproved = set(config.feature_names).difference(admitted_features)
    if unapproved:
        raise ValueError(f"model feature not admitted by Factor Observatory: {sorted(unapproved)}")
    target = build_reliability_target(train)
    if len(np.unique(target)) < 2:
        raise ValueError("reliability training target requires both classes")
    model = HistGradientBoostingClassifier(
        max_iter=config.max_iter,
        max_leaf_nodes=config.max_leaf_nodes,
        learning_rate=config.learning_rate,
        random_state=config.random_state,
    )
    model.fit(_feature_matrix(train, config), target)
    return model


def predict_reliability(
    model: Any,
    frame: pd.DataFrame,
    config: ReliabilityModelConfig,
) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(_feature_matrix(frame, config)), dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 2:
        raise ValueError("reliability model must produce binary class probabilities")
    return probabilities[:, 1]


def _is_exposure_increase(previous: float, target: float) -> bool:
    eps = 1e-12
    if abs(target) <= eps:
        return False
    if abs(previous) <= eps:
        return True
    if previous * target < 0:
        return True
    return abs(target) > abs(previous) + eps


def apply_reliability_probability(
    previous_weight: float,
    base_target_weight: float,
    probability_reliable: float,
    *,
    threshold: float = 0.50,
) -> float:
    probability = float(probability_reliable)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability_reliable must be in [0, 1]")
    if abs(float(threshold) - 0.50) > 1e-12:
        raise ValueError("V7 nonlinear reliability threshold is fixed at 0.50")
    previous = float(previous_weight)
    target = float(base_target_weight)
    if probability >= threshold or not _is_exposure_increase(previous, target):
        return target
    if abs(previous) <= 1e-12 or previous * target < 0:
        return 0.0
    return previous
