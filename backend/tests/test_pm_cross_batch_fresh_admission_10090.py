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
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("preview_redis")]


@pytest.fixture
async def preview_redis(redis_kwargs, monkeypatch):
    """Default DNPL admission/settlement uses its real, isolated Redis ledger."""
    from redis.asyncio import Redis

    client = Redis(**redis_kwargs)
    monkeypatch.setattr(blend.LiveBlendRefresher, "_client", lambda self: client)
    try:
        yield client
    finally:
        await client.aclose()


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
async def test_next_batch_same_event_write_or_withdrawal_waits_buffered_for_old_owner(
    monkeypatch, withdrawal
):
    # #10090: event 1's stamp is still running. Its newer price or wide book
    # neither lands under that read nor holds the batch: it stays buffered,
    # and the first flush after the stamp returns writes it.
    p, x, _ = cross_batch(monkeypatch)
    assert await p.ns["flush_prices"](flush_started=1000)
    if withdrawal:
        p.books[1] = (0.2, 0.8)
    else:
        p.ns["price_buffer"].update({1: 0.5, 2: 0.5})
    try:
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1001), 2)
        assert 1 not in x.committed and not x.release.is_set()
        assert p.trace.count(("write", [1, 2])) == 1
        assert ("withdraw", [1]) not in p.trace
        if withdrawal:
            assert p.books == {1: (0.2, 0.8)}
        else:
            assert p.ns["price_buffer"] == {1: 0.5, 2: 0.5}
        assert p.ns["stats"]["stamp_fenced"] == (1 if withdrawal else 2)
    finally:
        await finish(p, x)
    assert x.published == [1]
    assert await p.ns["flush_prices"](flush_started=1002)
    await p.ns["catalog_boundary"].join_stamps()
    frame = p.trace.index(("event_frame", 1))
    if withdrawal:
        assert frame < p.trace.index(("withdraw", [1]))
        assert not p.books
    else:
        writes = [i for i, step in enumerate(p.trace) if step == ("write", [1, 2])]
        assert len(writes) == 2 and frame < writes[1]
        assert not p.ns["price_buffer"]
    # The re-stamp reads the rig's unchanged board, so it owes no new frame.
    assert not x.r.pending_event_ids() and x.r.stats["errors"] == 0


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
    # The timed flush retains its stamp owner across the real ledger I/O.
    # Observe the completed owner, not an incidental no-I/O scheduling turn.
    await p.ns["catalog_boundary"].join_stamps()
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
                "prop_task",
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
    # The periodic flush and final drain must share the same clock.
    monkeypatch.setattr(blend, "_mono", lambda: 1000.0)
    p, x, later = cross_batch(monkeypatch)
    unwinding, unwind = asyncio.Event(), asyncio.Event()
    factory = x.r._session_factory

    @asynccontextmanager
    async def slow_unwind():
        async with factory() as session:
            try:
                yield session
            finally:
                if 1 in getattr(session, "event_ids", ()) and asyncio.current_task().cancelling():
                    unwinding.set()
                    await unwind.wait()

    x.r._session_factory = slow_unwind
    assert await p.ns["flush_prices"](flush_started=1000)
    # Cancellation must hit the held price transaction, after DNPL's ledger
    # admission read, rather than cancel an owner still preparing its read.
    await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
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
                "prop_task",
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


async def test_a_tail_withdrawal_stamp_takes_the_running_calls_free_worker(monkeypatch):
    # #10090: a later batch carries only a wide book on event 2's leg. Its
    # withdrawal commits at the tail; event 2's stamp joins the running call
    # (event 1's stamp still held) instead of the batch joining that whole
    # call and then stamping inline.
    p, x, later = cross_batch(monkeypatch)
    first = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await settle_until(first.done)
        assert first.result() is True and not x.release.is_set()
        assert await p.ns["write_chunk"](later)  # stored earlier, already stamped
        calls = []
        admit = x.r.admit_fresh

        def record(ids, **kwargs):
            owned = admit(ids, **kwargs)
            calls.append((set(ids), owned))
            return owned

        x.r.admit_fresh = record
        p.books[900] = (0.01, 0.99)
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1001), 2)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.committed and not x.release.is_set()
        assert ("withdraw", [900]) in p.trace
        assert calls == [({2}, frozenset({2}))]
    finally:
        x.release.set()
        await asyncio.gather(first, return_exceptions=True)
        await finish(p, x)
    assert x.published == [2, 1] and not x.r.pending_event_ids()
    assert x.r.stats["errors"] == 0


