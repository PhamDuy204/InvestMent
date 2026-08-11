import numpy as np
import pandas as pd
import pytest

from crypto_research.reliability_v7 import (
    ReliabilityGateConfig,
    apply_reliability_gates,
    fit_reliability_gates,
)


def _train():
    return pd.DataFrame(
        {
            "qh_abs_order_imbalance": [0.1, 0.2, 0.3, 0.4, 0.5],
            "dispersion_iqr": [0.01, 0.02, 0.03, 0.04, 0.05],
            "effective_score": [-0.05, -0.02, 0.01, 0.03, 0.08],
            "realized_net_contribution": [-0.02, -0.01, -0.005, 0.01, 0.02],
        }
    )


def test_fit_reliability_gates_uses_fixed_train_percentiles():
    train = _train()
    cfg = fit_reliability_gates(train)
    assert cfg.qh_abs_threshold == pytest.approx(train["qh_abs_order_imbalance"].median())
    assert cfg.dispersion_threshold == pytest.approx(train["dispersion_iqr"].quantile(0.80))
    assert cfg.weak_score_threshold == pytest.approx(train["effective_score"].abs().quantile(0.20))
    assert cfg.weak_score_veto_enabled is True


def test_h1_conflict_veto_blocks_new_entry():
    cfg = ReliabilityGateConfig(0.30, None, None, False)
    row = {"qh_order_imbalance": -0.80, "effective_score": 0.05, "dispersion_iqr": 0.01}
    out = apply_reliability_gates(row, 0.0, 0.25, cfg)
    assert out["target_weight"] == 0.0
    assert out["h1_veto"] is True


def test_h1_does_not_block_reduction_or_exit():
    cfg = ReliabilityGateConfig(0.30, None, None, False)
    row = {"qh_order_imbalance": -0.80, "effective_score": 0.05, "dispersion_iqr": 0.01}
    reduced = apply_reliability_gates(row, 0.25, 0.10, cfg)
    exited = apply_reliability_gates(row, 0.25, 0.0, cfg)
    assert reduced["target_weight"] == pytest.approx(0.10)
    assert exited["target_weight"] == 0.0


def test_h2_scales_only_incremental_exposure_increase():
    cfg = ReliabilityGateConfig(None, 0.03, None, False, high_dispersion_scale=0.5)
    row = {"qh_order_imbalance": 0.0, "effective_score": 0.05, "dispersion_iqr": 0.05}
    out = apply_reliability_gates(row, 0.10, 0.25, cfg)
    assert out["target_weight"] == pytest.approx(0.175)
    assert out["h2_scaled"] is True


def test_h2_does_not_scale_reduction():
    cfg = ReliabilityGateConfig(None, 0.03, None, False, high_dispersion_scale=0.5)
    row = {"qh_order_imbalance": 0.0, "effective_score": 0.05, "dispersion_iqr": 0.05}
    out = apply_reliability_gates(row, 0.25, 0.10, cfg)
    assert out["target_weight"] == pytest.approx(0.10)


def test_h3_vetoes_weak_new_exposure_only_when_enabled():
    cfg = ReliabilityGateConfig(None, None, 0.02, True)
    row = {"qh_order_imbalance": 0.0, "effective_score": 0.01, "dispersion_iqr": 0.01}
    entered = apply_reliability_gates(row, 0.0, 0.25, cfg)
    reduced = apply_reliability_gates(row, 0.25, 0.10, cfg)
    assert entered["target_weight"] == 0.0
    assert entered["h3_veto"] is True
    assert reduced["target_weight"] == pytest.approx(0.10)


def test_gates_never_flip_baseline_direction():
    cfg = ReliabilityGateConfig(0.20, 0.03, 0.02, True)
    row = {"qh_order_imbalance": -0.8, "effective_score": 0.01, "dispersion_iqr": 0.08}
    for base in (-0.25, 0.25):
        out = apply_reliability_gates(row, 0.0, base, cfg)
        sign = float(np.sign(out["target_weight"]))
        assert sign in {0.0, float(np.sign(base))}


def test_fit_isolation_ignores_evaluation_mutation():
    train = _train()
    before = fit_reliability_gates(train)
    evaluation = _train().copy()
    evaluation.loc[:, "effective_score"] = 999.0
    evaluation.loc[:, "realized_net_contribution"] = 999.0
    after = fit_reliability_gates(train)
    assert before == after
