import numpy as np
import pandas as pd
import pytest

from crypto_research.reliability_ml_v7 import (
    ReliabilityModelConfig,
    apply_reliability_probability,
    build_reliability_target,
    fit_reliability_model,
    predict_reliability,
)


def _train():
    index = np.arange(80)
    return pd.DataFrame(
        {
            "funding_crowding": np.sin(index / 5.0),
            "dispersion_iqr": 0.02 + 0.01 * np.cos(index / 7.0),
            "effective_score": np.where(index % 2 == 0, 0.04, -0.04),
            "realized_net_contribution": np.where(index % 3 == 0, -0.002, 0.003),
        }
    )


def test_model_config_is_fixed_and_bounded():
    cfg = ReliabilityModelConfig(feature_names=("funding_crowding", "dispersion_iqr"))
    assert cfg.max_iter == 100
    assert cfg.max_leaf_nodes == 15
    assert cfg.learning_rate == 0.05
    assert cfg.random_state == 42
    assert cfg.probability_threshold == 0.50


def test_unadmitted_feature_is_rejected_before_fit():
    cfg = ReliabilityModelConfig(feature_names=("funding_crowding", "unapproved"))
    with pytest.raises(ValueError, match="not admitted"):
        fit_reliability_model(
            _train().assign(unapproved=1.0),
            cfg,
            admitted_features={"funding_crowding"},
        )


def test_target_is_positive_after_cost_contribution_only():
    target = build_reliability_target(
        pd.DataFrame({"realized_net_contribution": [-0.01, 0.0, 0.01, np.nan]})
    )
    assert target.tolist() == [0, 0, 1, 0]


def test_fit_is_train_only_and_predictions_are_deterministic():
    train = _train()
    cfg = ReliabilityModelConfig(feature_names=("funding_crowding", "dispersion_iqr"))
    admitted = {"funding_crowding", "dispersion_iqr"}
    first = fit_reliability_model(train, cfg, admitted_features=admitted)
    evaluation = train.copy()
    evaluation["realized_net_contribution"] = evaluation["realized_net_contribution"] * -1000.0
    second = fit_reliability_model(train, cfg, admitted_features=admitted)
    np.testing.assert_allclose(
        predict_reliability(first, train, cfg),
        predict_reliability(second, train, cfg),
        atol=0.0,
        rtol=0.0,
    )


def test_probability_modifies_reliability_only_not_direction():
    assert apply_reliability_probability(0.0, 0.25, 0.40) == 0.0
    assert apply_reliability_probability(0.25, 0.10, 0.40) == pytest.approx(0.10)
    assert apply_reliability_probability(0.25, -0.25, 0.40) == 0.0
    assert apply_reliability_probability(0.0, -0.25, 0.80) == pytest.approx(-0.25)
