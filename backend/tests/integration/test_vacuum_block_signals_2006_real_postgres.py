"""#2006 — the vacuum-block signals, EXECUTED BY A REAL SERVER.

## what a fake session cannot say about this rail

``tests/test_vacuum_block_watchdog_2006.py`` proves the classifier, the alarm,
the cooldown and the recovery, all against a dict. Not one of its arms lets
PostgreSQL see a statement, and every interesting property of this rail is a
property PostgreSQL decides:

* **Can the application's role even see another backend's ``backend_xmin``?**
  The whole ship rests on it, CI's ``postgres`` user is a superuser and Heroku's
  application role is not, so the arms that matter run as a role created here
  with no privileges at all. **This gate found a shipping defect on its first
  run**, and the measurement is worth stating because it is not the split the
  documentation's "the ``query`` field" sentence suggests:

  =========================  ==========================================
  ``backend_xmin``           readable ACROSS roles
  ``state`` / ``xact_start``
  / ``backend_type``         NULL for another role's backend
  =========================  ==========================================

  So ``backend_type <> 'autovacuum worker'`` evaluates to NULL — and therefore
  EXCLUDES — precisely the cross-role rows whose ``backend_xmin`` is still
  readable. The xid signal would have been blinded on Heroku by its own
  autovacuum filter, in a way no superuser test could ever show.
  ``IS DISTINCT FROM`` keeps them, and
  ``test_the_xid_signal_still_sees_a_backend_of_another_role`` is what holds it
  there. The wall-clock signal remains same-role-only, which is a limit rather
  than a defect — the application role owns every backend the application opens,
  and #2005's culprit was one of them — and
  ``test_the_wall_clock_signal_is_blind_to_another_role`` records it so nobody
  later reads this alarm as covering every backend on the instance.
* **Do the two exclusion filters exclude only what they name?** A filter that
  hides rows is unfalsifiable when the innocent case leaves no trace, so the
  ``pg_dump`` arm asserts BOTH directions on one backend: named ``pg_dump`` it
  disappears, renamed it comes back, same pid.
* **Does the 5 s budget actually reach the connection?** #4482: a bare ``SET`` on
  a task session silently reverts when the pool recycles, so the bound goes
  through the startup packet. Whether it arrived is a question for a server, and
  whether it is ENFORCED is a second question, asked separately.
* **Is the absent dead-tuple reading reachable without an error?** That single
  fact is why the first candidate for this issue was rejected — its classifier
  turned one absent optional signal into ``unavailable`` for the whole check,
  and the incident shape then published ``ready``. The review argued the path
  was reachable from the SQL text. Here it is executed.

## the corpus

``SEARCH_TEST_DATABASE_URL`` names the ``search-recall`` job's SHARED database,
which several dozen sibling gates populate. Three arms here assert on *which*
table is worst by dead-tuple ratio and on there being *no* qualifying table at
all, so a shared database would let step ordering decide them. The fixture
therefore uses that URL only for its host and credentials and provisions
``bl_vacuum_signals_2006`` beside it — created on first use, kept, with the
tables and the role dropped on both ends of every test.

Two tables in it, created with ``autovacuum_enabled = false`` so the dead tuples
cannot be reclaimed out from under the read:

* ``vacuum_probe_dirty_2006`` — 2,000 rows inserted, 1,990 deleted ⇒ 99.5% dead.
* ``vacuum_probe_clean_2006`` — 2,000 rows, none deleted ⇒ 0% dead.

The clean table is the arm that stops ``ORDER BY ... DESC`` being reversible
without notice: "returns a row" is satisfied by either direction, "does not
return the clean table" is not.

``n_dead_tup`` is published by the statistics collector asynchronously, so the
fixture POLLS for it rather than sleeping a guessed interval or calling
``pg_stat_force_next_flush()`` (PG15+; this gate also has to run against a
developer's PG14).

The held transactions are raw asyncpg connections — the same driver production
uses — because a held transaction is the specimen here, and a SQLAlchemy
connection that manages its own transaction boundaries is the wrong instrument
for holding one open deliberately.

Read-only against ``pg_stat_activity``. Nothing in this file cancels a backend,
and nothing in it runs against production.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2006 vacuum-signal "
        "gate (CI job `search-recall` provides one)"
    ),
)

DIRTY_TABLE = "vacuum_probe_dirty_2006"
CLEAN_TABLE = "vacuum_probe_clean_2006"

#: The unprivileged stand-in for the Heroku application role. Created and
#: dropped by the fixture; it owns nothing and is granted nothing.
PROBE_ROLE = "bl_vacuum_probe_2006"
#: Not a credential: a random string minted per run for a role that exists for
#: the length of one test session on a disposable database, and is dropped after.
PROBE_SECRET = uuid.uuid4().hex

#: 1,990 of 2,000. Asserted as a floor, not as an exact winner — this gate owns
#: its database, but a floor says what the arm means without arithmetic.
DIRTY_PCT_FLOOR = 99.0

#: How long the fixture will wait for the statistics collector to publish the
#: dead-tuple counts it has already been sent.
STATS_TIMEOUT_S = 20.0


#: This gate provisions and owns a database of its own on the same server.
#:
#: NOT ``bl_searchtest``. The ``search-recall`` job's shared database is
#: populated by several dozen sibling gates, and three arms here assert on
#: *which* table is the worst by dead-tuple ratio and on there being *no*
#: qualifying table at all — both of which another gate's leftovers would decide
#: instead. Pointing this file at the shared URL would produce arms that pass or
#: fail on step ordering.
GATE_DB = "bl_vacuum_signals_2006"


def _plain_dsn(url: str) -> str:
    """asyncpg wants a libpq URL, not SQLAlchemy's ``+asyncpg`` form."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgres://", "postgresql://", 1
    )


