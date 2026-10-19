"""#10090 — a committed price does not wait behind a held recovery read (real Postgres).

THE SHIP, IN A READER'S WORDS: a live event page that is already open shows a
new committed price at once, even while the server is re-reading which source
removals the page has covered; the slower re-read still arrives afterwards.

THE DECIDING PAIR (attempt133 `test_recovery_price.py`, assertions verbatim;
fixture from attempt121/125 `test_reconcile_route.py`). The actual `_stream`
route reads coverage from real PostgreSQL through `async_session_maker`. After
the initial coverage, a confirmation (or a hub recovery) starts a second read
whose SELECT result is HELD for 700 ms. While it is held, a fresh probability
is committed on another session and its exact-revision frame is offered. The
page must receive that price before the read is released (well under 250 ms,
exactly one probability frame, one coverage query), and the conservative older
floor must still be emitted once the read completes.

On the accepted125 route the price waits behind the read (~700 ms) and both
cases fail; on attempt133 and attempt136 (whose fast path leaves an owned read
untouched) both pass. Route controls without a database live in
`tests/test_event_stream_recovery_read_controls_10090.py`.

BOUNDED WAITS. Every wait watches the stream task: a stream that ended first
re-raises its own error; one still running at the bound is cancelled and
awaited before the failure is reported.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.routes import event_stream as route
from app.utils import live_fanout
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
    seed,
)
from tests.test_event_stream_recovery_read_controls_10090 import data, until
from tests.test_folded_event_stream_invalidation_837 import Hub, Request, frame

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


@pytest.fixture
async def stream_rig(rig, monkeypatch):  # noqa: F811
    await seed(rig, count=2)
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "async_session_maker", rig.maker)
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)
    monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 0.02)
    tasks = []

    def start(ids=None):
        chunks = []

        async def collect():
            async for c in route._stream(1, Request(), ids):
                chunks.append(c)

        task = asyncio.create_task(collect())
        tasks.append(task)
        return chunks, task

    try:
        yield SimpleNamespace(hub=hub, start=start, db=rig)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert route._open_connections == 0


async def change(rig, value):  # noqa: F811
    async with rig.engine.begin() as db:
        return (
            await db.execute(
                text(
                    "UPDATE events SET win_probability_sources=jsonb_build_object("
                    "'polymarket',jsonb_build_object('value',CAST(:v AS numeric),"
                    "'updated_at',clock_timestamp())) WHERE id=1 "
                    "RETURNING win_probability_sources_rev"
                ),
                {"v": value},
            )
        ).scalar_one()


@pytest.mark.parametrize("kind", ["confirmation", "recovery"])
async def test_committed_price_does_not_wait_for_coverage_query(
    stream_rig, monkeypatch, kind
):
    s = stream_rig
    chunks, task = s.start()
    await until(lambda: data(chunks, "reconcile"), task, "initial coverage", poll=0.005)
    floor = await change(s.db, 0.61)
    entered = asyncio.Event()
    release = asyncio.Event()
    captured = []

    @contextlib.asynccontextmanager
    async def delayed():
        async with s.db.maker() as db:
            execute = db.execute

            async def held(statement, *args, **kwargs):
                result = await execute(statement, *args, **kwargs)
                captured.append(str(statement))
                entered.set()
                await release.wait()
                return result

            db.execute = held
            yield db

    monkeypatch.setattr(route, "async_session_maker", delayed)
    payload = (
        live_fanout.CONFIRMED if kind == "confirmation" else live_fanout.Recovery(1)
    )
    s.hub.subscriptions["live:event:1"].offer(payload)
    await until(entered.is_set, task, f"{kind} read entered", poll=0.005)
    revision = await change(s.db, 0.73)
    accepted = time.monotonic()
    s.hub.subscriptions["live:event:1"].offer(
        json.dumps(
            frame(
                1, p=0.73, source="polymarket", source_value=0.73, rev={"1": revision}
            )
        )
    )

    async def unblock():
        await asyncio.sleep(0.7)
        release.set()

    releaser = asyncio.create_task(unblock())
    try:
        await until(
            lambda: bool(data(chunks, "probability")), task, "fresh price", poll=0.005
        )
        elapsed = time.monotonic() - accepted
        before = not release.is_set()
        await releaser
        await until(
            lambda: any(
                c["removal_rev"] == {"1": floor} for c in data(chunks, "reconcile")
            ),
            task,
            "conservative coverage after release",
            poll=0.005,
        )
        result = {
            "kind": kind,
            "accepted_frame_to_sse_seconds": elapsed,
            "before_query_release": before,
            "controlled_query_hold_seconds": 0.7,
            "coverage_floor": floor,
            "price_revision": revision,
            "probability_frames": len(data(chunks, "probability")),
            "coverage_queries": len(captured),
        }
        assert before, result
        assert elapsed < 0.25 and len(data(chunks, "probability")) == 1, result
        assert revision > floor and len(captured) == 1, result
    finally:
        release.set()
        await releaser
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
