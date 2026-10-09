"""#10090 — a quoting event's priority read runs when its quotes start, not at
the next 30 s admission check.

af98846d2a lifts a started, unresolved, not-``live`` event into the live set
(fast writes, a direct book) once its winner legs quote — but only on the
admission reread, at once and every `ADMISSION_CHECK_SECONDS` (30 s). A
suspended game whose quotes resume after that first read waited up to a whole
interval for its book. Now the consumer's first winner quote for an event
outside the live set wakes the EXISTING watcher, coalesced and cooled down;
the read, the window and the book cap are unchanged.

The decisive control runs the actual consumer with a 30 s check that never
fires inside the test: the book opens anyway. The rest pin the bounds — a
burst is one read, same-event chatter (including an event the window refuses)
never reads again, a failed reread is not hurried, a cancel joins its waits,
and a live event's quote wakes nothing.
"""

import asyncio
import time

import pytest

import app.tasks.kalshi_ws as task
import app.tasks.ws_admission as admission
from tests.test_kalshi_changed_scope_continuity_10090 import (
    GAME_A, _rig, _stop, _until,
)
from tests.test_kalshi_exact_trace_10702 import TICKER, handler
from tests.test_kalshi_quote_priority_10090 import (
    SuspendedScope, _book_command, _quote,
)


class CountingScope(SuspendedScope):
    def __init__(self, window):
        super().__init__(window)
        self.live_reads = 0

    async def execute(self, statement, *args):
        columns = [str(c) for c in getattr(statement, "selected_columns", ())]
        if len(columns) == 3 and "win_probability_sources" in " ".join(columns):
            self.live_reads += 1
        return await super().execute(statement, *args)


def _slow_checks(monkeypatch, cooldown=0.05):
    """Only the first admission read happens inside the test unless woken."""
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 30)
    monkeypatch.setattr(admission, "ADMISSION_WAKE_COOLDOWN_SECONDS", cooldown)


@pytest.mark.asyncio
async def test_a_first_quote_after_the_check_opens_the_book_before_the_next_tick(
    monkeypatch,
):
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    scope = CountingScope(window=True)
    running, _sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    _slow_checks(monkeypatch)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        await _until(lambda: scope.live_reads >= 1, "the first admission read")
        game = socket_for({GAME_A})
        await asyncio.sleep(0.2)
        reads_before = scope.live_reads
        assert _book_command(game) is None and scope.quote_reads == []

        started = time.monotonic()
        await _quote(game)
        await _until(lambda: _book_command(game) is not None, "the quoting leg's book")
        assert time.monotonic() - started < 5  # the 30 s check never fired
        assert _book_command(game)["params"]["market_tickers"] == [GAME_A]
        assert scope.live_reads == reads_before + 1
        assert len(scope.quote_reads) == 1
        read = scope.quote_reads[-1]
        assert "events.status IN" in read and "futures_markets.status" in read
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_a_refused_events_burst_and_chatter_read_once(monkeypatch):
    """Completed event / settled market: one read for the burst, then its
    continuing quotes never read again (it keeps its evidence while quoting)."""
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    scope = CountingScope(window=False)
    running, _sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    _slow_checks(monkeypatch)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        await _until(lambda: scope.live_reads >= 1, "the first admission read")
        game = socket_for({GAME_A})
        await asyncio.sleep(0.2)
        reads_before = scope.live_reads
        for _ in range(5):
            await _quote(game)
        await _until(lambda: len(scope.quote_reads) == 1, "the woken read")
        for _ in range(5):
            await _quote(game)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)
        assert len(scope.quote_reads) == 1
        assert scope.live_reads == reads_before + 1
        assert _book_command(game) is None
    finally:
        await _stop(running)


# ------------------------------------------------------ the watcher ----


def _counting_load(answers=None):
    reads = []

    async def load():
        reads.append(time.monotonic())
        if answers is not None:
            answer = answers[min(len(reads), len(answers)) - 1]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return set()

    return reads, load


async def _watch(load, wake, cooldown=0.0, check=1000):
    return asyncio.create_task(admission.watch_for_unadmitted_live_events(
        load, [], arm="t", started_at=0.0, check_seconds=check,
        min_recycle_seconds=0, wake=wake, wake_cooldown_seconds=cooldown,
    ))


@pytest.mark.asyncio
async def test_a_burst_of_wakes_is_one_reread():
    wake = asyncio.Event()
    reads, load = _counting_load()
    watcher = await _watch(load, wake)
    try:
        await _until(lambda: len(reads) == 1, "the baseline read")
        for _ in range(50):
            wake.set()
        await _until(lambda: len(reads) == 2, "the woken read")
        await asyncio.sleep(0.2)
        assert len(reads) == 2
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_woken_reread_waits_out_the_cooldown_from_the_last_read():
    wake = asyncio.Event()
    reads, load = _counting_load()
    watcher = await _watch(load, wake, cooldown=0.3)
    try:
        await _until(lambda: len(reads) == 1, "the baseline read")
        wake.set()
        await _until(lambda: len(reads) == 2, "the woken read")
        assert reads[1] - reads[0] >= 0.29
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_woken_reread_still_admits_a_newly_live_event():
    wake = asyncio.Event()
    reads, load = _counting_load([set(), {901}])
    watcher = await _watch(load, wake)
    await _until(lambda: len(reads) == 1, "the baseline read")
    wake.set()
    assert await asyncio.wait_for(watcher, 2) == frozenset({901})


@pytest.mark.asyncio
async def test_after_a_failed_reread_a_wake_does_not_hurry_the_next():
    wake = asyncio.Event()
    reads, load = _counting_load([set(), RuntimeError("db down")])
    watcher = await _watch(load, wake)
    try:
        await _until(lambda: len(reads) == 1, "the baseline read")
        wake.set()
        await _until(lambda: len(reads) == 2, "the failing read")
        wake.set()
        await asyncio.sleep(0.3)
        assert len(reads) == 2
        assert not watcher.done()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelling_a_watcher_waiting_on_its_wake_joins_both_waits():
    wake = asyncio.Event()
    reads, load = _counting_load()
    before = asyncio.all_tasks()
    watcher = await _watch(load, wake)
    await _until(lambda: len(reads) == 1, "the baseline read")
    await asyncio.sleep(0.05)
    watcher.cancel()
    await asyncio.gather(watcher, return_exceptions=True)
    assert watcher.cancelled()
    assert {t for t in asyncio.all_tasks() - before if not t.done()} == set()


# ----------------------------------------------- the ticker's wake ----


async def _accepted_quote(ns):
    await ns["handle_ticker"](dict(
        market_ticker=TICKER, price_dollars=".80",
        yes_bid_dollars=".66", yes_ask_dollars=".70",
    ))


@pytest.mark.asyncio
async def test_only_a_first_quote_outside_the_live_set_wakes():
    ns = handler(None)
    wake = ns["admission_wake"]
    await _accepted_quote(ns)
    assert wake.is_set()  # first quote, event 900 not live

    wake.clear()
    await _accepted_quote(ns)
    assert not wake.is_set()  # same-event chatter

    ns["winner_quoted_at"][900] -= task.QUOTE_PRIORITY_EVIDENCE_SECONDS + 1
    await _accepted_quote(ns)
    assert wake.is_set()  # quotes again after its evidence expired

    live = handler(None)
    live["live_event_ids"].add(900)
    await _accepted_quote(live)
    assert not live["admission_wake"].is_set()  # already prioritised

    prop = handler(None, non_blend=(81,))
    await _accepted_quote(prop)
    assert not prop["admission_wake"].is_set()  # not a winner leg
