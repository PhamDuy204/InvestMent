from crypto_research.horizon_policy_v5 import choose_horizon, decide_action


def test_choose_horizon_and_abstention():
    forecasts = {15: 0.004, 60: 0.003, 240: 0.002, 720: 0.001}
    assert choose_horizon(forecasts, volatility_state="high", burst_probability=0.8, confidence=0.8) == 15
    assert choose_horizon(forecasts, volatility_state="high", burst_probability=0.1, confidence=0.8) == 60
    assert choose_horizon(forecasts, volatility_state="normal", burst_probability=0.1, confidence=0.8) == 240
    assert choose_horizon(forecasts, volatility_state="low", burst_probability=0.1, confidence=0.8) == 720
    assert choose_horizon({15: 0.01, 60: -0.01, 240: -0.01, 720: -0.01}, volatility_state="high", burst_probability=0.9, confidence=0.9) is None


def test_decide_action_enter_hold_exit_flip():
    assert decide_action(0.0, {240: 0.01}, 240, entry_threshold=0.002, exit_threshold=0.0005) == "ENTER_LONG"
    assert decide_action(0.2, {240: 0.01}, 240, entry_threshold=0.002, exit_threshold=0.0005) == "HOLD_LONG"
    assert decide_action(0.2, {240: 0.0}, 240, entry_threshold=0.002, exit_threshold=0.0005) == "EXIT"
    assert decide_action(0.2, {240: -0.01}, 240, entry_threshold=0.002, exit_threshold=0.0005) == "FLIP_SHORT"
