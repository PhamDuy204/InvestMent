from crypto_research.execution_v5 import choose_execution_mode


def test_high_urgency_uses_market():
    assert choose_execution_mode(urgency=0.9, vol_state="high", alpha_half_life_minutes=30) == "MARKET"


def test_low_urgency_low_vol_long_half_life_uses_post_only_candidate():
    assert choose_execution_mode(urgency=0.1, vol_state="low", alpha_half_life_minutes=720) == "POST_ONLY"


def test_mid_state_keeps_market_baseline():
    assert choose_execution_mode(urgency=0.3, vol_state="mid", alpha_half_life_minutes=180) == "MARKET"
