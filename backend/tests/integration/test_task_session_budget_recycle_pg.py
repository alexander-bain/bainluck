"""A per-job query budget survives the pool replacing its connection — #4482.

## why this one cannot be a unit test

Three of the claims behind #4482's fix are properties of a running PostgreSQL
and of asyncpg's startup packet, and every one of them was previously taken on
trust:

1. **`lock_timeout` is accepted as a startup parameter at all.** #3776 proved
   the `server_settings` channel for `statement_timeout` and nothing else. A GUC
   the startup packet refuses does not degrade — it fails the CONNECT, so every
   task in the app would stop having a database. A mock cannot fail that way.
2. **The value arrives as the value asked for.** `server_settings` takes strings
   and PostgreSQL parses them; `"7000"` reaching the server as `7s` is a round
   trip through two parsers.
3. **The budget rides a REPLACED connection.** This is the whole defect. The
   session returns its connection to the pool at every `commit()`, and when
   `pool_recycle` (1800 s in `_get_task_engine`) or a `pool_pre_ping` failure
   discards it, the next statement runs somewhere new.

## the differential rig, and why both arms have to render

The fix arm alone proves nothing: if the forced recycle never fired, the same
connection would come back and a broken fix would read green. So every arm
reads `pg_backend_pid()` alongside the budget and asserts the backend actually
changed, and the CONTROL arm reproduces today's bare `SET` and asserts it
LOSES the budget at the same point — 30 minutes of statement bound where 7
seconds was asked for. A rig where every arm renders the same thing reads as a
clean diff and is worth nothing.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

import app.tasks.base as base_mod
from app.services.database import DB_STATEMENT_TIMEOUT_MS

# Called as `base_mod.get_task_session`, not imported by name: this module
# monkeypatches `base_mod.DATABASE_URL` and `base_mod.create_async_engine`, and a
# name bound at import time would be a second handle on the same module whose
# relationship to those patches a reader has to work out. CodeQL flags the pair
# (`py/import-of-mutable-attribute`) and is right about the smell.


DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres query-budget "
        "contract (CI job `search-recall` provides one)"
    ),
)

STMT_MS = 7_000
LOCK_MS = 3_000


@pytest.fixture
def task_db(monkeypatch):
    """Point `get_task_session()` at the test server."""
    monkeypatch.setattr(base_mod, "DATABASE_URL", DB_URL)
    return DB_URL


@pytest.fixture
def force_recycle(monkeypatch):
    """Make the pool discard its connection at every checkout.

    `pool_recycle=0` is the trigger, not the thing under test: it reproduces in
    one statement what 30 minutes of a long task run does on production. What is
    under test is whether the budget is on the connection the pool hands back
    next.
    """
    real = base_mod.create_async_engine

    def _forcing(url, **kwargs):
        kwargs["pool_recycle"] = 0
        return real(url, **kwargs)

    monkeypatch.setattr(base_mod, "create_async_engine", _forcing)


def _as_pg(ms: int) -> str:
    """How PostgreSQL renders a millisecond GUC back to `current_setting`.

    Derived rather than pinned: a hardcoded `"7s"` beside `STMT_MS = 7_000` is a
    literal that happens to agree today and stops agreeing silently the moment
    the constant moves.
    """
    if ms % 60_000 == 0:
        return f"{ms // 60_000}min"
    if ms % 1_000 == 0:
        return f"{ms // 1_000}s"
    return str(ms)


async def _budget(session) -> tuple[int, str, str]:
    """`(backend pid, statement_timeout, lock_timeout)` as the server sees them."""
    row = (
        await session.execute(
            text(
                "SELECT pg_backend_pid() AS pid,"
                " current_setting('statement_timeout') AS stmt,"
                " current_setting('lock_timeout') AS lock"
            )
        )
    ).one()
    return int(row.pid), row.stmt, row.lock


@needs_postgres
async def test_the_startup_packet_accepts_both_budgets(task_db):
    # Claim 1 and 2. If `lock_timeout` were not a legal startup parameter this
    # would raise on connect, not read a wrong value.
    async with base_mod.get_task_session(
        statement_timeout_ms=STMT_MS, lock_timeout_ms=LOCK_MS
    ) as session:
        _pid, stmt, lock = await _budget(session)

    assert stmt == _as_pg(STMT_MS), f"statement_timeout came back as {stmt!r}"
    assert lock == _as_pg(LOCK_MS), f"lock_timeout came back as {lock!r}"


@needs_postgres
async def test_an_unarmed_session_rests_where_3776_left_it(task_db):
    # The baseline the leak falls back TO, read rather than assumed. It is also
    # why losing a lock budget is worse than losing a statement budget: there is
    # no resting value for lock_timeout, so the fallback is "wait forever".
    async with base_mod.get_task_session() as session:
        _pid, stmt, lock = await _budget(session)

    assert stmt == _as_pg(DB_STATEMENT_TIMEOUT_MS), (
        f"resting statement_timeout is {stmt!r}, not the "
        f"{DB_STATEMENT_TIMEOUT_MS} ms #3776 shipped"
    )
    assert lock == "0", f"lock_timeout has a resting value of {lock!r} — it should be 0"


@needs_postgres
async def test_the_budget_rides_a_replaced_connection(task_db, force_recycle):
    """THE FIX ARM."""
    pids: list[int] = []
    async with base_mod.get_task_session(
        statement_timeout_ms=STMT_MS, lock_timeout_ms=LOCK_MS
    ) as session:
        for _ in range(3):
            pid, stmt, lock = await _budget(session)
            pids.append(pid)
            assert stmt == _as_pg(STMT_MS), (
                f"lost the statement budget on backend {pid}: {stmt!r}"
            )
            assert lock == _as_pg(LOCK_MS), (
                f"lost the lock budget on backend {pid}: {lock!r}"
            )
            await session.commit()

    assert len(set(pids)) == 3, (
        f"the pool never replaced the connection ({pids}) — this arm would have "
        "passed whether or not the fix works"
    )


@needs_postgres
async def test_a_bare_set_loses_the_budget_at_the_same_point(task_db, force_recycle):
    """THE CONTROL ARM — today's eight call sites, reproduced.

    Renders a DIFFERENT result from the fix arm, which is the only thing that
    makes the fix arm mean anything.
    """
    readings: list[tuple[int, str, str]] = []
    async with base_mod.get_task_session() as session:
        # Exactly what `app/tasks/kalshi.py` did before #4482. Built here rather
        # than imported, because the point of the fix is that no such string
        # survives in `app/` for the guard test to find.
        await session.execute(text(f"SET statement_timeout = '{STMT_MS // 1000}s'"))
        await session.execute(text(f"SET lock_timeout = '{LOCK_MS // 1000}s'"))
        for _ in range(3):
            readings.append(await _budget(session))
            await session.commit()

    first, *rest = readings
    assert first[1:] == (_as_pg(STMT_MS), _as_pg(LOCK_MS)), (
        f"the bare SET did not even take: {first}"
    )
    assert len({r[0] for r in readings}) == 3, "the pool never replaced the connection"

    for pid, stmt, lock in rest:
        assert stmt == _as_pg(DB_STATEMENT_TIMEOUT_MS), (
            f"backend {pid} kept the 7s bound after the pool replaced the "
            f"connection ({stmt!r}) — the defect #4482 describes did not "
            "reproduce, so this control proves nothing"
        )
        assert lock == "0", (
            f"backend {pid} kept a lock bound of {lock!r}; the control expects "
            "it to be gone entirely"
        )


@needs_postgres
async def test_the_armed_budget_still_bites(task_db):
    """A bound the server reports but never enforces would pass every test above."""
    from sqlalchemy.exc import DBAPIError

    async with base_mod.get_task_session(statement_timeout_ms=1_000) as session:
        with pytest.raises(DBAPIError) as excinfo:
            await session.execute(text("SELECT pg_sleep(5)"))
        # The transaction is aborted; without this the context manager's exit
        # `commit()` raises PendingRollbackError and the test fails for a reason
        # that has nothing to do with the bound.
        await session.rollback()

    assert "canceling statement due to statement timeout" in str(excinfo.value).lower()
