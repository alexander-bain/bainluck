"""#10090 — a slow stamp holds only its own event, never an independent one.

Ship: new live probabilities for an independent event keep reaching the
headline and chart while another event's refresh is slow.

Every case runs the real `flush_prices` with the real `LiveBlendRefresher`
(the `test_kalshi_fresh_admission_10090` rig: outcomes 1,2 -> game 1,
3 -> game 2, and 9 -> game 3 where three games play). Game 1's stamp is held
in its UPDATE.

1. THE SAME-EVENT FENCE JOINED THE WHOLE REFRESH. A flush carrying a new
   tick for game 1, whose stamp the running refresh still held, joined that
   refresh: every later phase, and every later flush, waited for game 1,
   independent games included. Now game 1's whole cohort stays buffered (like
   a lock retry) and the flush carries on; the first flush after game 1's
   stamp has returned writes it.

2. AN EVENT WHOSE STAMP HAD RETURNED STAYED FENCED FOR THE WHOLE REFRESH.
   Game 2's changed second quote could not be written or admitted until game
   1's held stamp returned. Now a returned stamp fences nothing: the newer
   price is written and admitted again, on its own flush's clock.

3. A QUIET FLUSH STAMPED OLD DEBT INLINE, so the next flush could not start.
   Now the debt runs as the run's refresh (`prices.stamping`).

Source/progress controls on fake storage, not production timing.
"""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks import kalshi_ws
from tests import test_kalshi_game_isolation_10655 as flush_fixtures
from tests.test_kalshi_fresh_admission_10090 import _caller as _admission_caller
from tests.test_single_event_commit_10090 import rig as refresher_rig, settle_until

pytestmark = pytest.mark.asyncio

_LIVE_PLAN = ("flush_budget_spent", "live_preempts_tail", "yield_written_nonlive_tail")


def _caller(monkeypatch, *, blocked):
    """The admission rig with games 1 and 2 live: the shipped live plan."""
    x, r = _admission_caller(monkeypatch, blocked=blocked)
    r.ns.update({name: getattr(kalshi_ws, name) for name in _LIVE_PLAN})
    r.ns["live_event_ids"] = {1, 2}
    return x, r


def _three_games(monkeypatch, *, blocked):
    """Games 1, 2, 3 live; each stamp reads its event's own ``reading``, so a
    changed quote is a changed stamp and frame (``frames``: id, value)."""
    x = refresher_rig(monkeypatch, count=3, block=True, blocked=blocked)
    r = flush_fixtures.rig()
    r.events.clear()
    r.events.update({1: 1, 2: 1, 3: 2, 9: 3})
    r.release.set()
    r.ns.update({name: getattr(kalshi_ws, name) for name in _LIVE_PLAN})
    r.ns["live_event_ids"] = {1, 2, 3}

    async def market_changes(session):
        r.trace.append(("publish", tuple(session.rows)))

    x.r.publish_market_changes = market_changes
    r.ns["blend_refresher"] = x.r
    reading = {1: 0.61, 2: 0.52, 3: 0.43}

    def read(group, home, away):
        return SimpleNamespace(
            home_probability=reading[group[0].market.event_id],
            away_probability=None, draw_probability=None, eligibility=None,
        )

    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", read)
    frames, publish = [], x.r._publish

    async def recorded(batch):
        await publish(batch)
        frames.extend((f["event_id"], f["source_value"]) for f in batch)

    x.r._publish = recorded
    return SimpleNamespace(x=x, r=r, reading=reading, frames=frames)


