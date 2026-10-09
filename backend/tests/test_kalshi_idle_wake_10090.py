"""#10090 — an accepted Kalshi winner quote after idle starts the flush now,
not at the cadence's next timer phase.

082595c23d gave `run_flush_cadence` an opt-in wake: an empty timer probe
spends no budget, so buffered input may start the unused period at once while
actual work still starts at most once per period. Polymarket opted in; the
Kalshi consumer still ran timer-only, so a winner quote landing just after an
empty probe waited up to a whole period before its write began.

Now the ticker handler sets the wake for an accepted, linked winner leg (the
predicate that already marks an event quoting), and the run counts a flush as
work when it snapshots prices or actually refreshes owed stamps.

The decisive control runs the actual consumer: a winner quote right after an
empty probe is written well inside the period (the parent waits for the next
phase). The others pin the bounds — a burst behind a woken write waits the
full period and lands once, owed-stamp work spends the budget, and refused,
unmapped, open-contract and prop input wakes nothing.
"""

import asyncio
import time

import pytest

import app.tasks.kalshi_ws as task
import app.tasks.live_blend_refresh as blend
import tests.test_kalshi_changed_scope_continuity_10090 as continuity
from tests.test_kalshi_changed_scope_continuity_10090 import (
    GAME_A, OPEN_1, _rig, _stop, _until,
)
from tests.test_kalshi_exact_trace_10702 import TICKER, handler

PERIOD = 0.6
WINNER = 71  # GAME_A's linked winner leg (event 900)
OPEN_LEG = 81  # OPEN_1, an open contract the run does not link as a game


def _recording(monkeypatch, cadence=(PERIOD, 2, None, 4)):
    """The rig's consumer with a short real cadence; records each flush's end
    (`_FlushTimings.flushed`) and each phase write with its time."""
    flushes, writes, owners = [], [], []

    class RecordingPrices(continuity.Prices):
        def __init__(self, scope):
            super().__init__(scope)
            owners.append(self)

        async def phase(self, session, values, *, force_observation=False):
            writes.append((time.monotonic(), dict(values)))
            async for result in super().phase(
                session, values, force_observation=force_observation,
            ):
                yield result

    original = task._FlushTimings.flushed

    def flushed(self, seconds):
        flushes.append(time.monotonic())
        return original(self, seconds)

    monkeypatch.setattr(continuity, "Prices", RecordingPrices)
    monkeypatch.setattr(task._FlushTimings, "flushed", flushed)
    scope = continuity.Scope()
    running, _sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    # After `_rig`, which installs its own 1000 s cadence.
    monkeypatch.setattr(task, "kalshi_flush_cadence", lambda: cadence)
    return scope, running, socket_for, opened_sockets, flushes, writes, owners


async def _right_after_a_probe(flushes):
    """Return the end of a timer flush that just happened."""
    seen = len(flushes)
    await _until(lambda: len(flushes) > seen, "a timer probe")
    return flushes[-1]


def _written(writes, outcome):
    return [(at, values[outcome]) for at, values in writes if outcome in values]


