"""#10090 — a quiet flush hands owed stamps to the one stamp owner and returns.

Before this change a flush with no new speaking prices awaited
`refresh_pending` inline. When the owed event's stamp waited on its row lock,
that flush could not return, so the cadence started no flush and an unrelated
game's fresh quote waited behind it (Root, real PostgreSQL: 0.81 s vs 0.13 s).

Now a timed quiet flush starts `refresh_pending` as the persistent owner's
task (as a fresh chunk starts `refresh`) and returns; the next flush writes the
unrelated quote and admits it beside the held stamp. The final drain, untimed
calls and calls with nothing owed still await inline.

On the existing `paired` fixture: the actual flush closures and a real
`LiveBlendRefresher` whose event-1 stamp parks until `x.release`.
"""

import asyncio

import pytest

from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio


async def quiet(p, *keep):
    """Event 1's cohort is already written (so its stamp is owed debt, not a
    fresh input); the buffer then holds only `keep`, so the next flush has no
    speaking price."""
    assert await p.ns["write_chunk"]({1: 0.6, 2: 0.4})
    for oid in [o for o in p.ns["price_buffer"] if o not in keep]:
        p.ns["price_buffer"].pop(oid)
        p.ns["input_marks"].pop(oid, None)


async def drain(p, x):
    x.release.set()
    await p.ns["catalog_boundary"].join_stamps()


@pytest.mark.parametrize("branch", ["empty-batch", "nothing-written-batch"])
async def test_a_quiet_flush_returns_while_owed_debt_waits_and_a_peer_publishes(
    monkeypatch, branch,
):
    """Both quiet endings of `_flush_prices`: no price at all, and a batch that
    wrote nothing (event 2's whole cohort lock-deferred, so nothing is owed).
    A written prop price is not this path: the chunk loop already hands the
    debt to a detached `refresh` there."""
    p, x = paired(monkeypatch, blocked=(1,))
    deferred = {"on": False}
    if branch == "empty-batch":
        await quiet(p)
    else:
        await quiet(p, 900, 901)
        deferred["on"] = True
        write = p.ns["write_chunk"]

        async def lock_held(chunk, **kwargs):
            if deferred["on"] and 900 in chunk:
                return None  # a lock-held whole chunk (`write_chunk`'s None)
            return await write(chunk, **kwargs)

        p.ns["write_chunk"] = lock_held
    x.r.keep_owed({1})
    owner = p.ns["catalog_boundary"].stamp_owner(x.r)
    try:
        # Before: this awaited event 1's parked stamp and never returned.
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.0), 1)
        if branch == "nothing-written-batch":
            assert p.ns["price_buffer"] == {900: 0.7, 901: 0.3}  # not written
        # The owed membership was captured before the call took the debt, and
        # none of it is fresh input.
        assert owner.events == {1} and owner.fresh == set()
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        assert owner.task is not None and not owner.task.done()
        assert owner.held_events() == {1}
        assert 1 not in x.published
        # An unrelated game's fresh quote writes and publishes beside it.
        deferred["on"] = False
        p.ns["price_buffer"].update({900: 0.71, 901: 0.29})
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.published and not x.release.is_set()
    finally:
        await drain(p, x)
    # The owed event recovers once its holder lets go; nothing stays owed.
    assert 1 in x.published
    assert not x.r.pending_event_ids()
    assert x.r.stats["errors"] == 0


async def test_a_newer_quote_for_the_owed_event_stays_fenced_behind_its_stamp(
    monkeypatch,
):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    x.r.keep_owed({1})
    try:
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.0), 1)
        # The very next flush carries a newer event-1 pair: it must not be
        # written beside the owed stamp that still holds event 1.
        p.ns["price_buffer"].update({1: 0.64, 2: 0.36})
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
        assert p.ns["stats"]["stamp_fenced"] == 2
        assert ("write", [1, 2]) not in p.trace[1:]
        assert p.ns["price_buffer"] == {1: 0.64, 2: 0.36}
    finally:
        await drain(p, x)
    # Released: the next flush writes and stamps the newer pair.
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.5), 1)
    await p.ns["catalog_boundary"].join_stamps()
    assert not p.ns["price_buffer"] and not x.r.pending_event_ids()
    # Written once (the setup's write is the other), only after the release.
    assert p.trace.count(("write", [1, 2])) == 2
    assert 1 in x.published


async def test_cancelled_at_the_handoff_yield_joins_the_owner_and_keeps_the_debt(
    monkeypatch,
):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    x.r.keep_owed({1})
    owner = p.ns["catalog_boundary"].stamp_owner(x.r)
    flush = asyncio.create_task(p.ns["flush_prices"](flush_started=1000.0))
    try:
        # The owner task exists: the flush is now suspended at its one-turn yield.
        await settle_until(lambda: owner.task is not None)
        started = owner.task
        flush.cancel()
        with pytest.raises(asyncio.CancelledError):
            await flush
        assert started.done() and owner.task is None
        assert owner.fenced == set()
        assert 1 in x.r.pending_event_ids(), "a cancelled hand-off keeps the debt"
        assert 1 not in x.published
    finally:
        flush.cancel()
        x.release.set()
        await asyncio.gather(flush, return_exceptions=True)
    # The next ordinary flush picks the debt up again.
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
    await p.ns["catalog_boundary"].join_stamps()
    assert 1 in x.published and not x.r.pending_event_ids()


