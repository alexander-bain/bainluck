"""#10090 (Alex 11/01 ~12:25 PM PT): a Kalshi GAME contract is priced at its last
trade while that trade sits inside the live book, as Kalshi's app shows it and
as a Polymarket trade already prices its leg; an open contract keeps the
midpoint, and a trade outside the book is still refused (#8753)."""

from __future__ import annotations

import json

import pytest

import app.tasks.kalshi_ws as kalshi_ws
import tests.test_ws_kalshi_linked_first_10640 as rig_mod


def _tick_at(price_of):
    def tick(ticker, bid, ask):
        return json.dumps({"type": "ticker", "msg": {
            "market_ticker": ticker, "yes_bid_dollars": bid,
            "yes_ask_dollars": ask, "price_dollars": price_of(ticker, bid, ask),
        }})
    return tick


async def _committed(monkeypatch, price_of, game_ticker="KXNFLGAME-26NOV01LVNYJ-NYJ"):
    monkeypatch.setattr(rig_mod, "_tick", _tick_at(price_of))
    monkeypatch.setattr(rig_mod, "GAME_TICKER", game_ticker)
    rig = rig_mod._Rig()
    task = await rig_mod._start(monkeypatch, rig, recycle=rig_mod.STEP * 2)
    await rig_mod._until(
        lambda: {o for o, _ in rig.committed} >= {rig_mod.GAME_OUTCOME, rig_mod.OPEN_OUTCOME},
        "both rows committed")
    task.cancel()
    try:
        await task
    except BaseException:
        pass
    return dict(rig.committed)


async def test_a_game_trade_inside_the_book_is_the_price(monkeypatch):
    rows = await _committed(monkeypatch, lambda t, bid, ask: bid)  # traded at the bid
    assert rows[rig_mod.GAME_OUTCOME] == pytest.approx(0.60)
    assert rows[rig_mod.OPEN_OUTCOME] == pytest.approx(0.21), "an open contract keeps the midpoint"


async def test_a_trade_outside_the_book_keeps_the_midpoint(monkeypatch):
    rows = await _committed(monkeypatch, lambda t, bid, ask: "0.70")
    assert rows[rig_mod.GAME_OUTCOME] == pytest.approx(0.61)


async def test_the_switch_restores_the_midpoint(monkeypatch):
    monkeypatch.setattr(kalshi_ws, "KALSHI_WS_GAME_LAST_TRADE", False)
    rows = await _committed(monkeypatch, lambda t, bid, ask: bid)
    assert rows[rig_mod.GAME_OUTCOME] == pytest.approx(0.61)


async def test_a_tennis_match_keeps_the_midpoint(monkeypatch):
    """11/01 20:34Z: a trade price failed the Challenger pairs' current-book
    proof (15-28 s na_proof waits); tennis keeps the midpoint."""
    rows = await _committed(monkeypatch, lambda t, bid, ask: bid,
                            game_ticker="KXATPMATCH-26SEP28ANGJOH-ANG")
    assert rows[rig_mod.GAME_OUTCOME] == pytest.approx(0.61)


def test_only_team_game_series_qualify():
    assert kalshi_ws._is_team_game_ticker("KXNFLGAME-26NOV01LVNYJ-NYJ")
    assert kalshi_ws._is_team_game_ticker("KXNCAAFGAME-26OCT31BSUTXST-BSU")
    assert not kalshi_ws._is_team_game_ticker("KXATPMATCH-26SEP28ANGJOH-ANG")
    assert not kalshi_ws._is_team_game_ticker("KXATPCHALLENGERMATCH-26NOV01AB-A")
