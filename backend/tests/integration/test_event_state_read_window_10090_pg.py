"""#10090 — the detail payload's state-read window, on a REAL Postgres.

`event_state_read_window` claims the served row was read inside
``[transaction_timestamp(), clock_timestamp()]`` on the database's own clock,
so a reader may order two payloads' game state only when one window ends
strictly before the other begins. The unit suite grades the shape; only a real
server can grade the claim. Two cases, each with a real committed write:

* SEQUENTIAL — read `scheduled`, a writer commits `live`, read again: the
  second window begins strictly after the first ends, so the newer state is
  provably newer;
* CONCURRENT — two open transactions that both read before the window is
  taken overlap, so the rule refuses to order them (nothing may choose).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.routes.events import (
    STATE_READ_NOT_AFTER_KEY,
    STATE_READ_NOT_BEFORE_KEY,
    event_state_read_window,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"),
]


@pytest.fixture
async def maker():
    schema = "staterw10090_" + uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(DB_URL, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE game (id int PRIMARY KEY, status text NOT NULL)"))
            await conn.execute(text("INSERT INTO game VALUES (1, 'scheduled')"))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def _status(session) -> str:
    return (await session.execute(text("SELECT status FROM game WHERE id = 1"))).scalar_one()


def _bounds(window):
    from datetime import datetime

    assert set(window) == {STATE_READ_NOT_BEFORE_KEY, STATE_READ_NOT_AFTER_KEY}, window
    lo = datetime.fromisoformat(window[STATE_READ_NOT_BEFORE_KEY])
    hi = datetime.fromisoformat(window[STATE_READ_NOT_AFTER_KEY])
    assert lo.utcoffset() is not None and lo <= hi
    return lo, hi


async def test_a_read_after_a_committed_kickoff_is_provably_newer(maker):
    async with maker() as before:
        assert await _status(before) == "scheduled"
        first = _bounds(await event_state_read_window(before))
    async with maker() as writer:
        await writer.execute(text("UPDATE game SET status = 'live' WHERE id = 1"))
        await writer.commit()
    async with maker() as after:
        assert await _status(after) == "live"
        second = _bounds(await event_state_read_window(after))
    assert second[0] > first[1], (first, second)


async def test_two_open_reads_overlap_and_are_not_ordered(maker):
    async with maker() as a, maker() as b:
        assert await _status(a) == "scheduled"
        assert await _status(b) == "scheduled"
        a_window = _bounds(await event_state_read_window(a))
        b_window = _bounds(await event_state_read_window(b))
    # Neither begins after the other ends: a reader holding both must keep
    # today's rule — the window never picks a side it cannot prove.
    assert not (b_window[0] > a_window[1])
    assert not (a_window[0] > b_window[1])


async def test_a_long_transaction_keeps_its_early_lower_bound(maker):
    """A row read late in a transaction that began early: `not_before` is the
    transaction start, which is still at or before that read's snapshot — the
    window widens, it never lies."""
    async with maker() as early:
        await early.execute(text("SELECT 1"))
        async with maker() as writer:
            await writer.execute(text("UPDATE game SET status = 'live' WHERE id = 1"))
            await writer.commit()
            committed_at = (await writer.execute(text("SELECT clock_timestamp()"))).scalar_one()
        assert await _status(early) == "live"  # READ COMMITTED: a fresh snapshot per statement
        lo, hi = _bounds(await event_state_read_window(early))
    assert lo < committed_at < hi
