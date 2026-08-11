from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd


def block_bootstrap_equity(
    returns: pd.Series,
    *,
    samples: int = 2000,
    block_length: int = 20,
    seed: int = 42,
) -> dict[str, float | int]:
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) == 0:
        raise ValueError("returns must contain at least one finite observation")
    if samples <= 0 or block_length <= 0:
        raise ValueError("samples and block_length must be positive")
    rng = np.random.default_rng(seed)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(samples):
        picks: list[float] = []
        while len(picks) < len(values):
            max_start = max(len(values) - block_length + 1, 1)
            start = int(rng.integers(0, max_start))
            block = values[start : start + block_length]
            if len(block) == 0:
                block = values
            picks.extend(block.tolist())
        path = np.cumprod(1.0 + np.asarray(picks[: len(values)], dtype=float))
        peak = np.maximum.accumulate(path)
        finals.append(float(path[-1]))
        drawdowns.append(float(np.max(1.0 - path / peak)))
    final_array = np.asarray(finals, dtype=float)
    dd_array = np.asarray(drawdowns, dtype=float)
    return {
        "samples": int(samples),
        "block_length": int(block_length),
        "seed": int(seed),
        "final_equity_p05": float(np.quantile(final_array, 0.05)),
        "final_equity_median": float(np.median(final_array)),
        "final_equity_p95": float(np.quantile(final_array, 0.95)),
        "probability_final_equity_below_one": float(np.mean(final_array < 1.0)),
        "max_drawdown_median": float(np.median(dd_array)),
        "max_drawdown_p95": float(np.quantile(dd_array, 0.95)),
    }


def _sharpe(values: np.ndarray) -> float:
    if len(values) <= 1:
        return 0.0
    std = float(np.std(values, ddof=1))
    return float(np.mean(values) / std) if std > 0 else 0.0


def cscv_pbo(candidate_returns: pd.DataFrame, *, segments: int = 8) -> dict[str, object]:
    clean = candidate_returns.apply(pd.to_numeric, errors="coerce").dropna()
    if segments <= 0 or segments % 2:
        raise ValueError("segments must be a positive even integer")
    if len(clean) < segments:
        raise ValueError("not enough aligned observations for CSCV")
    if clean.shape[1] < 2:
        raise ValueError("CSCV requires at least two candidate columns")
    parts = np.array_split(np.arange(len(clean)), segments)
    logits: list[float] = []
    half = segments // 2
    for chosen in itertools.combinations(range(segments), half):
        train_idx = np.concatenate([parts[index] for index in chosen])
        test_idx = np.concatenate([parts[index] for index in range(segments) if index not in chosen])
        train_scores = {
            column: _sharpe(clean[column].to_numpy(dtype=float)[train_idx])
            for column in clean.columns
        }
        winner = max(train_scores, key=train_scores.get)
        test_scores = {
            column: _sharpe(clean[column].to_numpy(dtype=float)[test_idx])
            for column in clean.columns
        }
        ordered = sorted(test_scores, key=test_scores.get, reverse=True)
        rank = ordered.index(winner) + 1
        percentile = 1.0 - rank / (len(ordered) + 1.0)
        percentile = min(max(percentile, 1e-12), 1.0 - 1e-12)
        logits.append(math.log(percentile / (1.0 - percentile)))
    return {
        "segments": int(segments),
        "combinations": int(len(logits)),
        "candidate_count": int(clean.shape[1]),
        "observations": int(len(clean)),
        "pbo": float(np.mean(np.asarray(logits, dtype=float) <= 0.0)),
        "status": "CSCV_PBO_NOT_CPCV",
    }


def approximate_dsr(
    *,
    observed_sharpe: float,
    trial_sharpes: list[float],
    observations: int,
    total_trial_count: int,
) -> dict[str, object]:
    finite = [float(value) for value in trial_sharpes if math.isfinite(float(value))]
    benchmark = max(finite) if finite else 0.0
    scale = max(1.0 / math.sqrt(max(int(observations), 1)), 1e-12)
    z_score = (float(observed_sharpe) - benchmark) / scale
    probability = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
    return {
        "observed_sharpe": float(observed_sharpe),
        "benchmark_sharpe": float(benchmark),
        "available_trial_sharpes": int(len(finite)),
        "total_trial_count": int(total_trial_count),
        "observations": int(observations),
        "probability": float(min(max(probability, 0.0), 1.0)),
        "status": "APPROXIMATE_DSR_HISTORICAL_TRIAL_SHARPE_DISTRIBUTION_INCOMPLETE",
    }