async def test_cancelled_while_the_owed_stamp_waits_keeps_the_debt(monkeypatch):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    x.r.keep_owed({1})
    flush = asyncio.create_task(p.ns["flush_prices"](flush_started=1000.0))
    try:
        # Before: the quiet flush awaited the parked stamp and never returned.
        assert await asyncio.wait_for(asyncio.shield(flush), 1)
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        await p.ns["catalog_boundary"].join_stamps(cancel=True)
        assert 1 in x.r.pending_event_ids()
        assert not p.ns["catalog_boundary"].flush_wake.is_set()
    finally:
        x.release.set()
        await asyncio.wait_for(flush, 1)
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
    await p.ns["catalog_boundary"].join_stamps()
    assert 1 in x.published and not x.r.pending_event_ids()


@pytest.mark.parametrize("call", ["final", "untimed"])
async def test_the_final_drain_and_untimed_calls_still_await_the_owed_stamp(
    monkeypatch, call,
):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    x.r.keep_owed({1})
    kwargs = {"final": True} if call == "final" else {}
    flush = asyncio.create_task(p.ns["flush_prices"](**kwargs))
    try:
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        for _ in range(20):
            await asyncio.sleep(0)
        assert not flush.done(), "no later flush would finish a detached stamp"
        assert p.ns["catalog_boundary"].stamp_owner(x.r).task is None
    finally:
        x.release.set()
        await asyncio.wait_for(flush, 1)
    assert 1 in x.published and not x.r.pending_event_ids()


async def test_a_quiet_flush_with_nothing_owed_starts_no_owner(monkeypatch):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    owner = p.ns["catalog_boundary"].stamp_owner(x.r)
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.0), 1)
    assert owner.task is None and not x.sessions


# Root's two narrow owner-boundary controls (quiet-debt-check/test_owner_boundaries.py,
# OWNER-BOUNDARIES-RECEIPT.json), carried in verbatim.


async def test_cancel_before_owner_body_starts_retains_committed_debt(monkeypatch):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    x.r.keep_owed({1})
    owner = p.ns["catalog_boundary"].stamp_owner(x.r)
    entered = False
    original_pending = x.r.refresh_pending

    async def marked_pending(*args, **kwargs):
        nonlocal entered
        entered = True
        return await original_pending(*args, **kwargs)

    original_create = asyncio.create_task
    cancelled = []

    def cancel_before_schedule(coro, *args, **kwargs):
        task = original_create(coro, *args, **kwargs)
        if getattr(coro, "cr_code", None) is marked_pending.__code__:
            # Synchronous cancellation: neither the new owner nor the caller
            # can run again until this interception returns to the event loop.
            task.cancel()
            cancelled.append(task)
            asyncio.current_task().cancel()
        return task

    with monkeypatch.context() as m:
        m.setattr(x.r, "refresh_pending", marked_pending)
        m.setattr(asyncio, "create_task", cancel_before_schedule)
        flush = original_create(p.ns["flush_prices"](flush_started=1000.0))
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(flush, 1)
    assert len(cancelled) == 1 and cancelled[0].cancelled()
    assert not entered, "this control must cancel before the owner body executes"
    assert owner.task is None and not owner.fenced
    assert x.r.pending_event_ids() == {1}
    assert not x.sessions and not x.published
    x.release.set()
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
    await asyncio.wait_for(p.ns["catalog_boundary"].join_stamps(), 1)
    assert x.published == [1] and not x.r.pending_event_ids()


async def test_peer_admission_does_not_start_a_second_mutable_refresh(monkeypatch):
    p, x = paired(monkeypatch, blocked=(1,))
    await quiet(p)
    x.r.keep_owed({1})
    active = maximum = calls = 0
    original_refresh = x.r.refresh

    async def counted_refresh(*args, **kwargs):
        nonlocal active, maximum, calls
        active += 1
        calls += 1
        maximum = max(maximum, active)
        try:
            return await original_refresh(*args, **kwargs)
        finally:
            active -= 1

    monkeypatch.setattr(x.r, "refresh", counted_refresh)
    try:
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.0), 1)
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        p.ns["price_buffer"].update({900: 0.71, 901: 0.29})
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.published and not x.release.is_set()
        assert active == maximum == calls == 1
    finally:
        x.release.set()
        await asyncio.wait_for(p.ns["catalog_boundary"].join_stamps(), 1)
    assert active == 0 and maximum == calls == 1
    assert x.published == [2, 1] and not x.r.pending_event_ids()