@pytest.mark.asyncio
async def test_a_winner_quote_after_empty_probes_is_written_before_the_next_phase(
    monkeypatch,
):
    (scope, running, socket_for, opened_sockets,
     flushes, writes, owners) = _recording(monkeypatch)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        while len(flushes) < 2:  # the cadence is idle: empty timer probes
            await _right_after_a_probe(flushes)
        assert writes == []

        probe = await _right_after_a_probe(flushes)
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
        await _until(lambda: _written(writes, WINNER), "the woken write")
        written_at = _written(writes, WINNER)[0][0]
        # Timer-only (the parent) writes at the next phase, a period after the
        # probe. Woken, the write starts as soon as the quote is accepted.
        assert written_at - probe < PERIOD / 2
        # Only the woken write spent budget; the empty probes before it did not.
        assert owners[0].flush_work == 1
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_a_burst_behind_a_woken_write_waits_the_full_period_and_lands_once(
    monkeypatch,
):
    (scope, running, socket_for, opened_sockets,
     flushes, writes, owners) = _recording(monkeypatch)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        await _right_after_a_probe(flushes)
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
        await _until(lambda: _written(writes, WINNER), "the woken write")
        first = _written(writes, WINNER)[0][0]

        prices = ("0.62", "0.63", "0.64", "0.65", "0.66")
        for price in prices:
            await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": price})
        await _until(lambda: len(_written(writes, WINNER)) == 2, "the next actual flush")
        await asyncio.sleep(0.1)
        legs = _written(writes, WINNER)
        assert len(legs) == 2
        # The actual-work ceiling: never two price flushes inside one period.
        assert legs[1][0] - first >= PERIOD - 0.05
        assert legs[1][1][0] == pytest.approx(0.66)  # coalesced to the newest
        assert owners[0].flush_work == 2
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_an_open_contract_quote_after_idle_waits_for_the_timer(monkeypatch):
    (scope, running, socket_for, opened_sockets,
     flushes, writes, owners) = _recording(monkeypatch)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        shard = socket_for({OPEN_1})
        probe = await _right_after_a_probe(flushes)
        await shard.deliver("ticker", {"market_ticker": OPEN_1, "price_dollars": "0.40"})
        await _until(lambda: _written(writes, OPEN_LEG), "the timer's write")
        # Still written (it is real work), but on the timer, never woken.
        assert _written(writes, OPEN_LEG)[0][0] - probe >= PERIOD - 0.1
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_owed_stamp_work_spends_the_budget_and_a_quote_waits_for_it(
    monkeypatch,
):
    (scope, running, socket_for, opened_sockets,
     flushes, writes, owners) = _recording(monkeypatch)
    adopted = []
    original = blend.LiveBlendRefresher.refresh_pending

    async def refresh_pending(self, *args, **kwargs):
        if not adopted:  # one owed event, then the debt is paid
            adopted.append(self.pending_event_ids())
        self.pending_event_ids = lambda: set()
        return await original(self, *args, **kwargs)

    def adopt(refresher):
        refresher.pending_event_ids = lambda: {900}
        return 1

    monkeypatch.setattr(blend, "adopt_handed_off", adopt)
    monkeypatch.setattr(blend.LiveBlendRefresher, "refresh_pending", refresh_pending)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        owed = await _right_after_a_probe(flushes)
        assert adopted == [{900}] and writes == []
        assert owners[0].flush_work == 1  # a pending-only flush is actual work

        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
        await _until(lambda: _written(writes, WINNER), "the next actual flush")
        assert _written(writes, WINNER)[0][0] - owed >= PERIOD - 0.1
    finally:
        await _stop(running)


# ----------------------------------------------- the ticker's wake ----


async def _tick(ns, **fields):
    await ns["handle_ticker"](dict(market_ticker=TICKER, **fields))


ACCEPTED = dict(price_dollars=".80", yes_bid_dollars=".66", yes_ask_dollars=".70")


@pytest.mark.asyncio
async def test_only_an_accepted_linked_winner_quote_wakes_the_flush():
    winner = handler(None)
    await _tick(winner, **ACCEPTED)
    assert winner["flush_wake"].is_set() and winner["price_buffer"]

    live = handler(None)
    live["live_event_ids"].add(900)
    await _tick(live, **ACCEPTED)
    assert live["flush_wake"].is_set()  # a live game's quote wakes it too

    refused = handler(None)
    await _tick(refused, yes_bid_dollars=".1", yes_ask_dollars=".9")
    assert not refused["flush_wake"].is_set() and not refused["price_buffer"]

    prop = handler(None, non_blend=(81,))
    await _tick(prop, **ACCEPTED)
    assert prop["price_buffer"] and not prop["flush_wake"].is_set()

    unmapped = handler(None, mapped=False)
    await _tick(unmapped, **ACCEPTED)
    assert not unmapped["flush_wake"].is_set()

    foreign = handler(None, mapped=False)
    foreign["open_contract_ids"][TICKER] = (7, 81)
    await _tick(foreign, **ACCEPTED)
    assert foreign["price_buffer"] and not foreign["flush_wake"].is_set()

    unlinked = handler(None)
    unlinked["event_id_by_outcome"].clear()
    await _tick(unlinked, **ACCEPTED)
    assert unlinked["price_buffer"] and not unlinked["flush_wake"].is_set()
