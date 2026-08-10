from crypto_research.allocator_v5 import allocate_equity


def _kwargs():
    return dict(peak_equity=1000.0, weights={"A": 0.25, "B": -0.25}, sigma12={"A": 0.02, "B": 0.02}, per_position_budget=0.01, total_risk_budget=0.02, max_multiplier=2.0, reserve_fraction=0.0, drawdown_threshold=0.1, drawdown_multiplier=0.5)


def test_profit_compounds_through_current_equity_only():
    base = allocate_equity(current_equity=1000.0, **_kwargs())
    richer = allocate_equity(current_equity=1100.0, **{**_kwargs(), "peak_equity": 1100.0})
    assert abs(richer["target_notionals"]["A"] / base["target_notionals"]["A"] - 1.1) < 1e-12


def test_reserve_drawdown_and_correlation_cap():
    reserve = allocate_equity(current_equity=1000.0, **{**_kwargs(), "reserve_fraction": 0.2})
    assert reserve["reserve_cash"] == 200.0 and reserve["deployable_equity"] == 800.0
    normal = allocate_equity(current_equity=1000.0, **_kwargs())
    stressed = allocate_equity(current_equity=800.0, **_kwargs())
    assert abs(stressed["drawdown"] - 0.2) < 1e-12
    assert stressed["risk_multiplier"] <= normal["risk_multiplier"] * 0.5 + 1e-12
    assert normal["correlation_one_risk_fraction"] <= 0.02 + 1e-12
