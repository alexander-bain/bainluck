"""#10090 — an event that quotes BEFORE its start gets live priority at its
start, not at the next 30 s admission check.

f7163836bf wakes the admission reread on an event's FIRST winner quote in the
90 s evidence window. A game whose winner legs trade before kickoff takes that
wake while it is still refused (the window requires a passed start); its
quotes then keep the evidence fresh, so crossing its start wakes nothing and
the lift waited for the periodic 30 s reread. Now the same quote-priority read
also returns, for otherwise-eligible events starting before the next check,
seconds-to-start on the database's clock; the existing watcher brings its next
reread forward to the soonest one (never inside the 5 s cooldown), and that
reread validates as before. The due time lifts nothing on its own.

The decisive control runs the actual consumer with a 30 s check: refused
before the start, quotes spanning the start, book open just after it. The rest
pin the bounds — a start beyond the next check, or an event refused at its
start, reads no more; the watcher's due time shortens only its wait.
"""

import asyncio
import time

import pytest

import app.tasks.kalshi_ws as task
import app.tasks.ws_admission as admission
from tests.test_kalshi_changed_scope_continuity_10090 import (
    GAME_A, _rig, _stop, _until,
)
from tests.test_kalshi_quote_priority_10090 import (
    SuspendedScope, _book_command, _quote,
)


def _slow_checks(monkeypatch, cooldown=0.05):
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 30)
    monkeypatch.setattr(admission, "ADMISSION_WAKE_COOLDOWN_SECONDS", cooldown)


async def _quote_until(game, predicate, what, every=0.1, limit=50):
    """Keep the winner leg quoting (no evidence gap) until ``predicate``."""
    for _ in range(limit):
        if predicate():
            return
        await _quote(game)
        await asyncio.sleep(every)
    raise AssertionError(f"timed out waiting for {what}")


async def _started(monkeypatch, scope):
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    running, _sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    _slow_checks(monkeypatch)
    await _until(lambda: opened_sockets() == 3, "startup sockets")
    await asyncio.sleep(0.2)
    return running, socket_for({GAME_A})


@pytest.mark.asyncio
async def test_quotes_before_the_start_get_the_book_at_the_start_not_the_next_tick(
    monkeypatch,
):
    scope = SuspendedScope(window=True, starts_at=time.monotonic() + 30)
    running, game = await _started(monkeypatch, scope)
    try:
        scope.starts_at = time.monotonic() + 1.0
        await _quote(game)
        await _until(lambda: len(scope.quote_reads) == 1, "the woken, refused read")
        assert _book_command(game) is None  # quoting, but not started
        assert "INTERVAL '30 seconds'" in scope.quote_reads[0]

        await _quote_until(game, lambda: _book_command(game) is not None,
                           "the book after the start")
        opened = time.monotonic()
        assert opened >= scope.starts_at  # never lifted before its start
        assert opened - scope.starts_at < 1.0  # the 30 s check never fired
        assert _book_command(game)["params"]["market_tickers"] == [GAME_A]
        assert len(scope.quote_reads) == 2  # the refused read and the start's
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_a_start_beyond_the_next_check_reads_no_more(monkeypatch):
    scope = SuspendedScope(window=True, starts_at=time.monotonic() + 100)
    running, game = await _started(monkeypatch, scope)
    try:
        await _quote(game)
        await _until(lambda: len(scope.quote_reads) == 1, "the woken read")
        for _ in range(15):
            await _quote(game)
            await asyncio.sleep(0.1)
        assert len(scope.quote_reads) == 1
        assert _book_command(game) is None
    finally:
        await _stop(running)