async def test_a_held_games_tick_in_the_same_chunk_does_not_hold_an_independent_game(
    monkeypatch,
):
    # #10090 post-v5710 residual: one 500-row chunk carries the slate, so any
    # tick of a game whose stamp is still running joined that WHOLE refresh
    # before the write, and every independent game in the chunk waited too.
    p, x, later = cross_batch(monkeypatch)
    assert await p.ns["flush_prices"](flush_started=1000)
    p.ns["price_buffer"].update({1: 0.5, 2: 0.5, **later})
    try:
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1001), 2)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.committed and not x.release.is_set()
        assert ("write", [900, 901]) in p.trace
        assert p.ns["price_buffer"] == {1: 0.5, 2: 0.5}  # fenced, not dropped
    finally:
        await finish(p, x)
    assert await p.ns["flush_prices"](flush_started=1002)
    await p.ns["catalog_boundary"].join_stamps()
    assert p.trace.count(("write", [1, 2])) == 2 and not p.ns["price_buffer"]
    assert x.published == [2, 1] and not x.r.pending_event_ids()


async def test_the_fence_and_the_remaining_join_wait_reach_the_minute_line(caplog):
    from app.tasks import polymarket_ws as poly_task

    stats = {"price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0,
             "stamp_fenced": 3, "stamp_wait_s": 1.26}
    blend_stats = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level("INFO", logger=poly_task.logger.name):
        poly_task._log_stats_line(stats, {}, blend_stats)
    assert "fenced=3 stamp_wait_s=1.3" in caplog.text


async def test_the_owner_counts_only_time_spent_waiting_on_a_running_refresh():
    from app.tasks.polymarket_ws import _PMStampOwner

    owner = _PMStampOwner(refresher=None)
    owner.task = asyncio.create_task(asyncio.sleep(0.05))
    await owner.join()
    waited = owner.waited_s
    assert 0.04 <= waited < 1
    owner.task = asyncio.create_task(asyncio.sleep(0))
    await asyncio.sleep(0.01)  # already finished: a reap, not a wait
    await owner.join()
    assert owner.waited_s - waited < 0.005


@pytest.mark.parametrize("fenced_tick", [False, True])
async def test_a_quiet_batch_hands_due_debt_to_the_running_call_without_joining(
    monkeypatch, fenced_tick,
):
    # #10090 repeat tail: event 1's stamp is held and event 2 owes a stamp. A
    # quiet batch that joined the call held every later flush behind the held
    # stamp; now it returns, and the call's door takes the due debt, which
    # publishes while event 1 is still held. fenced_tick: the batch carries
    # only the held event's newer prices, which the fence keeps buffered (the
    # second quiet path).
    p, x, later = cross_batch(monkeypatch)
    first = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await settle_until(first.done)
        assert first.result() is True and not x.release.is_set()
        assert await p.ns["write_chunk"](later)  # stored; its stamp is owed
        x.r.adopt_pending([2])
        if fenced_tick:
            p.ns["price_buffer"].update({1: 0.5, 2: 0.5})
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1001), 2)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.committed and not x.release.is_set()
        assert not x.r.pending_event_ids()
        if fenced_tick:
            assert p.ns["price_buffer"] == {1: 0.5, 2: 0.5}
    finally:
        x.release.set()
        await asyncio.gather(first, return_exceptions=True)
        await finish(p, x)
    assert await p.ns["flush_prices"](flush_started=1002)
    await p.ns["catalog_boundary"].join_stamps()
    assert x.published[:2] == [2, 1] and not x.r.pending_event_ids()
    assert not p.ns["price_buffer"] and x.r.stats["errors"] == 0


