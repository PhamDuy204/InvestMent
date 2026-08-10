import numpy as np

from crypto_research.v4_overlays import funding_adjusted_prediction, no_trade_band


def test_no_trade_band_keeps_small_changes_and_applies_large_changes():
    previous = np.array([0.10, -0.10, 0.0])
    target = np.array([0.105, -0.13, 0.04])
    result = no_trade_band(previous, target, min_abs_change=0.01)
    assert np.allclose(result, [0.10, -0.13, 0.04])


def test_zero_no_trade_band_is_identity():
    previous = np.array([0.10, -0.10])
    target = np.array([0.20, -0.20])
    assert np.allclose(no_trade_band(previous, target, min_abs_change=0.0), target)


def test_funding_adjusted_prediction_uses_causal_expected_funding_return():
    prediction = np.array([0.01, -0.02])
    expected_funding_return = np.array([0.001, -0.002])
    result = funding_adjusted_prediction(prediction, expected_funding_return)
    assert np.allclose(result, [0.009, -0.018])
