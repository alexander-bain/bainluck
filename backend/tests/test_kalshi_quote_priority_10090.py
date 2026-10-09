"""#10090 — a started, unresolved event whose winner legs are trading gets the
live games' delivery priority without being called live.

Moller–Pereira, 10/09 (Root's RESULT.md): event 15327169 ``suspended``, no
score, both winner contracts active; the slate's suspended arm admitted it,
but only ``status == 'live'`` filled the live set. Over 35 s the CLOB quote
moved 54.5 → 51.5 while Bain published two revisions 15.6 s apart: no book,
and its quotes waited behind the flush budget. Here the actual consumer runs
on a scope whose event is NOT live: a winner quote lifts it into the live set
(its book opens), and the two controls lift nothing — no quote (no read at
all), or a quote on an event the window refuses (completed, settled market).
"""

import asyncio
import time

import pytest

import app.tasks.kalshi_ws as task
import app.tasks.ws_admission as admission
from tests.test_kalshi_changed_scope_continuity_10090 import (
    GAME_A, Result, Scope, _rig, _stop, _until,
)

QUOTE_READ = "futures_markets.event_id"


class SuspendedScope(Scope):
    """Event 900 is never in the live reread; ``window`` is the quote-priority
    read's answer (the event is unresolved, scheduled/suspended). It started a
    minute ago, or at monotonic ``starts_at``; like the read's start clause, a
    start beyond the next admission check returns no row."""

    def __init__(self, window, starts_at=None):
        super().__init__()
        self.window = window
        self.starts_at = starts_at
        self.quote_reads = []

    async def execute(self, statement, *args):
        columns = [str(c) for c in getattr(statement, "selected_columns", ())]
        if columns and "win_probability_sources" in " ".join(columns):
            return Result([])  # not live
        if columns[:1] == [QUOTE_READ] and len(columns) == 2:
            self.quote_reads.append(str(statement))
            if not self.window:
                return Result([])
            starts_in = (-60.0 if self.starts_at is None
                         else self.starts_at - time.monotonic())
            if starts_in > admission.ADMISSION_CHECK_SECONDS:
                return Result([])
            return Result([(900, starts_in)])
        return await super().execute(statement, *args)


def _book_command(game):
    return next((c for c in game.commands
                 if c["params"].get("channels") == ["orderbook_delta"]
                 and c["params"].get("market_tickers")), None)


async def _quote(game):
    await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.53",
                                  "yes_bid_dollars": "0.52", "yes_ask_dollars": "0.53"})


@pytest.mark.asyncio
async def test_a_quoting_suspended_event_gets_live_priority_and_its_book(monkeypatch):
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    scope = SuspendedScope(window=True)
    running, _sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        await asyncio.sleep(0.2)  # many live rereads
        assert _book_command(game) is None
        assert scope.quote_reads == []  # nothing quoting: no read at all

        await _quote(game)
        await _until(lambda: _book_command(game) is not None, "the quoting leg's book")
        assert _book_command(game)["params"]["market_tickers"] == [GAME_A]
        read = scope.quote_reads[-1]
        assert "events.status IN" in read and "futures_markets.status" in read
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_a_quote_on_an_event_the_window_refuses_lifts_nothing(monkeypatch):
    """Completed/cancelled event or settled market: the read answers nothing."""
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    scope = SuspendedScope(window=False)
    running, _sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        await _quote(game)
        await _until(lambda: len(scope.quote_reads) >= 3, "quote-priority rereads")
        assert _book_command(game) is None
    finally:
        await _stop(running)


def test_quote_evidence_expires_in_place():
    quoted = {1: 100.0, 2: 50.0}
    window = task.QUOTE_PRIORITY_EVIDENCE_SECONDS
    assert task.recently_quoted_event_ids(quoted, 100.0 + window) == {1}
    assert quoted == {1: 100.0}
    assert task.recently_quoted_event_ids(quoted, 100.1 + window) == set()
    assert quoted == {}
