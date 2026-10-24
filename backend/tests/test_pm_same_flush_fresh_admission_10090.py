"""PM committed cohorts join the same flush's real refresh owner.

Run paired with Live's shared admission implementation. These controls execute
the shipped PM closures and real refresher through held database boundaries;
they prove frame ordering and ownership, not production/sub-second latency.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.tasks import live_blend_refresh as blend
from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig
from tests.test_single_event_commit_10090 import rig as stamp_rig, settle_until

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def cadence_redis(monkeypatch, private_redis_socket, caplog):
    """Keep DNPL's real ledger, but never borrow an ambient Redis server.

    Cadence controls fake their database and socket inputs. Their preview
    boundary must be equally explicit now that DNPL is enabled by default.
    The shared private-Redis fixture owns server startup before any timed work.
    """
    from redis.asyncio import Redis
    from redis.exceptions import ConnectionError as RedisConnectionError
    from app.tasks import redis_state
    from app.utils import blend_preview

    client = Redis(unix_socket_path=str(private_redis_socket))
    await client.ping()
    assert isinstance(blend_preview.registry(), blend_preview.LedgerRegistry)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: client)
    try:
        yield client
        assert not any(
            record.exc_info and isinstance(record.exc_info[1], (ConnectionError, RedisConnectionError))
            for record in caplog.get_records("call")
        ), "the cadence fixture must not depend on a missing external service"
    finally:
        await client.aclose()


def paired(monkeypatch, *, split=False, fail_last=False, blocked=(1,)):
    x = stamp_rig(monkeypatch, count=2, block=True, blocked=blocked)
    p = pm_rig(
        batch={1: 0.6, 2: 0.4, 900: 0.7, 901: 0.3},
        mapping={1: 1, 2: 1, 900: 2, 901: 2}, books={},
        failed_price=901 if fail_last else None,
    )
    p.release.set()
    if split:
        p.ns["FLUSH_CHUNK_ROWS"] = 1
    else:
        p.ns["open_complement_of"].update({900: 901, 901: 900})
    receipts = blend.TailReceipts("polymarket")
    p.ns["input_marks"] = {
        oid: blend.InputMark(
            seq=n, event_id=p.ns["event_id_by_outcome"][oid],
            outcome_id=oid, probability=value, kind="price",
            recv_wall=1000 + n, recv_mono=100 + n, venue_ts_ms=None,
            event_ordinal=n,
        )
        for n, (oid, value) in enumerate(p.ns["price_buffer"].items(), 1)
    }
    x.r.receipts = p.ns["tail_receipts"] = receipts
    p.ns["blend_refresher"] = x.r
    p.ns["logger"] = blend.logger
    committed = set()
    original_write = p.ns["write_chunk"]

    async def write(chunk, **kwargs):
        result = await original_write(chunk, **kwargs)
        if result:
            committed.update(chunk)
        return result

    p.ns["write_chunk"] = write
    original_publish = x.r._publish

    async def publish(frames):
        for frame in frames:
            cohort = {oid for oid, eid in p.ns["event_id_by_outcome"].items()
                      if eid == frame["event_id"]}
            assert cohort <= committed, "no event frame before its entire cohort commits"
            p.trace.append(("event_frame", frame["event_id"]))
        await original_publish(frames)

    x.r._publish = publish
    return p, x


async def test_new_committed_binary_frame_publishes_before_old_stamp_releases(monkeypatch):
    p, x = paired(monkeypatch)
    calls = []
    admit = x.r.admit_fresh

    def record(ids, **kwargs):
        owned = admit(ids, **kwargs)
        calls.append((set(ids), kwargs, owned))
        return owned

    x.r.admit_fresh = record
    flush = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.committed and not x.release.is_set()
        assert await asyncio.wait_for(flush, 2) is True
        owner = p.ns["catalog_boundary"].stamps
        assert (
            owner.task is not None and not owner.task.done()
        ), "the persistent owner retains the older stamp after the batch returns"
        assert ("write", [900, 901]) in p.trace  # complements commit together
        assert calls[0][0] == {2} and calls[0][2] == frozenset({2})
        offered = calls[0][1]
        assert offered["flush_started"] == 1000
        assert {m.outcome_id for m in offered["marks"]} == {900, 901}
        assert {m.probability for m in offered["marks"]} == {0.7, 0.3}
        assert offered["defer_event_ids"] == set()
        assert x.frames[-1]["rev"] == {"2": 42}
        assert x.r.stats["errors"] == 0
    finally:
        x.release.set()
        await asyncio.wait_for(flush, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert x.published == [2, 1]
    assert not x.r.pending_event_ids()
    assert not p.ns["price_buffer"]


async def test_late_same_event_withdrawal_waits_for_its_owner_not_the_next_cohort(monkeypatch):
    p, x = paired(monkeypatch)
    write = p.ns["write_chunk"]

    async def late_book(chunk, **kwargs):
        if 900 in chunk:
            # The active owner already admitted event 1. A book arriving during
            # this later write must keep its withdrawal after that owner.
            p.books[1] = (0.2, 0.8)
        return await write(chunk, **kwargs)

    p.ns["write_chunk"] = late_book
    flush = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        # #10090: event 2's committed cohort does not wait behind event 1's
        # withdrawal, which waits (buffered) for event 1's own stamp only.
        await settle_until(lambda: 2 in x.published)
        assert await asyncio.wait_for(flush, 2)
        assert 1 not in x.committed and not x.release.is_set()
        assert ("withdraw", [1]) not in p.trace and p.books == {1: (0.2, 0.8)}
    finally:
        x.release.set()
        await asyncio.wait_for(flush, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert await p.ns["flush_prices"](flush_started=1001)
    await p.ns["catalog_boundary"].join_stamps()
    assert p.trace.index(("event_frame", 1)) < p.trace.index(("withdraw", [1]))
    assert x.published[:2] == [2, 1] and not p.books
    assert not x.r.pending_event_ids()


@pytest.mark.parametrize("fail_last", [False, True])
async def test_implicit_debt_waits_for_the_final_planned_leg(monkeypatch, fail_last):
    p, x = paired(monkeypatch, split=True, fail_last=fail_last)
    x.r.adopt_pending([2])
    last_entered, last_release = asyncio.Event(), asyncio.Event()
    write = p.ns["write_chunk"]

    async def held_last(chunk, **kwargs):
        if 901 in chunk:
            last_entered.set()
            await last_release.wait()
        return await write(chunk, **kwargs)

    p.ns["write_chunk"] = held_last
    flush = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await asyncio.wait_for(last_entered.wait(), 2)
        assert 900 not in p.ns["price_buffer"] and 901 in p.ns["price_buffer"]
        assert 2 not in x.published and 2 not in x.committed
        assert 2 in x.r.pending_event_ids()
        last_release.set()
        if not fail_last:
            await settle_until(lambda: 2 in x.published)
            assert not x.release.is_set() and 1 not in x.committed
    finally:
        last_release.set()
        x.release.set()
        ok = await asyncio.wait_for(flush, 2)
        await p.ns["catalog_boundary"].join_stamps()
    if fail_last:
        assert ok is False and 901 in p.ns["price_buffer"]
        assert 2 not in x.published and x.r.pending_event_ids() == frozenset({2})
    else:
        assert ok is True and not x.r.pending_event_ids()


async def test_repeated_cancellation_joins_admitted_stamp_before_catalog_handover(monkeypatch):
    p, x = paired(monkeypatch, blocked=(1, 2))
    unwinding, finish_unwind, handed_over = asyncio.Event(), asyncio.Event(), asyncio.Event()
    factory = x.r._session_factory

    @asynccontextmanager
    async def slow_unwind():
        async with factory() as session:
            try:
                yield session
            finally:
                if 2 in session.event_ids and asyncio.current_task().cancelling():
                    unwinding.set()
                    await finish_unwind.wait()

    x.r._session_factory = slow_unwind
    flush = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))

    async def handover():
        async with p.ns["catalog_boundary"].updating():
            handed_over.set()

    update = None
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 2)
        assert await asyncio.wait_for(flush, 2) is True
        update = asyncio.create_task(handover())
        await asyncio.sleep(0)  # catalog enters the persistent-owner join
        update.cancel()
        await asyncio.wait_for(unwinding.wait(), 2)
        update.cancel()
        await asyncio.sleep(0)
        assert not update.done() and not handed_over.is_set()
        assert not x.published and not x.committed
        finish_unwind.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(update, 2)
        assert not handed_over.is_set()
        assert x.r.pending_event_ids() == frozenset({1, 2})
        assert x.r._admission is None
        assert p.ns["catalog_boundary"].active == 0
        assert not p.ns["catalog_boundary"].changing
    finally:
        finish_unwind.set()
        x.release.set()
        flush.cancel()
        await asyncio.gather(flush, *([update] if update else []), return_exceptions=True)
