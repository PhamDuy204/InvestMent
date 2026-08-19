from __future__ import annotations

import inspect
import math
from datetime import datetime, timezone

import pytest

from crypto_research.l2_shadow_v8 import snapshot_from_order_book


def test_snapshot_from_order_book_computes_top_book_and_notional_depth() -> None:
    book = {
        "timestamp": 1_787_150_400_000,
        "nonce": 123,
        "bids": [[99.0, 2.0], [100.0, 1.5], [98.0, 3.0]],
        "asks": [[102.0, 2.5], [101.0, 1.0], [103.0, 4.0]],
    }
    captured = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

    row = snapshot_from_order_book("BTC/USDT:USDT", book, captured)

    assert row["symbol"] == "BTC/USDT:USDT"
    assert row["best_bid"] == 100.0
    assert row["best_ask"] == 101.0
    assert row["bid_qty"] == 1.5
    assert row["ask_qty"] == 1.0
    assert math.isclose(row["mid_price"], 100.5)
    assert math.isclose(row["spread_bps"], (1.0 / 100.5) * 10_000.0)
    assert math.isclose(row["top_of_book_imbalance"], 0.2)
    assert math.isclose(row["microprice"], (101.0 * 1.5 + 100.0 * 1.0) / 2.5)
    assert math.isclose(row["depth_5_bid"], 100.0 * 1.5 + 99.0 * 2.0 + 98.0 * 3.0)
    assert math.isclose(row["depth_5_ask"], 101.0 * 1.0 + 102.0 * 2.5 + 103.0 * 4.0)
    assert row["update_id"] == 123
    assert row["captured_at"] == captured.isoformat()


def test_snapshot_from_order_book_rejects_crossed_or_empty_book() -> None:
    captured = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="non-empty"):
        snapshot_from_order_book("BTC/USDT:USDT", {"bids": [], "asks": []}, captured)

    with pytest.raises(ValueError, match="crossed"):
        snapshot_from_order_book(
            "BTC/USDT:USDT",
            {"bids": [[101.0, 1.0]], "asks": [[100.0, 1.0]]},
            captured,
        )


def test_l2_module_has_no_authenticated_trading_surface() -> None:
    import crypto_research.l2_shadow_v8 as module

    source = inspect.getsource(module).lower()
    forbidden = (
        "api_key",
        "secret",
        "create_order",
        "new_order",
        "place_order",
        "cancel_order",
        "withdraw",
        "transfer",
        "set_leverage",
        "change_leverage",
    )

    assert not any(token in source for token in forbidden)
