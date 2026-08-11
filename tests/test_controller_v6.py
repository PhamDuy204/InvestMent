from crypto_research.controller_v6 import ControllerConfig, decide_v6


def test_burst_cannot_reverse_h12_direction():
    cfg = ControllerConfig()
    out = decide_v6(0.0, 0.02, {"burst_probability": 0.99, "vol_state": "high"}, cfg)
    assert out["decision"] != "ENTER_SHORT"
    assert out["target_weight"] >= 0


def test_high_risk_state_can_reduce_but_not_create_opposite_alpha():
    cfg = ControllerConfig(high_vol_scale=0.5, burst_high_scale=0.5)
    out = decide_v6(0.4, 0.01, {"burst_probability": 0.9, "vol_state": "high"}, cfg)
    assert out["target_weight"] >= 0
    assert abs(out["target_weight"]) <= 0.4


def test_low_vol_vn_day_can_select_longer_horizon_without_changing_side():
    cfg = ControllerConfig(low_vol_vn_horizon_minutes=180)
    out = decide_v6(0.0, -0.02, {"burst_probability": 0.1, "vol_state": "low", "vn_day_session": True}, cfg)
    assert out["decision"] == "ENTER_SHORT"
    assert out["chosen_horizon"] == 180


def test_no_trade_hysteresis_holds_small_weight_change():
    cfg = ControllerConfig(base_target_weight=0.30, no_trade_band=0.01)
    out = decide_v6(0.295, 0.01, {"burst_probability": 0.0, "vol_state": "mid"}, cfg)
    assert out["decision"] == "HOLD_LONG"
    assert out["target_weight"] == 0.295