def _with_database(url: str, database: str) -> str:
    head, _, _tail = _plain_dsn(url).rpartition("/")
    return f"{head}/{database}"


def _gate_dsn() -> str:
    return _with_database(DB_URL, GATE_DB)


def _sqlalchemy_url() -> str:
    return _gate_dsn().replace("postgresql://", "postgresql+asyncpg://", 1)


def _role_dsn() -> str:
    """This gate's database, reached as the unprivileged probe role."""
    tail = _gate_dsn().split("@", 1)[1]
    return f"postgresql://{PROBE_ROLE}:{PROBE_SECRET}@{tail}"


async def _await_dead_tuples(conn, table: str, at_least: int) -> int:
    """Poll until the collector has published this table's dead tuples."""
    deadline = asyncio.get_running_loop().time() + STATS_TIMEOUT_S
    seen = 0
    while asyncio.get_running_loop().time() < deadline:
        seen = (
            await conn.fetchval(
                "SELECT coalesce(n_dead_tup, 0) FROM pg_stat_user_tables "
                "WHERE relname = $1",
                table,
            )
            or 0
        )
        if seen >= at_least:
            return seen
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"pg_stat_user_tables never published {at_least} dead tuples for {table} "
        f"within {STATS_TIMEOUT_S}s (last read {seen})"
    )


async def _burn_xids(conn, count: int) -> None:
    """Advance the transaction counter so a held snapshot has a real AGE.

    Without this every backend reports the same ``backend_xmin`` and
    ``age(...)`` is 0 for all of them, which makes every xid arm below pass
    against a query that returns whichever row it likes.
    """
    for _ in range(count):
        await conn.execute("SELECT txid_current()")


@pytest.fixture
async def pg():
    """This gate's own database, its two probe tables, and the probe role.

    The database is created on first use and left in place; the tables and the
    role are dropped on both ends of every test. Nothing here touches the
    ``bl_searchtest`` database the rest of the job shares.
    """
    import asyncpg

    admin = await asyncpg.connect(_with_database(DB_URL, "postgres"))
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", GATE_DB
        )
        if not exists:
            await admin.execute(f"CREATE DATABASE {GATE_DB}")
    finally:
        await admin.close()

    conn = await asyncpg.connect(_gate_dsn())

    async def _drop():
        for table in (DIRTY_TABLE, CLEAN_TABLE):
            await conn.execute(f"DROP TABLE IF EXISTS {table}")
        await conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
            f"'{PROBE_ROLE}') THEN DROP ROLE {PROBE_ROLE}; END IF; END $$;"
        )

    try:
        await _drop()
        await conn.execute(
            f"CREATE ROLE {PROBE_ROLE} LOGIN PASSWORD '{PROBE_SECRET}'"
        )
        for table in (DIRTY_TABLE, CLEAN_TABLE):
            await conn.execute(
                f"CREATE TABLE {table} (id integer PRIMARY KEY) "
                f"WITH (autovacuum_enabled = false)"
            )
            await conn.execute(
                f"INSERT INTO {table} SELECT generate_series(1, 2000)"
            )
        await conn.execute(f"DELETE FROM {DIRTY_TABLE} WHERE id > 10")
        await _await_dead_tuples(conn, DIRTY_TABLE, 1990)
        yield conn
    finally:
        try:
            await _drop()
        finally:
            await conn.close()


