import numpy as np

from crypto_research.meta_calibrator_v5 import (
    META_FEATURES,
    calibrate_scores_from_probability,
)


def test_meta_features_exclude_future_labels():
    assert "model_score" in META_FEATURES
    assert not any("future" in name or "label" in name or "target" in name for name in META_FEATURES)


def test_probability_calibration_shrinks_without_flipping():
    scores = np.array([0.01, -0.02, 0.03])
    adjusted = calibrate_scores_from_probability(scores, np.array([1.0, 0.75, 0.4]))
    assert np.allclose(adjusted, [0.01, -0.01, 0.0])
    assert np.sign(adjusted[0]) == np.sign(scores[0])
    assert np.sign(adjusted[1]) == np.sign(scores[1])