async def test_a_tail_cohort_still_being_written_is_kept_owed_without_joining(monkeypatch):
    # #10090 repeat tail (replay 31.8 s, 1.4 s): event 2's withdrawal commits at
    # the tail while a newer wide book for its leg arrives inside that
    # transaction, so this flush is still writing event 2 and admission refuses
    # it (`defer_event_ids`). The joined refresh could only defer it; joining
    # waited out the WHOLE running call (event 1's stamp held).
    p, x, later = cross_batch(monkeypatch)
    first = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await settle_until(first.done)
        assert first.result() is True and not x.release.is_set()
        assert await p.ns["write_chunk"](later)
        withdraw = p.ns["withdraw_book_refuted_prices"]

        async def newer_book_arrives(session, selected):
            p.ns["withdraw_book_refuted_prices"] = withdraw  # once
            rows = await withdraw(session, selected)
            p.books[900] = (0.02, 0.98)
            return rows

        p.ns["withdraw_book_refuted_prices"] = newer_book_arrives
        calls = []
        admit = x.r.admit_fresh

        def record(ids, **kwargs):
            owned = admit(ids, **kwargs)
            calls.append((set(ids), set(kwargs["defer_event_ids"]), owned))
            return owned

        x.r.admit_fresh = record
        p.books[900] = (0.01, 0.99)
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1001), 2)
        assert 1 not in x.committed and not x.release.is_set()
        assert ("withdraw", [900]) in p.trace
        assert calls == [({2}, {2}, frozenset())]  # refused: still being written
        assert x.r.pending_event_ids() == frozenset({2}) and 2 not in x.published
        assert p.books == {900: (0.02, 0.98)}
    finally:
        x.release.set()
        await asyncio.gather(first, return_exceptions=True)
        await finish(p, x)
    assert await p.ns["flush_prices"](flush_started=1002)
    await p.ns["catalog_boundary"].join_stamps()
    assert p.trace.count(("withdraw", [900])) == 2 and not p.books
    assert x.published[:2] == [1, 2] and not x.r.pending_event_ids()
    assert x.r.stats["errors"] == 0


async def test_keep_owed_records_the_debt_a_deferring_refresh_records(monkeypatch):
    from tests.test_single_event_commit_10090 import rig as stamp_rig

    r = stamp_rig(monkeypatch, count=2).r
    receipts = r.receipts = blend.TailReceipts("polymarket")
    receipts._live_events = {1, 2}
    mark = blend.InputMark(
        seq=7, event_id=2, outcome_id=900, probability=0.7, kind="price",
        recv_wall=1007, recv_mono=107, venue_ts_ms=None, event_ordinal=7,
    )
    other = blend.InputMark(
        seq=8, event_id=1, outcome_id=1, probability=0.6, kind="price",
        recv_wall=1008, recv_mono=108, venue_ts_ms=None, event_ordinal=8,
    )
    staged = (receipts._staged, receipts._staged_wall)
    before = r.stats["throttled"]
    r.keep_owed({2}, marks=[mark, other])
    r.keep_owed([2])
    assert r.pending_event_ids() == frozenset({2})
    assert r.stats["throttled"] == before + 1  # once per owed event
    assert set(receipts._open) == {2}  # the cohort's input opens its chain
    assert (receipts._staged, receipts._staged_wall) == staged  # slot untouched


def held_admission(monkeypatch, *, games):
    """The real PM flush driving the real refresher, Root's closed-admission
    shape: game n's single leg is outcome 10*n; game 2's UPDATE is held until
    ``x.release``; ``gates[n]`` holds game n's stamp before it starts."""
    from tests import test_polymarket_withdrawal_speed_10651 as fixtures
    from tests.test_single_event_commit_10090 import rig as stamp_rig

    values = {n: round(0.5 + n / 20, 2) for n in range(1, games + 1)}
    p = fixtures.rig(
        batch={10: values[1]}, mapping={10 * n: n for n in values}, books={},
    )
    p.release.set()
    x = stamp_rig(monkeypatch, count=games, block=True, blocked=(2,))
    p.ns["blend_refresher"] = x.r
    receipts = p.ns["tail_receipts"] = x.r.receipts = blend.TailReceipts("polymarket")
    p.ns["input_marks"] = {
        10 * n: blend.InputMark(
            seq=n, event_id=n, outcome_id=10 * n, probability=value, kind="price",
            recv_wall=1000 + n, recv_mono=100 + n, venue_ts_ms=None, event_ordinal=n,
        )
        for n, value in values.items()
    }

    async def no_market_publish(session):
        return 0

    x.r.publish_market_changes = no_market_publish
    gates = {n: (asyncio.Event(), asyncio.Event()) for n in (1, 3)}  # entered, release
    batch = x.r._refresh_batch

    async def gated(ids, *a, **kw):
        if len(ids) == 1 and ids[0] in gates:
            entered, release = gates[ids[0]]
            entered.set()
            await release.wait()
        return await batch(ids, *a, **kw)

    x.r._refresh_batch = gated
    return p, x, receipts, values, gates


async def own_done_with_game_2_held(p, x, values, gates):
    """Game 1's own stamp returns while admitted game 2's stamp is held."""
    assert await p.ns["flush_prices"](flush_started=1000)
    await asyncio.wait_for(gates[1][0].wait(), 1)
    p.ns["price_buffer"][20] = values[2]
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.25), 1)
    await asyncio.wait_for(x.second_stamp.wait(), 1)
    gates[1][1].set()
    await settle_until(lambda: x.r._admission is not None and x.r._admission.own_done)
    assert x.r.holding_event_ids() == frozenset({2}) and x.published == [1]


