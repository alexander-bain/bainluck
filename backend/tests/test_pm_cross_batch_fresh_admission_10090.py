"""Actual PM caller + paired shared contract: next-batch COMMIT/frame progress.

PM_SHARED_SNAPSHOT optionally selects Live's immutable reviewed shared source
before composition. These controls measure ownership/order, never elapsed speed.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.tasks import live_blend_refresh as blend

if os.environ.get("PM_SHARED_SNAPSHOT"):
    snapshot = Path(os.environ["PM_SHARED_SNAPSHOT"])
    exec(compile(snapshot.read_text(), str(snapshot), "exec"), blend.__dict__)

from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_polymarket_withdrawal_speed_10651 import compile_functions
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio


def cross_batch(monkeypatch, **kwargs):
    p, x = paired(monkeypatch, **kwargs)
    if os.environ.get("PM_PARENT_SOURCE"):
        compile_functions(
            Path(os.environ["PM_PARENT_SOURCE"]),
            ["_flush_prices", "flush_prices"],
            p.ns,
        )
    later = {oid: p.ns["price_buffer"].pop(oid) for oid in (900, 901)}
    return p, x, later


async def finish(p, x):
    x.release.set()
    await p.ns["catalog_boundary"].join_stamps()


async def test_next_batch_commits_and_publishes_while_old_stamp_is_blocked(monkeypatch):
    p, x, later = cross_batch(monkeypatch)
    first = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        # The parent stays in its final stamp join and cannot start this batch.
        await settle_until(first.done)
        assert first.result() is True and not x.release.is_set()
        calls = []
        admit = x.r.admit_fresh

        def record(ids, **kwargs):
            owned = admit(ids, **kwargs)
            calls.append((set(ids), kwargs, owned))
            return owned

        x.r.admit_fresh = record
        p.ns["price_buffer"].update(later)
        assert await p.ns["flush_prices"](flush_started=1001)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.committed and not x.release.is_set()
        assert ("write", [900, 901]) in p.trace
        offered = calls[0][1]
        assert calls[0][0] == {2} and calls[0][2] == frozenset({2})
        assert offered["flush_started"] == 1001
        assert {m.outcome_id for m in offered["marks"]} == {900, 901}
        assert offered["defer_event_ids"] == set()
        assert x.r._last_refresh_at[2] == 1001
        assert p.ns["catalog_boundary"].stamps.task is not None
        assert x.r.stats["errors"] == 0
    finally:
        x.release.set()
        await asyncio.gather(first, return_exceptions=True)
        await finish(p, x)
    assert x.published == [2, 1] and not x.r.pending_event_ids()
    assert not p.ns["price_buffer"] and x.r._admission is None


@pytest.mark.parametrize("fail_last", [False, True])
async def test_later_batch_implicit_debt_waits_for_complete_cohort(
    monkeypatch, fail_last
):
    p, x, later = cross_batch(monkeypatch, split=True, fail_last=fail_last)
    assert await p.ns["flush_prices"](flush_started=1000)
    x.r.adopt_pending([2])
    p.ns["price_buffer"].update(later)
    entered, release = asyncio.Event(), asyncio.Event()
    original = p.ns["write_chunk"]

    async def last(chunk, **kwargs):
        if 901 in chunk:
            entered.set()
            await release.wait()
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = last
    task = asyncio.create_task(p.ns["flush_prices"](flush_started=1001))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert 900 not in p.ns["price_buffer"] and 901 in p.ns["price_buffer"]
        assert 2 not in x.published and 2 in x.r.pending_event_ids()
        release.set()
        if not fail_last:
            await settle_until(lambda: 2 in x.published)
            assert 1 not in x.committed
    finally:
        release.set()
        await finish(p, x)
        ok = await asyncio.wait_for(task, 2)
    assert ok is not fail_last
    if fail_last:
        assert 2 not in x.published and x.r.pending_event_ids() == frozenset({2})
        assert 901 in p.ns["price_buffer"]
    else:
        assert not x.r.pending_event_ids()


@pytest.mark.parametrize("withdrawal", [False, True])
async def test_next_batch_same_event_write_or_withdrawal_joins_old_owner(
    monkeypatch, withdrawal
):
    p, x, _ = cross_batch(monkeypatch)
    assert await p.ns["flush_prices"](flush_started=1000)
    if withdrawal:
        p.books[1] = (0.2, 0.8)
    else:
        p.ns["price_buffer"].update({1: 0.5, 2: 0.5})
    task = asyncio.create_task(p.ns["flush_prices"](flush_started=1001))
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        assert p.trace.count(("write", [1, 2])) == 1
        assert ("withdraw", [1]) not in p.trace
    finally:
        await finish(p, x)
        await asyncio.wait_for(task, 2)
    if withdrawal:
        assert p.trace.index(("event_frame", 1)) < p.trace.index(("withdraw", [1]))


async def test_quiet_batch_does_not_overlap_refresh_and_debt_progresses_after_join(
    monkeypatch,
):
    p, x, later = cross_batch(monkeypatch)
    assert await p.ns["flush_prices"](flush_started=1000)
    assert await p.ns["flush_prices"](flush_started=1001)
    assert 1 not in x.committed
    await finish(p, x)
    # These prices are already stored; a quiet batch owns only their debt.
    assert await p.ns["write_chunk"](later)
    x.r.adopt_pending([2])
    assert await p.ns["flush_prices"](flush_started=1002)
    assert x.published == [1, 2] and not x.r.pending_event_ids()


async def test_catalog_waits_for_repeated_cancel_cleanup_before_maps_change(
    monkeypatch,
):
    p, x, later = cross_batch(monkeypatch, blocked=(1, 2))
    unwinding, unwind, handed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    factory = x.r._session_factory

    @asynccontextmanager
    async def slow_unwind():
        async with factory() as session:
            try:
                yield session
            finally:
                if 2 in session.event_ids and asyncio.current_task().cancelling():
                    unwinding.set()
                    await unwind.wait()

    x.r._session_factory = slow_unwind
    assert await p.ns["flush_prices"](flush_started=1000)
    p.ns["price_buffer"].update(later)
    assert await p.ns["flush_prices"](flush_started=1001)
    await asyncio.wait_for(x.second_stamp.wait(), 2)

    async def handover():
        async with p.ns["catalog_boundary"].updating():
            handed.set()

    task = asyncio.create_task(handover())
    try:
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.wait_for(unwinding.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not handed.is_set()
        unwind.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert x.r.pending_event_ids() == frozenset({1, 2})
        assert x.r._admission is None
        assert p.ns["catalog_boundary"].stamps.task is None
    finally:
        unwind.set()
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)
        await finish(p, x)


async def test_final_drain_joins_the_stamp_it_starts_even_after_price_buffer_empties(
    monkeypatch,
):
    p, x, later = cross_batch(monkeypatch, blocked=(2,))
    assert await p.ns["flush_prices"](flush_started=1000)
    await finish(p, x)
    x.release.clear()
    p.ns["price_buffer"].update(later)
    compile_functions(
        Path(__file__).parents[1] / "app/tasks/polymarket_ws.py",
        ["drain_prices", "join_flushes_then_drain"],
        p.ns,
    )
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    p.ns.update(
        {
            name: done
            for name in (
                "flush_task",
                "standalone_task",
                "admission_task",
                "game_run_task",
            )
        }
    )
    p.ns.update(
        resolution_tasks=set(),
        open_run_task=None,
        FINAL_FLUSH_ATTEMPTS=3,
        LOOP_REAP_TIMEOUT_S=1,
        asyncio=asyncio,
    )
    task = asyncio.create_task(p.ns["join_flushes_then_drain"]())
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 2)
        assert not p.ns["price_buffer"] and not task.done()
        assert p.ns["catalog_boundary"].stamps.task is not None
        x.release.set()
        await asyncio.wait_for(task, 2)
        assert p.ns["catalog_boundary"].stamps.task is None
        assert x.published == [1, 2]
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)
        await finish(p, x)


async def test_repeated_shutdown_cancel_joins_old_owner_then_still_drains_prices(
    monkeypatch,
):
    p, x, later = cross_batch(monkeypatch)
    unwinding, unwind = asyncio.Event(), asyncio.Event()
    factory = x.r._session_factory

    @asynccontextmanager
    async def slow_unwind():
        async with factory() as session:
            try:
                yield session
            finally:
                if 1 in session.event_ids and asyncio.current_task().cancelling():
                    unwinding.set()
                    await unwind.wait()

    x.r._session_factory = slow_unwind
    assert await p.ns["flush_prices"](flush_started=1000)
    p.ns["price_buffer"].update(later)
    compile_functions(
        Path(__file__).parents[1] / "app/tasks/polymarket_ws.py",
        ["drain_prices", "join_flushes_then_drain"],
        p.ns,
    )
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    p.ns.update(
        {
            name: done
            for name in (
                "flush_task",
                "standalone_task",
                "admission_task",
                "game_run_task",
            )
        }
    )
    p.ns.update(
        resolution_tasks=set(),
        open_run_task=None,
        FINAL_FLUSH_ATTEMPTS=3,
        LOOP_REAP_TIMEOUT_S=1,
        asyncio=asyncio,
    )
    task = asyncio.create_task(p.ns["join_flushes_then_drain"]())
    try:
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.wait_for(unwinding.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and 900 in p.ns["price_buffer"]
        # The old transaction has cancelled; let its owed final retry finish.
        x.release.set()
        unwind.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert set(x.published) == {1, 2} and not p.ns["price_buffer"]
        assert p.ns["catalog_boundary"].stamps.task is None
        assert x.r._admission is None and not x.r.pending_event_ids()
    finally:
        unwind.set()
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)
        await finish(p, x)
