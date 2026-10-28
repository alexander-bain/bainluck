"""#10090: on real PostgreSQL, a preview read past its deadline keeps its connection.

The production read scope (`ConsumerSessions.observation_read`) over a real
asyncpg pool. A second session holds ACCESS EXCLUSIVE on `futures_outcomes`,
so the real graph SELECT waits on the server past the 0.25 s preview deadline.
Cancelling it (the code before this change) invalidates the pooled connection
and the next read pays a fresh connect; left to finish, it returns the
connection and the next read reuses it.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event as sa_event, text

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.tasks.ws_consumer_sessions import ConsumerSessions
from app.utils import blend_preview
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig as _rig, seed

rig = _rig

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not DB_URL, reason="disposable PostgreSQL required")]


@pytest.fixture(autouse=True)
def legacy_preview(monkeypatch):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.PreviewRegistry())
    yield
    blend_preview.reset_registry_for_tests()


async def test_a_read_past_its_deadline_returns_its_connection_for_the_next(rig, monkeypatch):
    await seed(rig, count=1)
    sessions = ConsumerSessions("obs10090")
    sessions._engine, sessions._loop, sessions._pid = (
        rig.engine, asyncio.get_running_loop(), os.getpid(),
    )
    pool = rig.engine.sync_engine.pool
    connects, invalidated = [], []
    sa_event.listen(pool, "connect", lambda *a: connects.append(1))
    sa_event.listen(pool, "invalidate", lambda *a: invalidated.append(1))

    r = LiveBlendRefresher("polymarket", observation_read_factory=sessions.observation_read)
    r.preview_events = frozenset({1})
    r.preview = True

    async def publish(*args, **kwargs):
        return None

    monkeypatch.setattr(r, "_publish_previews", publish)
    now = datetime.now(timezone.utc)
    obs = {1: {1: (.7, (now - timedelta(seconds=1)).timestamp(), SimpleNamespace(probability=.7))}}

    async def validate(event_ids):
        return set(event_ids)

    schema = await _schema(rig)
    await r.preview_accepted_observations(obs, validate)  # warm: a pooled connection
    assert not invalidated
    connects.clear()
    lock_held, release = asyncio.Event(), asyncio.Event()

    async def hold_lock():
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)  # its own pool, not counted
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'LOCK TABLE "{schema}".futures_outcomes IN ACCESS EXCLUSIVE MODE'))
                lock_held.set()
                await release.wait()
        finally:
            await engine.dispose()

    holder = asyncio.create_task(hold_lock())
    await asyncio.wait_for(lock_held.wait(), 5)
    assert connects == []
    started = asyncio.get_running_loop().time()
    assert await r.preview_accepted_observations(obs, validate) is False
    waited = asyncio.get_running_loop().time() - started
    await asyncio.sleep(.3)  # the statement is still waiting on the server
    release.set()
    await holder
    detached = set(getattr(r, "_detached_reads", ()))
    if detached:
        await asyncio.wait_for(asyncio.wait(detached), 5)
    await asyncio.sleep(.05)
    assert not invalidated, "the timed-out read invalidated its pooled connection"
    await r.preview_accepted_observations(obs, validate)
    assert connects == [], "the next read paid a fresh connect"
    assert waited < .4
    await sessions.aclose()


async def _schema(rig):
    async with rig.engine.connect() as conn:
        return (await conn.execute(text("SELECT current_schema()"))).scalar_one()