async def release_all(p, x, gates):
    x.release.set()
    for _, release in gates.values():
        release.set()
    await p.ns["catalog_boundary"].join_stamps()


async def test_an_unrelated_price_publishes_while_an_admitted_holder_outlives_own_done(
    monkeypatch,
):
    # #10090, Root's closed-admission counterexample (1.504 s FAIL on a23a6c9680):
    # event 1's own stamp returns while admitted event 2's stamp is still held.
    # The call still admits, so event 3's committed price joins it and
    # publishes before event 2's holder lets go, instead of waiting it out. Its
    # mark stays the admission's own; the staging slot is untouched.
    p, x, receipts, values, gates = held_admission(monkeypatch, games=3)
    gates[3][1].set()  # game 3's stamp is not held here
    try:
        await own_done_with_game_2_held(p, x, values, gates)
        window = x.r._admission
        assert x.r.admitting()
        slot = (receipts._staged, receipts._staged_wall)
        p.ns["price_buffer"][30] = values[3]
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.5), 1)
        await settle_until(lambda: 3 in x.published)
        assert not x.release.is_set() and 2 not in x.committed  # holder still held
        assert window.staged[3].seq == 3 and x.r.admitting()
        assert (receipts._staged, receipts._staged_wall) == slot
    finally:
        await release_all(p, x, gates)
    assert x.published == [1, 3, 2] and not p.ns["price_buffer"]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_an_unrelated_price_publishes_while_a_successor_holder_is_held(monkeypatch):
    # #10090, Root's successor counterexample (1.506 s FAIL on 317dc06135, a
    # fixed frontier): game 3 is admitted and held; game 2's holder then lets
    # go; game 4's price arrives while game 3 is still held. Overlapping
    # holders never shut an unrelated game out: game 4 publishes first.
    p, x, receipts, values, gates = held_admission(monkeypatch, games=4)
    try:
        await own_done_with_game_2_held(p, x, values, gates)
        p.ns["price_buffer"][30] = values[3]
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.5), 1)
        await asyncio.wait_for(gates[3][0].wait(), 1)
        x.release.set()
        await settle_until(lambda: 2 in x.published)
        assert x.r.holding_event_ids() == frozenset({3}) and x.r.admitting()
        p.ns["price_buffer"][40] = values[4]
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000.75), 1)
        await settle_until(lambda: 4 in x.published)
        assert not gates[3][1].is_set() and 3 not in x.published
    finally:
        await release_all(p, x, gates)
    assert x.published == [1, 2, 4, 3] and not p.ns["price_buffer"]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_a_join_is_a_lifecycle_drain_that_stops_admission_first(monkeypatch):
    # #10090: the call keeps admitting; any join (final, cancellation, catalog,
    # a refused fallback) closes its door before it waits, so the wait is
    # bounded by what is already queued, never by a later arrival.
    p, x, receipts, values, gates = held_admission(monkeypatch, games=3)
    gates[3][1].set()
    try:
        await own_done_with_game_2_held(p, x, values, gates)
        joining = asyncio.create_task(p.ns["catalog_boundary"].join_stamps())
        await settle_until(lambda: not x.r.admitting())
        assert not joining.done()
        assert x.r.admit_fresh([3], flush_started=1000.5) == frozenset()
        x.release.set()
        await asyncio.wait_for(joining, 2)
    finally:
        await release_all(p, x, gates)
    assert x.published == [1, 2] and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_the_write_fence_covers_owed_events_the_call_took_later(monkeypatch):
    # #10090, Root's fence counterexample on be0d6a8a: an owed event the call
    # takes after it started (`window.debt`) is in the refresher's holding but
    # not in the owner's captured membership; `held_events` returned {1}, so a
    # later write or withdrawal to event 2 could cross its live stamp.
    from app.tasks.polymarket_ws import _PMStampOwner
    from tests.test_single_event_commit_10090 import rig as stamp_rig

    x = stamp_rig(monkeypatch, count=2, block=True, blocked=(1, 2))
    owner = _PMStampOwner(x.r)
    owner.events = {1}
    owner.task = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: x.r._admission is not None)
        x.r.adopt_pending({2})
        assert x.r.admit_fresh((), flush_started=1000.25) == frozenset()
        await asyncio.wait_for(x.second_stamp.wait(), 1)
        assert x.r.holding_event_ids() == frozenset({1, 2})
        assert owner.held_events() == {1, 2}
    finally:
        x.release.set()
        await owner.join()