async def test_independent_live_game_is_not_held_behind_a_fenced_game(monkeypatch):
    x, r = _caller(monkeypatch, blocked=(1,))
    later_game_two = r.batch.pop(3)
    del r.batch[9]
    try:
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        assert r.committed == [1, 2] and x.committed == []
        # Game 1 ticks again (first in the buffer), then game 2.
        r.batch[1] = (.65, .64, .66)
        r.batch[3] = later_game_two
        assert await asyncio.wait_for(r.flush(1002.0), 2) is True
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [1, 2, 3], "game 1's new price is not written"
        assert 1 not in x.committed, "game 1's stamp is still held"
        assert set(r.batch) == {1}, "game 1's whole cohort stays buffered"
        assert r.stats["stamp_fenced"] == 1
        # A later flush while game 1 is still held leaves it buffered again.
        assert await asyncio.wait_for(r.flush(1004.0), 2) is True
        assert set(r.batch) == {1} and r.committed == [1, 2, 3]
    finally:
        x.release.set()
    await settle_until(lambda: 1 in x.published)
    # Its stamp returned: the next flush writes game 1's newest price.
    assert await asyncio.wait_for(r.flush(1006.0), 2) is True
    assert r.committed == [1, 2, 3, 1] and not r.batch
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert x.published[:2] == [2, 1]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_continuing_arrivals_and_a_changed_repeat_publish_while_one_game_is_held(
    monkeypatch,
):
    # Root's continuing-arrival case (1948Z), ported to the current source,
    # with the held-page repeat: game 3 arrives AFTER flush 1002 took its
    # snapshot, and game 2's quote CHANGES after its first stamp returned.
    g = _three_games(monkeypatch, blocked=(1,))
    x, r = g.x, g.r
    game_two, game_three = r.batch.pop(3), r.batch.pop(9)
    try:
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        r.batch[1] = (.65, .64, .66)
        r.batch[3] = game_two
        assert await asyncio.wait_for(r.flush(1002.0), 2) is True
        await settle_until(lambda: (2, 0.52) in g.frames)
        # New independent input after that snapshot, and game 2 moves.
        r.batch[9] = game_three
        r.batch[3] = (.75, .74, .76)
        g.reading[2], g.reading[3] = 0.58, 0.47
        assert await asyncio.wait_for(r.flush(1004.0), 2) is True
        await settle_until(lambda: (2, 0.58) in g.frames and (3, 0.47) in g.frames)
        assert 1 not in x.committed, "both before game 1 is released"
        assert [f for f in g.frames if f[0] == 2] == [(2, 0.52), (2, 0.58)]
        assert r.committed == [1, 2, 3, 9, 3] and set(r.batch) == {1}
        assert x.r._last_refresh_at[2] == 1004.0, "the repeat's own flush clock"
    finally:
        x.release.set()
    await settle_until(lambda: 1 in x.published)
    assert await asyncio.wait_for(r.flush(1006.0), 2) is True
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert r.committed[-1] == 1 and not r.batch
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_a_second_admission_is_refused_while_the_first_is_still_stamping(
    monkeypatch,
):
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=(1, 2))
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        assert x.r.holding_event_ids() == {1}
        assert x.r.admit_fresh([2], flush_started=1002) == {2}
        await settle_until(lambda: x.commands.count("update") == 2)
        assert x.r.holding_event_ids() == {1, 2}
        assert x.r.admit_fresh([2], flush_started=1004) == frozenset()
        assert x.r.admit_fresh([1], flush_started=1004) == frozenset()
    finally:
        x.release.set()
    await asyncio.wait_for(running, 2)
    assert sorted(x.published) == [1, 2] and x.r.stats["errors"] == 0


