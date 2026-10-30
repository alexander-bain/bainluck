"""#10090 — `chunk_price_update_stmt(..., skip_units=...)` and when the writer uses it.

The real-Postgres behaviour is `tests/integration/test_pm_skip_locked_row_10090_pg.py`.
These pin what a refactor could silently lose: the row-lock order, the change
filter ahead of the lock, the unchanged waiting/NOWAIT forms, and the two
paths that must never skip (the final drain; a chunk of one unit).
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks.polymarket_ws import chunk_price_update_stmt
from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime

CHUNK = {1: 0.5, 2: 0.25, 3: 0.75}


def sql(**kwargs) -> str:
    return str(chunk_price_update_stmt(CHUNK, **kwargs).compile(dialect=postgresql.dialect()))


def test_rows_are_locked_skip_locked_in_chunk_order_behind_the_change_filter():
    text = sql(force_ids=set(), skip_units={1: 10, 2: 10, 3: None})
    locked = text[text.index("locked AS MATERIALIZED"):text.index("wanted AS MATERIALIZED")]
    # Deadlock avoidance: chunk order. An unchanged row is filtered BEFORE
    # LockRows, so it takes no lock.
    assert "ORDER BY given.ord FOR NO KEY UPDATE OF futures_outcomes SKIP LOCKED" in locked
    assert locked.index("WHERE given.force_write OR") < locked.index("FOR NO KEY UPDATE")
    # The unlocked read uses the same filter, so a skip is a wanted row.
    wanted = text[text.index("wanted AS MATERIALIZED"):text.index("held AS MATERIALIZED")]
    assert "WHERE given.force_write OR" in wanted and "FOR UPDATE" not in wanted
    # Held-back rows are returned, explicitly marked.
    assert "false AS skipped" in text and "true AS skipped" in text


def test_without_skip_units_the_statement_keeps_its_waiting_and_nowait_forms():
    for kwargs in ({}, {"force_ids": {1}}):
        text = sql(**kwargs)
        assert "SKIP LOCKED" not in text and "UNION" not in text and "skipped" not in text
        assert "ORDER BY given.ord FOR UPDATE OF futures_outcomes)" in text
    assert "FOR UPDATE OF futures_outcomes NOWAIT" in sql(nowait=True)


@pytest.mark.asyncio
async def test_the_final_drain_never_skips(monkeypatch):
    r, state = writer_rig(_FakeTime(monkeypatch, t=1000))
    state.held = False
    r.ns["non_blend_outcome_ids"].add(2)  # two units
    assert (await r.ns["write_chunk"]({1: 0.7, 2: 0.3}, final=True)).written_ids == (1, 2)
    assert state.skip == [False]


@pytest.mark.asyncio
async def test_a_chunk_of_one_unit_keeps_its_wait_and_probe(monkeypatch):
    r, state = writer_rig(_FakeTime(monkeypatch, t=1000))
    # Event 10's two legs: one unit, already holding back only itself.
    assert await r.ns["write_chunk"]({1: 0.7, 2: 0.3}) is None
    assert state.skip == [False] and state.nowait == [False]
    assert await r.ns["write_chunk"]({1: 0.7, 2: 0.3}) is None
    assert state.skip == [False, False] and state.nowait == [False, True]


@pytest.mark.asyncio
async def test_a_session_bound_to_another_database_never_skips(monkeypatch):
    r, state = writer_rig(_FakeTime(monkeypatch, t=1000))
    state.held = False
    r.ns["non_blend_outcome_ids"].add(2)
    sessions = r.ns["get_task_session"]

    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    @asynccontextmanager
    async def sqlite_bound():
        async with sessions() as session:
            session.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
            yield session

    r.ns["get_task_session"] = sqlite_bound
    assert (await r.ns["write_chunk"]({1: 0.7, 2: 0.3})).written_ids == (1, 2)
    assert state.skip == [False]
