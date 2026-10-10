"""#9733 — a trade smaller than any order the venue accepts does not set a price.

WHAT A READER SAW. ``/search?q=yankees`` (390 px, 2026-09-30 05:00Z), the
ANSWERS card: "Will New York Yankees advance to the ALCS … No 38%", which reads
as Yankees 62%. The venue's price was ~38% YES.

WHY. Market 61380825 (condition ``0x8bd936dd…202a``) streams through #9484's
open-contract arm. At 01:54:05Z a 2-share No SELL at 0.38 printed on the tape
(76 cents); ``handle_trade`` graded the No leg with it, so both legs read 0.38
and ``rank`` tied, and search printed the No leg.

THE RULE. Polymarket's smallest order is 5 shares; a trade below that is the
leftover of someone else's order. On this market's tape every absurd print was
one (No 0.38 × 2, No 0.29 × 0.5, No 0.04 × 1.77, Yes 0.48 × 0.87) and every
print at the real price was 3.3 shares and up. A frame with no size keeps the old
behaviour.

Drives the REAL consumer with only the socket and the slate faked (the
``test_poly_ws_side1_leg_pairing_8403.py`` harness).
"""

import json

import pytest

import app.tasks.polymarket_ws as poly_task
from app.tasks.polymarket_ws import (
    MIN_PRICE_SETTING_TRADE_SHARES,
    trade_sets_a_price,
)
from tests.test_poly_ws_side1_leg_pairing_8403 import _run as _run_8403
import tests.test_poly_ws_side1_leg_pairing_8403 as rig

CONDITION = "0x8bd936dd0ebe810a2cf67f8ef8c0caf86b7dc0edda9375ea4499d404e333202a"
YES_TOKEN = "1111"
NO_TOKEN = "2222"
YES_LEG = 231082133
NO_LEG = 231082134
LEGS = [(YES_LEG, f"{CONDITION}_yes"), (NO_LEG, f"{CONDITION}_no")]


async def _run(monkeypatch, frames):
    monkeypatch.setattr(rig, "LUKKO_TOKEN", YES_TOKEN)
    monkeypatch.setattr(rig, "TAPPARA_TOKEN", NO_TOKEN)
    monkeypatch.setattr(rig, "CONDITION", CONDITION)
    # The rig's slate reads its token constants at call time.
    monkeypatch.setattr(
        rig,
        "_slate",
        lambda legs: [
            [(oid, rig.MARKET_ID, ext, CONDITION, rig.EVENT_ID) for oid, ext in legs],
            # The token read also carries the event's status (8b376bc807),
            # as the rig's own slate does.
            [(
                rig.MARKET_ID, CONDITION,
                {"clob_token_ids": [YES_TOKEN, NO_TOKEN]}, "scheduled",
            )],
            [(oid, rig.MARKET_ID, ext) for oid, ext in legs],
        ],
    )
    return await _run_8403(monkeypatch, LEGS, frames)


def _trade(token, price, size=None):
    frame = {"event_type": "last_trade_price", "asset_id": token, "price": price}
    if size is not None:
        frame["size"] = size
    return json.dumps(frame)


class TestTheSpecimenTape:
    async def test_the_two_share_no_print_does_not_move_the_no_leg(self, monkeypatch):
        """THE REGRESSION. Pre-fix the No leg took 0.38 and the pair read
        0.38 / 0.38. The real Yes prints before it still land."""
        writes, stats = await _run(
            monkeypatch,
            [
                _trade(YES_TOKEN, "0.38", "20"),
                _trade(NO_TOKEN, "0.38", "2"),
            ],
        )
        assert writes == [(YES_LEG, pytest.approx(0.38))], writes
        assert stats["trade_updates"] == 1, stats
        assert stats["trades_below_min_order"] == 1, stats

    @pytest.mark.parametrize(
        "price, size",
        [("0.29", "0.5"), ("0.04", "1.77"), ("0.38", "2"), ("0.48", "0.87")],
    )
    async def test_every_leftover_on_the_tape_is_refused(
        self, monkeypatch, price, size
    ):
        writes, stats = await _run(monkeypatch, [_trade(NO_TOKEN, price, size)])
        assert writes == [], writes
        assert stats["trades_below_min_order"] == 1, stats


class TestRealTradesStillStream:
    async def test_a_coherent_pair_keeps_streaming(self, monkeypatch):
        """Control (61380824 Red Sox shape): full-size prints on both legs are
        written, as before."""
        writes, stats = await _run(
            monkeypatch,
            [_trade(YES_TOKEN, "0.115", "40"), _trade(NO_TOKEN, "0.885", "12.5")],
        )
        assert dict(writes) == {
            YES_LEG: pytest.approx(0.115),
            NO_LEG: pytest.approx(0.885),
        }, writes
        assert stats["trades_below_min_order"] == 0, stats

    async def test_exactly_the_minimum_order_sets_a_price(self, monkeypatch):
        writes, _ = await _run(monkeypatch, [_trade(NO_TOKEN, "0.62", "5")])
        assert writes == [(NO_LEG, pytest.approx(0.62))], writes

    async def test_a_frame_without_a_size_behaves_as_before(self, monkeypatch):
        writes, stats = await _run(monkeypatch, [_trade(NO_TOKEN, "0.62")])
        assert writes == [(NO_LEG, pytest.approx(0.62))], writes
        assert stats["trades_below_min_order"] == 0, stats


@pytest.mark.parametrize(
    "size, expected",
    [
        (None, True),
        ("", True),
        ("abc", True),
        ("5", True),
        (5, True),
        ("100.25", True),
        ("4.99", False),
        ("2", False),
        (0.5, False),
        ("0", False),
    ],
)
def test_trade_sets_a_price(size, expected):
    msg = {"price": "0.5"}
    if size is not None:
        msg["size"] = size
    assert trade_sets_a_price(msg) is expected


def test_the_floor_is_the_venues_smallest_order():
    assert MIN_PRICE_SETTING_TRADE_SHARES == 5.0
    assert poly_task.MIN_PRICE_SETTING_TRADE_SHARES is MIN_PRICE_SETTING_TRADE_SHARES