@pytest.mark.parametrize("boundary", ["before_first_turn", "in_update", "after_commit"])
async def test_a_second_admission_owes_its_own_attempt_at_every_cancellation(
    monkeypatch, boundary,
):
    # Game 2's first admitted stamp committed and was sent. Its second
    # admission is cancelled before it runs or inside its UPDATE: it stays
    # owed (the first completion pays nothing). Cancelled after its COMMIT,
    # the stamp is stored: nothing is owed, and none is lost.
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=(1,))
    reading = {1: 0.61, 2: 0.52}
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, home, away: SimpleNamespace(
            home_probability=reading[group[0].market.event_id],
            away_probability=None, draw_probability=None, eligibility=None,
        ),
    )
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        assert x.r.admit_fresh([2], flush_started=1002) == {2}
        await settle_until(lambda: 2 in x.published)
        reading[2] = 0.58  # its newer committed price reads differently
        await settle_until(lambda: all(t.done() for t in x.r._admission.workers))
        entered, execute = asyncio.Event(), x.Session.execute

        async def held_second_update(self, statement, *args, **kwargs):
            if (
                isinstance(statement, Update)
                and statement.compile().params["id_1"] == 2
            ):
                entered.set()
                await asyncio.Event().wait()
            return await execute(self, statement, *args, **kwargs)

        sending, publish = asyncio.Event(), x.r._publish

        async def held_send(frames):
            sending.set()
            await asyncio.Event().wait()

        if boundary == "in_update":
            monkeypatch.setattr(x.Session, "execute", held_second_update)
        elif boundary == "after_commit":
            x.r._publish = held_send
        if boundary == "before_first_turn":
            # The cancel is queued ahead of the new worker's first turn.
            running.cancel()
        assert x.r.admit_fresh([2], flush_started=1004) == {2}, "admitted again"
        if boundary == "in_update":
            await asyncio.wait_for(entered.wait(), 1)
        elif boundary == "after_commit":
            await asyncio.wait_for(sending.wait(), 1)
        if boundary != "before_first_turn":
            running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 2)
    finally:
        x.release.set()
    owed = {1} if boundary == "after_commit" else {1, 2}
    assert x.r.pending_event_ids() == frozenset(owed)
    assert x.committed.count(2) == (2 if boundary == "after_commit" else 1)
    assert not x.r._failed_hold_until and x.r._admission is None


async def test_quiet_flush_debt_stamp_does_not_hold_the_next_flush(monkeypatch):
    x, r = _caller(monkeypatch, blocked=(1,))
    later_game_two = r.batch.pop(3)
    r.batch.clear()
    x.r._lock_retry = {1}  # game 1's price is stored; its stamp is owed
    try:
        # A quiet flush pays the debt on the run's refresh and returns.
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        assert r.ns["prices"].stamping is not None
        assert r.ns["prices"].stamping_events == {1}
        assert r.ns["prices"].flush_work == 1
        r.batch[3] = later_game_two
        assert await asyncio.wait_for(r.flush(1002.0), 2) is True
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [3] and 1 not in x.committed, "game 1 still held"
    finally:
        x.release.set()
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert x.published == [2, 1]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_a_debt_stamp_still_fences_its_own_game_new_price(monkeypatch):
    # The debt a quiet flush started holds game 1: game 1's new price is not
    # written under that stamp's read, while game 2's cohort goes through.
    x, r = _caller(monkeypatch, blocked=(1,))
    later_game_two = r.batch.pop(3)
    r.batch.clear()
    x.r._lock_retry = {1}
    try:
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        r.batch[1] = (.65, .64, .66)
        r.batch[3] = later_game_two
        assert await asyncio.wait_for(r.flush(1002.0), 2) is True
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [3], "game 1's new price waits for its own stamp"
        assert set(r.batch) == {1}
    finally:
        x.release.set()
    await settle_until(lambda: 1 in x.published)
    assert await asyncio.wait_for(r.flush(1004.0), 2) is True
    assert r.committed == [3, 1]
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert x.published[:2] == [2, 1]
    assert not x.r.pending_event_ids() and x.r._admission is None


async def test_cancelled_quiet_flush_debt_stamp_stays_owed(monkeypatch):
    # Cancelled at the consumer's join (a scope change or before its final
    # drain), the debt a quiet flush started stays owed with no failed hold.
    x, r = _caller(monkeypatch, blocked=(1,))
    r.batch.clear()
    x.r._lock_retry = {1}
    assert await asyncio.wait_for(r.flush(1000.0), 2) is True
    await settle_until(lambda: "update" in x.commands)
    join = asyncio.create_task(r.ns["prices"].join_stamp(x.r))
    await asyncio.sleep(0)
    join.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(join, 2)
    assert r.ns["prices"].stamping is None and x.committed == []
    assert x.r.pending_event_ids() == frozenset({1})
    assert not x.r._failed_hold_until and x.r._admission is None


