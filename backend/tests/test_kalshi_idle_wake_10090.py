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
Root attempt32: of a snapshot with prices, only a price attempt, a new held
quote's admission or a stamp start/admit counts; a probe over a cooled or
fenced cohort is an empty probe.

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

        async def phase(self, session, values, *, force_observation=False, forced_ids=()):
            writes.append((time.monotonic(), dict(values)))
            async for result in super().phase(
                session, values, force_observation=force_observation,
                forced_ids=forced_ids,
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



class _LockTimeout(Exception):
    sqlstate = "55P03"


@pytest.mark.asyncio
async def test_a_quote_after_a_cooled_held_cohorts_deadline_is_written_on_its_wake(
    monkeypatch,
):
    """Root attempt32: a cohort cooling down after a lock timeout stays
    buffered, and each timer probe that skipped it used to count as actual
    work. So a new quote arriving just after the retry deadline waited out the
    rest of that probe's period (the parent: ~197 ms of 250 ms). A probe that
    attempts nothing now spends no budget; the attempt that failed still did.
    The live phase's first refusal is its short probe, retried at the next
    flush start; the cooldown follows its ordinary attempt's refusal."""
    period, cooldown = 1.0, 2.5
    (scope, running, socket_for, opened_sockets,
     flushes, writes, owners) = _recording(monkeypatch, cadence=(period, 2, None, 4))
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", cooldown)
    attempts = []
    recording = continuity.Prices
    original_phase = recording.phase

    async def refused_once(self, session, values, **kwargs):
        attempts.append((time.monotonic(), dict(values)))
        if len(attempts) <= 2:
            raise _LockTimeout("canceling statement due to lock timeout")
        async for result in original_phase(self, session, values, **kwargs):
            yield result

    monkeypatch.setattr(recording, "phase", refused_once)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        await _right_after_a_probe(flushes)
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
        await _until(
            lambda: len(attempts) == 2
            and owners[0].lock_retry_until.get(WINNER, 0) > attempts[1][0],
            "the refused short probe, then its refused ordinary attempt",
        )
        until = owners[0].lock_retry_until[WINNER]
        work_after_refusal = owners[0].flush_work
        # The deadline falls between two timer phases (one period apart from
        # the refused flush's start), so at least one probe ran while cooled.
        await _until(lambda: blend._mono() > until + 0.05, "the retry deadline")
        assert len(attempts) == 2 and writes == []
        assert len(flushes) >= 4  # both refused flushes + probes over the cooled cohort
        # Probes that attempted nothing spent nothing.
        assert owners[0].flush_work == work_after_refusal

        sent = time.monotonic()
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.62"})
        await _until(lambda: _written(writes, WINNER), "the woken retry")
        written_at, value = _written(writes, WINNER)[0]
        # Counting the cooled probe as work (the parent), the write waits for
        # the next timer phase, ~0.45 s here. Woken, it starts at once.
        assert written_at - sent < period / 5, written_at - sent
        assert value[0] == pytest.approx(0.62)  # the newest quote, not the refused one
        assert owners[0].flush_work == work_after_refusal + 1
    finally:
        await _stop(running)



@pytest.mark.asyncio
async def test_ticks_on_a_cooled_cohort_attempt_nothing_and_keep_the_work_ceiling(
    monkeypatch,
):
    """The cost side of the change above: an uncounted probe leaves the wake
    live, so each winner tick on a cooled cohort may wake a flush. Such a flush
    attempts no price write while the cohort cools, and counted work still
    starts at most once per period."""
    period, cooldown = 0.5, 2.0
    (scope, running, socket_for, opened_sockets,
     flushes, writes, owners) = _recording(monkeypatch, cadence=(period, 2, None, 4))
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", cooldown)
    attempts = []
    recording = continuity.Prices
    original_phase = recording.phase

    async def refused_once(self, session, values, **kwargs):
        attempts.append((time.monotonic(), dict(values)))
        if len(attempts) == 1:
            raise _LockTimeout("canceling statement due to lock timeout")
        async for result in original_phase(self, session, values, **kwargs):
            yield result

    monkeypatch.setattr(recording, "phase", refused_once)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})
        await _right_after_a_probe(flushes)
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
        await _until(lambda: attempts, "the refused write")
        until = owners[0].lock_retry_until[WINNER]
        refused_at, work = time.monotonic(), owners[0].flush_work
        seen = len(flushes)
        ticks = 0
        while blend._mono() < until - 0.2:
            await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
            ticks += 1
            await asyncio.sleep(0.05)
        elapsed = time.monotonic() - refused_at
        woken = len(flushes) - seen
        print(f"EVIDENCE cooled ticks: {ticks} ticks, {woken} flushes in {elapsed:.2f}s, "
              f"counted work +{owners[0].flush_work - work}")
        assert len(attempts) == 1  # nothing written while the cohort cools
        assert owners[0].flush_work - work <= int(elapsed / period) + 1
        await _until(lambda: _written(writes, WINNER), "the retry after the deadline")
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
