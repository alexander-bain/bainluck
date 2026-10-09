"""An event stamp progresses while its committed market notification waits."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.tasks.polymarket_ws import _PMPriceWriteResult
from tests.test_polymarket_withdrawal_speed_10651 import (
    ROOT, compile_functions, rig,
)


def committed_rig(*, fail_commit=False, hold_cleanup=False):
    r = rig(batch={1: 0.6, 2: 0.4}, books={})
    publishing, release, refreshed = (asyncio.Event() for _ in range(3))
    cleaning, cleanup = asyncio.Event(), asyncio.Event()

    class Session:
        async def execute(self, statement, params=None):
            if isinstance(statement, tuple) and statement[0] == "prices":
                return SimpleNamespace(all=lambda: [
                    SimpleNamespace(
                        id=oid, ord=i, market_id=10, quote_moved=True,
                        last_updated=100,
                    ) for i, oid in enumerate(statement[1])
                ])
            return SimpleNamespace(rowcount=1)

    @asynccontextmanager
    async def session():
        r.trace.append(("begin", None))
        yield Session()
        if fail_commit:
            raise RuntimeError("commit refused")
        r.trace.append(("commit", None))

    class Refresher:
        async def publish_market_changes(self, session):
            assert ("commit", None) in r.trace
            publishing.set()
            try:
                await release.wait()
            finally:
                if hold_cleanup:
                    cleaning.set()
                    await cleanup.wait()
                r.trace.append(("market_done", None))

        def pending_event_ids(self):
            return frozenset()

        async def refresh(self, ids, **kwargs):
            assert ("commit", None) in r.trace
            if 10 in ids:
                r.trace.append(("event_ready", 10))
                refreshed.set()

        async def refresh_pending(self, **kwargs):
            pass

    r.ns.update(
        get_task_session=session,
        blend_refresher=Refresher(),
        _PMPriceWriteResult=_PMPriceWriteResult,
        chunk_price_update_stmt=lambda chunk, **kw: ("prices", chunk),
    )
    # Execute the actual writer as well as the actual game-flush implementation.
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], r.ns)
    return r, publishing, release, refreshed, cleaning, cleanup


@pytest.mark.asyncio
async def test_event_stamp_does_not_wait_for_its_market_notification():
    r, publishing, release, refreshed, _, _ = committed_rig()
    task = asyncio.create_task(r.ns["flush_prices"]())
    try:
        await asyncio.wait_for(publishing.wait(), 1)
        await asyncio.wait_for(refreshed.wait(), 1)
        assert not task.done(), "the flush still owns and joins publication"
        assert ("market_done", None) not in r.trace
        # A genuinely newer input survives while the older notice is pending.
        r.ns["price_buffer"][1] = 0.7
    finally:
        release.set()
        await asyncio.wait_for(task, 1)
    assert r.ns["price_buffer"] == {1: 0.7}
    assert r.trace.index(("event_ready", 10)) < r.trace.index(("market_done", None))


@pytest.mark.asyncio
async def test_cancelled_flush_joins_publication_even_after_repeat_cancel():
    r, publishing, _, refreshed, cleaning, cleanup = committed_rig(hold_cleanup=True)
    task = asyncio.create_task(r.ns["flush_prices"]())
    try:
        await asyncio.wait_for(publishing.wait(), 1)
        await asyncio.wait_for(refreshed.wait(), 1)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        for _ in range(5):
            await asyncio.sleep(0)
        assert not task.done()
    finally:
        cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
    assert ("market_done", None) in r.trace
    assert not any(t.get_name() == "polymarket-committed-market-publish"
                   for t in asyncio.all_tasks() if not t.done())


@pytest.mark.asyncio
async def test_failed_commit_neither_publishes_nor_stamps_and_keeps_prices():
    r, publishing, _, refreshed, _, _ = committed_rig(fail_commit=True)
    assert await r.ns["flush_prices"]() is False
    assert not publishing.is_set() and not refreshed.is_set()
    assert r.ns["price_buffer"] == {1: 0.6, 2: 0.4}