@pytest.mark.parametrize("turn", ["before_first_turn", "after_first_turn"])
async def test_a_quiet_flush_cancelled_at_its_yield_keeps_the_debt(monkeypatch, turn):
    # Cancellation delivered at the yield right after the debt task is created:
    # before its first turn (the debt never moved) or after UPDATE entry
    # (taken into the refresher, then cancelled with it). DNPL admission can
    # yield before UPDATE, so a single event-loop turn is not that witness.
    # Owed either way, no failed hold.
    x, r = _caller(monkeypatch, blocked=(1,))
    r.batch.clear()
    x.r._lock_retry = {1}
    update_entered = asyncio.Event()
    execute = x.Session.execute

    async def witnessed_execute(session, statement, *args, **kwargs):
        if isinstance(statement, Update):
            update_entered.set()
        return await execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(x.Session, "execute", witnessed_execute)

    async def cancelled_yield(delay, *args, **kwargs):
        if delay == 0 and turn == "after_first_turn":
            await update_entered.wait()
        raise asyncio.CancelledError

    r.ns["asyncio"] = SimpleNamespace(
        create_task=asyncio.create_task, sleep=cancelled_yield,
        CancelledError=asyncio.CancelledError,
    )
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(r.flush(1000.0), 2)
    assert r.ns["prices"].stamping is None
    assert ("update" in x.commands) == (turn == "after_first_turn")
    assert x.r.pending_event_ids() == frozenset({1}) and x.committed == []
    assert not x.r._failed_hold_until and x.r._admission is None


async def test_final_drain_quiet_flush_joins_a_running_stamp_then_stamps_its_debt(
    monkeypatch,
):
    # The drain has no next flush: neither a running stamp nor its own debt
    # stamp may outlive it.
    x, r = _caller(monkeypatch, blocked=(1,))
    r.batch.clear()
    x.r._lock_retry = {1}
    assert await asyncio.wait_for(r.flush(1000.0), 2) is True
    await settle_until(lambda: "update" in x.commands)
    x.r._lock_retry = {2}
    drain = asyncio.create_task(r.flush(final_drain=True))
    await asyncio.sleep(0.05)
    assert not drain.done(), "the drain waits for the running stamp"
    x.release.set()
    assert await asyncio.wait_for(drain, 2) is True
    assert r.ns["prices"].stamping is None
    assert sorted(x.published) == [1, 2] and not x.r.pending_event_ids()


@pytest.mark.parametrize("prior", ["completed", "failed"])
async def test_a_throttled_readmission_is_debt_not_an_unfinished_attempt(
    monkeypatch, prior,
):
    # Root 2010Z: game 2's earlier admitted attempt has returned (committed,
    # or failed); its newer price is admitted again but THROTTLED, so no new
    # attempt starts. A normal close must leave it owed as throttled debt,
    # never re-owe the retired attempt as cancelled on its old clock.
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=(1,))
    stamp = x.r._refresh_batch

    async def second_fails(ids, *args, **kwargs):
        if prior == "failed" and ids == [2]:
            raise RuntimeError("game 2's first admitted stamp failed")
        return await stamp(ids, *args, **kwargs)

    x.r._refresh_batch = second_fails
    recovered, refresh_failed = [], x.r._refresh_failed

    def spied(due, retry, clock, *args, **kwargs):
        recovered.append((sorted(due), clock))
        return refresh_failed(due, retry, clock, *args, **kwargs)

    x.r._refresh_failed = spied
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        assert x.r.admit_fresh([2], flush_started=1002) == {2}
        await settle_until(lambda: all(t.done() for t in x.r._admission.workers))
        assert recovered == ([([2], 1002)] if prior == "failed" else [])
        # Inside the floor (completed) or its failure hold (failed).
        x.r.min_refresh_interval_s = 10
        assert x.r.admit_fresh([2], flush_started=1004) == {2}, "taken, throttled"
        assert not x.r._admission.queue and 2 in x.r.pending_event_ids()
    finally:
        x.release.set()
    await asyncio.wait_for(running, 2)
    assert recovered == ([([2], 1002)] if prior == "failed" else []), (
        "a normal close re-owed the retired attempt"
    )
    assert 2 in x.r._throttle_deferred and x.r._admission is None
    assert (2 in x.r._failed_hold_until) == (prior == "failed")