class _HeldTransaction:
    """A second backend sitting in an open transaction, like #2005's pid.

    ``REPEATABLE READ`` plus one statement is the cheapest way to take a real
    snapshot, which is what gives the backend a ``backend_xmin`` at all — a
    transaction that has issued nothing has none, and an arm written against
    that would assert nothing.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None
        self._tx = None
        self.pid = None

    async def __aenter__(self):
        import asyncpg

        self._conn = await asyncpg.connect(self._dsn)
        self._tx = self._conn.transaction(isolation="repeatable_read")
        await self._tx.start()
        self.pid = await self._conn.fetchval("SELECT pg_backend_pid()")
        await self._conn.fetchval("SELECT 1")
        return self

    async def set_application_name(self, name: str):
        await self._conn.execute(f"SET application_name = '{name}'")

    async def __aexit__(self, *exc):
        try:
            await self._tx.rollback()
        finally:
            await self._conn.close()
        return False


@needs_postgres
class TestTheShippedSqlRunsOnARealServer:
    async def test_the_held_transaction_is_found_with_its_pid(self, pg):
        """The signal that carries the one-hour bar, executed end to end."""
        from app.tasks.watchdog import Q_VACUUM_OLDEST_XACT

        async with _HeldTransaction(_gate_dsn()) as held:
            rows = await pg.fetch(Q_VACUUM_OLDEST_XACT)

        assert rows, "the shipped statement found no non-idle transaction at all"
        assert rows[0]["xact_age_s"] is not None
        assert float(rows[0]["xact_age_s"]) >= 0
        # `idle in transaction` — the #2005 holder's own state — is `<> 'idle'`
        # and must not be filtered out by the predicate.
        assert held.pid in {r["pid"] for r in rows}, (
            "the backend holding an open transaction is not visible to the "
            "shipped predicate"
        )

    async def test_the_xid_signal_names_the_backend_holding_the_horizon(self, pg):
        from app.tasks.watchdog import Q_VACUUM_OLDEST_XMIN

        async with _HeldTransaction(_gate_dsn()) as held:
            await _burn_xids(pg, 60)
            row = await pg.fetchrow(Q_VACUUM_OLDEST_XMIN)

        assert row is not None
        assert row["xmin_age"] is not None and int(row["xmin_age"]) >= 60
        assert row["pid"] == held.pid, (
            "the oldest held snapshot belongs to the transaction this test is "
            "holding, and the query must name its pid — a bare max() would give "
            "the on-call a number with nothing to act on"
        )

    async def test_an_unprivileged_role_sees_its_own_roles_stalled_backend(self, pg):
        """The production shape: the monitor and the stalled backend are the
        SAME application role, because the application opened both.

        Heroku's app role is not a superuser, so this is the arm that says the
        rail works there at all — both signals, read by a role created here with
        no privileges.
        """
        import asyncpg

        from app.tasks.watchdog import Q_VACUUM_OLDEST_XACT, Q_VACUUM_OLDEST_XMIN

        async with _HeldTransaction(_role_dsn()) as held:
            # Let the held transaction age past a second so the reader cannot
            # pass the age assertion on a zero.
            await asyncio.sleep(1.1)
            await _burn_xids(pg, 60)
            reader = await asyncpg.connect(_role_dsn())
            try:
                assert await reader.fetchval("SELECT current_user") == PROBE_ROLE
                assert not await reader.fetchval(
                    "SELECT usesuper FROM pg_user WHERE usename = current_user"
                ), "the probe role must not be a superuser"
                xmin_row = await reader.fetchrow(Q_VACUUM_OLDEST_XMIN)
                xact_rows = await reader.fetch(Q_VACUUM_OLDEST_XACT)
            finally:
                await reader.close()

        assert xmin_row is not None and xmin_row["pid"] == held.pid
        assert int(xmin_row["xmin_age"]) >= 60
        assert held.pid in {r["pid"] for r in xact_rows}, (
            "an unprivileged role cannot see its OWN role's open transaction — "
            "the wall-clock signal is dead on Heroku"
        )
        assert max(float(r["xact_age_s"]) for r in xact_rows) >= 1.0

    async def test_the_xid_signal_still_sees_a_backend_of_another_role(self, pg):
        """THE arm this gate was written for, and the defect it caught.

        ``backend_xmin`` is readable across roles while ``backend_type`` is not,
        so ``backend_type <> 'autovacuum worker'`` is NULL — and excludes — for
        exactly these rows. Written with ``<>`` instead of ``IS DISTINCT FROM``
        this arm fails: the reader gets only its own young snapshot back and the
        one signal the issue calls unambiguous reports healthy.
        """
        import asyncpg

        from app.tasks.watchdog import Q_VACUUM_OLDEST_XMIN

        # The holder is the SUPERUSER — a different role from the reader.
        async with _HeldTransaction(_gate_dsn()) as held:
            await _burn_xids(pg, 60)
            reader = await asyncpg.connect(_role_dsn())
            try:
                row = await reader.fetchrow(Q_VACUUM_OLDEST_XMIN)
                own_pid = await reader.fetchval("SELECT pg_backend_pid()")
            finally:
                await reader.close()

        assert row is not None
        assert row["pid"] == held.pid, (
            "the unprivileged reader did not see the other role's held snapshot "
            f"(got pid {row['pid']}, its own is {own_pid})"
        )
        assert int(row["xmin_age"]) >= 60

    async def test_the_wall_clock_signal_is_blind_to_another_role(self, pg):
        """The stated limit, asserted so it stays stated.

        ``state`` and ``xact_start`` are NULL for another role's backend, so no
        SQL makes the wall-clock signal see one. That is acceptable for this
        ship — the application role owns every backend the application opens —
        and it is the sharpest reason the two signals must be classified
        independently: they do not see the same population.
        """
        import asyncpg

        from app.tasks.watchdog import Q_VACUUM_OLDEST_XACT

        async with _HeldTransaction(_gate_dsn()) as held:
            await asyncio.sleep(1.1)
            reader = await asyncpg.connect(_role_dsn())
            try:
                rows = await reader.fetch(Q_VACUUM_OLDEST_XACT)
                cross_role = await reader.fetchrow(
                    "SELECT state, xact_start, backend_type FROM pg_stat_activity "
                    "WHERE pid = $1",
                    held.pid,
                )
            finally:
                await reader.close()

        assert cross_role is not None, "the row itself is visible"
        assert cross_role["state"] is None
        assert cross_role["xact_start"] is None
        assert cross_role["backend_type"] is None
        assert held.pid not in {r["pid"] for r in rows}

    async def test_the_pg_dump_filter_excludes_only_pg_dump(self, pg):
        """Both directions on ONE backend, so the exclusion cannot be a no-op
        and cannot be a blanket."""
        from app.tasks.watchdog import Q_VACUUM_OLDEST_XACT

        async with _HeldTransaction(_gate_dsn()) as held:
            await held.set_application_name("pg_dump")
            hidden = {r["pid"] for r in await pg.fetch(Q_VACUUM_OLDEST_XACT)}

            await held.set_application_name("bainluck-web")
            shown = {r["pid"] for r in await pg.fetch(Q_VACUUM_OLDEST_XACT)}

        assert held.pid not in hidden, "a pg_dump backend must not page the on-call"
        assert held.pid in shown, (
            "the filter removed a backend that is not pg_dump — the innocent "
            "case must leave a trace"
        )


@needs_postgres
class TestTheDeadTupleReadingIsGenuinelyOptional:
    async def test_the_worst_table_query_orders_the_dirtiest_first(self, pg):
        from app.tasks.watchdog import Q_VACUUM_WORST_DEAD_PCT

        row = await pg.fetchrow(Q_VACUUM_WORST_DEAD_PCT)

        assert row is not None
        assert row["relname"] != CLEAN_TABLE, (
            "the 0%-dead table was returned as the worst — the ORDER BY is "
            "reversed and nothing else in this file would notice"
        )
        assert row["relname"] == DIRTY_TABLE
        pct = row["n_dead_tup"] / (row["n_live_tup"] + row["n_dead_tup"]) * 100
        assert pct >= DIRTY_PCT_FLOOR

    async def test_no_qualifying_table_returns_no_row_and_no_error(self, pg):
        """THE reachable ``None``. This is the read the rejected classifier
        turned into ``unavailable`` for the whole check — and the review's claim
        that it needs no failure to go quiet, executed rather than argued.
        """
        from app.tasks.watchdog import (
            Q_VACUUM_WORST_DEAD_PCT,
            classify_vacuum_signals,
        )

        for table in (DIRTY_TABLE, CLEAN_TABLE):
            await pg.execute(f"DROP TABLE IF EXISTS {table}")

        row = await pg.fetchrow(Q_VACUUM_WORST_DEAD_PCT)

        assert row is None, (
            "expected no qualifying table after dropping the probe tables — "
            "this gate owns its database"
        )
        # And that absence, paired with the incident's own xmin reading, is
        # still a page. This is the whole correction, on real evidence.
        assert classify_vacuum_signals(81_643, None, None)[0] == "page"


@needs_postgres
class TestTheReadIsBoundedAndWiredToTheRealSession:
    async def test_the_shipped_budget_reaches_the_connection(self, pg, monkeypatch):
        """#4482: the bound travels in the startup packet, not in a ``SET``.

        ``SHOW statement_timeout`` is the server's own account of what it was
        given, which is the only thing that distinguishes "we passed a kwarg"
        from "the connection is bounded".
        """
        from sqlalchemy import text

        from app.tasks import base as task_base
        from app.tasks.watchdog import VACUUM_QUERY_TIMEOUT_MS

        monkeypatch.setattr(task_base, "DATABASE_URL", _sqlalchemy_url())

        async with task_base.get_task_session(
            statement_timeout_ms=VACUUM_QUERY_TIMEOUT_MS
        ) as session:
            shown = (await session.execute(text("SHOW statement_timeout"))).scalar()

        assert shown == "5s", f"statement_timeout on the connection reads {shown!r}"

    async def test_a_statement_past_the_budget_is_cancelled(self, pg, monkeypatch):
        """The bound is ENFORCED, not merely reported. Uses a deliberately tiny
        budget so the arm costs a fraction of a second rather than five."""
        from sqlalchemy import text

        from app.tasks import base as task_base

        monkeypatch.setattr(task_base, "DATABASE_URL", _sqlalchemy_url())

        with pytest.raises(Exception) as excinfo:
            async with task_base.get_task_session(statement_timeout_ms=250) as session:
                await session.execute(text("SELECT pg_sleep(5)"))

        assert "canceling statement" in str(excinfo.value).lower(), (
            f"expected a statement_timeout cancellation, got {excinfo.value!r}"
        )

    async def test_read_vacuum_signals_returns_the_classifiers_shape(
        self, pg, monkeypatch
    ):
        """The shipped reader, on the shipped session, against a real server.

        This is the arm that would have caught a column renamed in the SELECT
        list, a row attribute that does not exist, or an ``EXTRACT`` whose
        numeric result does not survive ``int(float(...))``.
        """
        from app.tasks import base as task_base
        from app.tasks.watchdog import _read_vacuum_signals, classify_vacuum_signals

        monkeypatch.setattr(task_base, "DATABASE_URL", _sqlalchemy_url())

        async with _HeldTransaction(_gate_dsn()) as held:
            signals = await _read_vacuum_signals()

        assert signals["xmin_age"] is not None
        assert signals["xact_age_s"] is not None
        assert signals["xact_pid"] is not None
        assert signals["xact_backend_type"] == "client backend"
        assert signals["worst_table"] == DIRTY_TABLE
        assert signals["worst_dead_pct"] >= DIRTY_PCT_FLOOR
        assert held.pid is not None

        status, per_signal = classify_vacuum_signals(
            signals["xmin_age"], signals["xact_age_s"], signals["worst_dead_pct"]
        )
        # A 99.5%-dead probe table is a genuine page on the dead-tuple signal;
        # what this arm is for is that every signal came back KNOWN.
        assert "unknown" not in per_signal.values()
        assert status == "page"