@pytest.mark.asyncio
async def test_an_event_refused_at_its_start_reads_no_more(monkeypatch):
    """Settled or finished by its start: the start's read answers nothing,
    and its continuing quotes never read again."""
    scope = SuspendedScope(window=True, starts_at=time.monotonic() + 30)
    running, game = await _started(monkeypatch, scope)
    try:
        scope.starts_at = time.monotonic() + 0.5
        await _quote(game)
        await _until(lambda: len(scope.quote_reads) == 1, "the woken, refused read")
        scope.window = False
        await _quote_until(game, lambda: len(scope.quote_reads) == 2, "the start's read")
        for _ in range(10):
            await _quote(game)
            await asyncio.sleep(0.1)
        assert len(scope.quote_reads) == 2
        assert _book_command(game) is None
    finally:
        await _stop(running)


# ------------------------------------------------------ the watcher ----


def _counting_load(answers=None, dues=()):
    """Like the Kalshi reread: each successful read sets the next due time
    (``dues[i]`` seconds from now, or None); a failing read leaves it stale."""
    reads, due = [], {"at": None}
    dues = list(dues)

    async def load():
        reads.append(time.monotonic())
        answer = set()
        if answers is not None:
            answer = answers[min(len(reads), len(answers)) - 1]
            if isinstance(answer, Exception):
                raise answer
        after = dues.pop(0) if dues else None
        due["at"] = None if after is None else time.monotonic() + after
        return answer

    return reads, load, lambda: due["at"]


async def _watch(load, due, wake=None, cooldown=0.0, check=1000):
    return asyncio.create_task(admission.watch_for_unadmitted_live_events(
        load, [], arm="t", started_at=0.0, check_seconds=check,
        min_recycle_seconds=0, wake=wake, wake_cooldown_seconds=cooldown, due=due,
    ))


async def _cancel(watcher):
    watcher.cancel()
    await asyncio.gather(watcher, return_exceptions=True)


@pytest.mark.parametrize("wake", [None, asyncio.Event])
@pytest.mark.asyncio
async def test_a_due_time_brings_the_next_reread_forward_once(wake):
    reads, load, due = _counting_load(dues=[0.2])
    watcher = await _watch(load, due, wake=wake and wake())
    try:
        await _until(lambda: len(reads) == 2, "the due read")
        assert 0.19 <= reads[1] - reads[0] < 0.5
        await asyncio.sleep(0.3)  # that read found nothing starting
        assert len(reads) == 2
    finally:
        await _cancel(watcher)


@pytest.mark.asyncio
async def test_a_due_time_never_beats_the_cooldown():
    reads, load, due = _counting_load(dues=[-10, -10, -10])  # starts passed
    watcher = await _watch(load, due, cooldown=0.2)
    try:
        await _until(lambda: len(reads) >= 3, "due rereads")
        assert all(b - a >= 0.19 for a, b in zip(reads, reads[1:]))
    finally:
        await _cancel(watcher)


@pytest.mark.asyncio
async def test_after_a_failed_reread_a_due_time_does_not_hurry_the_next():
    reads, load, due = _counting_load([set(), RuntimeError("db down")], dues=[0.05])
    watcher = await _watch(load, due)
    try:
        await _until(lambda: len(reads) == 2, "the failing read")
        assert due() is not None and due() < time.monotonic()  # stale, passed
        await asyncio.sleep(0.3)
        assert len(reads) == 2
        assert not watcher.done()
    finally:
        await _cancel(watcher)


@pytest.mark.asyncio
async def test_a_due_reread_still_admits_a_newly_live_event():
    reads, load, due = _counting_load([set(), {901}], dues=[0.05])
    watcher = await _watch(load, due)
    assert await asyncio.wait_for(watcher, 2) == frozenset({901})


def test_the_read_widens_only_the_start_clause():
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket

    def sql(clause):
        return str(select(FuturesMarket.event_id).join(
            Event, FuturesMarket.event_id == Event.id).where(clause))

    plain, wide = sql(task._kalshi_quote_priority_window()), sql(
        task._kalshi_quote_priority_window(29.2))
    assert "events.commence_time <= NOW()" in plain
    assert wide == plain.replace("<= NOW()", "<= NOW() + INTERVAL '30 seconds'")
    assert "events.commence_time - now()" in str(task.quote_priority_starts_in())
