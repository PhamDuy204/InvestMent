from __future__ import annotations

import numpy as np
import pandas as pd

META_FEATURES = ["model_score", "abs_model_score", "realized_vol_24", "quote_volume_z24", "trade_count_z24", "ret_24", "market_ret_4", "cross_sectional_dispersion", "hour_sin", "hour_cos", "taker_imbalance"]


def calibrate_scores_from_probability(scores, probabilities):
    scores = np.asarray(scores, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)
    if scores.shape != probabilities.shape:
        raise ValueError("scores and probabilities must have the same shape")
    return scores * np.clip(2.0 * probabilities - 1.0, 0.0, 1.0)


def _meta_frame(scored: pd.DataFrame) -> pd.DataFrame:
    frame = scored.copy()
    frame["abs_model_score"] = frame["model_score"].abs()
    missing = set(META_FEATURES).difference(frame.columns)
    if missing:
        raise ValueError(f"missing meta features: {sorted(missing)}")
    return frame.replace([np.inf, -np.inf], np.nan)


def fit_correctness_model(scored_validation: pd.DataFrame, *, target_col: str = "future_residual_return_12"):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if target_col not in scored_validation.columns:
        raise ValueError(f"missing meta target: {target_col}")
    frame = _meta_frame(scored_validation).dropna(subset=[*META_FEATURES, target_col])
    y = ((frame["model_score"] * frame[target_col]) > 0.0).astype(int)
    if y.nunique() < 2:
        raise ValueError("meta correctness target has only one class")
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=300, C=1.0, class_weight="balanced"))
    model.fit(frame[META_FEATURES], y)
    return model


def apply_correctness_model(model, scored: pd.DataFrame) -> pd.DataFrame:
    frame = _meta_frame(scored)
    valid = frame[META_FEATURES].notna().all(axis=1)
    probabilities = np.full(len(frame), 0.5, dtype=float)
    if valid.any():
        probabilities[valid.to_numpy()] = model.predict_proba(frame.loc[valid, META_FEATURES])[:, 1]
    result = scored.copy()
    result["meta_correct_probability"] = probabilities
    result["model_score_uncalibrated"] = result["model_score"].astype(float)
    result["model_score"] = calibrate_scores_from_probability(result["model_score_uncalibrated"].to_numpy(), probabilities)
    return result
