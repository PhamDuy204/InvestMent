from __future__ import annotations

import pytest

from crypto_research.arbitrage_v12 import VenueBook, best_opportunity, evaluate_pair


def _book(*, bid: float, ask: float, bid_qty: float = 10.0, ask_qty: float = 10.0):
    return {"bids": [[bid, bid_qty]], "asks": [[ask, ask_qty]]}


def test_rejects_spread_below_total_costs():
    buy = VenueBook("cheap", _book(bid=99.9, ask=100.0), fee_bps=5.0)
    sell = VenueBook("rich", _book(bid=100.05, ask=100.15), fee_bps=5.0)

    opportunity = evaluate_pair(
        "BTC/USDT:USDT",
        buy,
        sell,
        target_notional=20.0,
        safety_buffer_bps=1.0,
    )

    assert opportunity is None


def test_accepts_profitable_depth_aware_spread():
    buy = VenueBook("cheap", _book(bid=99.9, ask=100.0), fee_bps=2.0)
    sell = VenueBook("rich", _book(bid=101.0, ask=101.1), fee_bps=2.0)

    opportunity = evaluate_pair(
        "ETH/USDT:USDT",
        buy,
        sell,
        target_notional=20.0,
        safety_buffer_bps=1.0,
    )

    assert opportunity is not None
    assert opportunity.buy_venue == "cheap"
    assert opportunity.sell_venue == "rich"
    assert opportunity.buy_vwap == pytest.approx(100.0)
    assert opportunity.sell_vwap == pytest.approx(101.0)
    assert opportunity.net_edge_bps > 90.0


def test_rejects_when_either_leg_cannot_fill_requested_notional():
    buy = VenueBook(
        "thin",
        _book(bid=99.9, ask=100.0, bid_qty=10.0, ask_qty=0.05),
        fee_bps=0.0,
    )
    sell = VenueBook("rich", _book(bid=110.0, ask=110.1), fee_bps=0.0)

    assert (
        evaluate_pair(
            "SOL/USDT:USDT",
            buy,
            sell,
            target_notional=20.0,
        )
        is None
    )


def test_best_opportunity_selects_best_ordered_venue_pair():
    venues = [
        VenueBook("a", _book(bid=99.8, ask=100.0), fee_bps=1.0),
        VenueBook("b", _book(bid=101.0, ask=101.2), fee_bps=1.0),
        VenueBook("c", _book(bid=102.0, ask=102.2), fee_bps=1.0),
    ]

    opportunity = best_opportunity(
        "XRP/USDT:USDT",
        venues,
        target_notional=20.0,
        min_net_edge_bps=5.0,
    )

    assert opportunity is not None
    assert (opportunity.buy_venue, opportunity.sell_venue) == ("a", "c")


def test_crossed_or_invalid_book_is_rejected_not_promoted():
    crossed = VenueBook("bad", _book(bid=101.0, ask=100.0), fee_bps=0.0)
    normal = VenueBook("ok", _book(bid=102.0, ask=102.1), fee_bps=0.0)

    assert (
        evaluate_pair(
            "DOGE/USDT:USDT",
            crossed,
            normal,
            target_notional=20.0,
        )
        is None
    )
