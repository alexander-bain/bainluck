"""#9120 — the postponed-ticker carry, the half that needs no database.

The SQL fences are proven on real Postgres in
``tests/integration/test_kalshi_postponed_carry_9120_pg.py``, which SKIPS
without ``SEARCH_TEST_DATABASE_URL``. This file runs everywhere and holds the
two things a skipped gate cannot: which tickers are eligible at all, and that
every place the matcher decides "the ticker's date says another game" asks
the carry first — the Kalshi winner was refused by the link guard AND stripped
by Phase 2 95 times, so a carry at one site only would flap forever.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.tasks.prediction_market_matching import (
    _kalshi_postponed_carry_matchup,
    _kalshi_postponed_game_carries,
)

_MODULE = Path(__file__).resolve().parents[1] / "app" / "tasks" / "prediction_market_matching.py"
UTC = timezone.utc


class TestWhichTickersAreEligible:
    def test_the_specimen_and_its_props(self):
        assert _kalshi_postponed_carry_matchup("KXMLBGAME-26SEP261915CHCBOS") == "CHCBOS"
        assert _kalshi_postponed_carry_matchup("KXMLBRFI-26SEP261915CHCBOS") == "CHCBOS"
        assert _kalshi_postponed_carry_matchup("KXMLBEXTRAS-26SEP261915CHCBOS") == "CHCBOS"
        assert _kalshi_postponed_carry_matchup("KXMLBINNINGTOTAL-26SEP271505CHCBOS-1") == "CHCBOS"

    def test_a_doubleheader_game_number_is_not_guessed(self):
        assert _kalshi_postponed_carry_matchup("KXMLBGAME-26SEP251305CHCBOSG1") is None
        assert _kalshi_postponed_carry_matchup("KXMLBGAME-26SEP261915CHCBOSG2") is None

    def test_other_sports_and_date_only_tickers_are_not_eligible(self):
        assert _kalshi_postponed_carry_matchup("KXNHLGAME-26SEP261915CHIBOS") is None
        assert _kalshi_postponed_carry_matchup("KXNFLGAME-26SEP27KCMIA") is None
        assert _kalshi_postponed_carry_matchup("KXMLBGAME-26SEP26CHCBOS") is None  # no HHMM
        assert _kalshi_postponed_carry_matchup(None) is None
        assert _kalshi_postponed_carry_matchup("") is None


@pytest.mark.asyncio
async def test_an_ineligible_ticker_never_touches_the_database():
    session = AsyncMock()
    td = datetime(2026, 9, 26, 19, 15, tzinfo=UTC)
    now = datetime(2026, 9, 27, 10, 53, tzinfo=UTC)
    assert await _kalshi_postponed_game_carries(
        session, "KXNHLGAME-26SEP261915CHIBOS", td, 1, now=now,
    ) is False
    assert await _kalshi_postponed_game_carries(
        session, "KXMLBGAME-26SEP261915CHCBOSG2", td, 1, now=now,
    ) is False
    session.execute.assert_not_called()


def _calls_per_function():
    tree = ast.parse(_MODULE.read_text())
    out = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        date = carry = 0
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "_ticker_date_conflicts_with_event":
                    date += 1
                elif node.func.id == "_kalshi_postponed_game_carries":
                    carry += 1
        if date or carry:
            out[fn.name] = (date, carry)
    return out


def test_every_site_that_refuses_or_unlinks_on_the_date_asks_the_carry():
    calls = _calls_per_function()
    # The deciders: the link guard, and Phase 2's two unlink arms.
    assert calls["_check_duplicate_kalshi_linkage_reason"] == (1, 1)
    assert calls["_match_prediction_markets"] == (2, 2)
    # The set is pinned, so a new date site has to take a position here.
    # `_kalshi_postponed_game_carries` uses the predicate on the venue's OTHER
    # tickers; `auto_create_self_refutes` decides whether a ticker-dated CREATE
    # converges, and never links or unlinks anything.
    assert set(calls) == {
        "_check_duplicate_kalshi_linkage_reason",
        "_match_prediction_markets",
        "_kalshi_postponed_game_carries",
        "auto_create_self_refutes",
    }
