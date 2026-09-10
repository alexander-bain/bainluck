"""#3879 — `price_observed_at` against a real server: the migration, and the
three refusals as Postgres actually evaluates them.

## why a real server, when the expression is already pinned

`tests/test_price_observed_at.py` asserts the RENDERED SQL. That is the right
test for "did the helper build the statement I meant", and it is worth very
little for "does the database do what I think that statement means" — the
distinction this lane paid for one session earlier, when a mutation survived
because a test compared statement TEXT while the value under test rode in the
bound parameters.

Two of the three refusals rest on a claim about Postgres semantics that no
amount of string matching can check:

* **`GREATEST` ignores NULL arguments.** The whole monotonicity design depends
  on it. If `GREATEST(NULL, now())` returned NULL — which is what `max()` in
  Python and `NULL + anything` in SQL would lead you to expect — then every
  FIRST observation would write NULL, the column would never populate at all,
  and #3879's census would read the entire table as unreachable. The failure
  would be total, silent, and indistinguishable from the defect being measured.
* **`NULL IS NOT NULL` is false, not NULL.** The no-price refusal is a `CASE`
  guard. A three-valued-logic surprise here would send an unpriced null-out
  down the THEN branch and stamp a fresh observation of nothing.

So both are executed, not reasoned about.

## and the migration itself

Migration-class under D45: this ships only on Alex's word, so the evidence that
it applies and reverses cleanly should exist before he is asked. The round trip
runs the real `alembic` binary as a subprocess against a scratch database, the
way the Heroku release phase does — the same rig
`test_containers_migration_real_postgres.py` established, for the same reason.

There is no local Postgres in the agent sandbox (`initdb` fails on `shmget`), so
CI is the environment that runs this — the `search-recall` job, whose service
container provides `SEARCH_TEST_DATABASE_URL`.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import uuid
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy.dialects import postgresql

from app.models import FuturesOutcome
from app.utils.migration_lock_budget import psycopg2_url
from app.utils.price_change_stamp import price_observed_at_value

BACKEND_DIR = Path(__file__).resolve().parents[2]

_RAW_URL = os.getenv("SEARCH_TEST_DATABASE_URL") or os.getenv(
    "MIGRATION_TEST_DATABASE_URL"
)

pytestmark = pytest.mark.skipif(
    not _RAW_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall job's service container) or MIGRATION_TEST_DATABASE_URL"
    ),
)

#: The revision immediately before ours — the state the undo line returns to:
#:     alembic downgrade containers_phase1
PARENT_REVISION = "containers_phase1"
THIS_REVISION = "price_observed_at"

COLUMN = "price_observed_at"
TABLE = "futures_outcomes"


def _admin_url_and_scratch_name() -> tuple[str, str]:
    sync_url = psycopg2_url(_RAW_URL)
    base, _, _ = sync_url.rpartition("/")
    return f"{base}/postgres", f"bl_pobs_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="module")
def scratch_db() -> str:
    """An empty database for the round trip; dropped afterwards."""
    admin_url, scratch = _admin_url_and_scratch_name()

    conn = psycopg2.connect(admin_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{scratch}"')
    finally:
        conn.close()

    base, _, _ = admin_url.rpartition("/")
    scratch_url = f"{base}/{scratch}"
    try:
        yield scratch_url
    finally:
        conn = psycopg2.connect(admin_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cur:
                # A leaked connection makes DROP DATABASE hang, and a hanging
                # teardown reads as a hung test.
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (scratch,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
        finally:
            conn.close()


def _alembic(scratch_url: str, *args: str) -> subprocess.CompletedProcess:
    """Alembic exactly the way the Heroku release phase runs it — a subprocess."""
    env = dict(os.environ)
    env["DATABASE_URL"] = scratch_url
    return subprocess.run(
        ["python", "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _require_alembic(scratch_url: str, *args: str) -> None:
    result = _alembic(scratch_url, *args)
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


def _column_row(conn, table: str, column: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s AND column_name=%s",
            (table, column),
        )
        return cur.fetchone()


@pytest.fixture(scope="module")
def migrated(scratch_db: str) -> dict:
    """Migrate to the parent, confirm the column is ABSENT, then migrate up.

    The absent-first check is what makes the present-after check mean anything:
    without it a column created by some earlier revision would satisfy the
    assertion and this file would be certifying a migration that did nothing.

    Module-scoped: the chain is ~113 migrations and running it per assertion
    would turn a fast gate into one nobody keeps.
    """
    _require_alembic(scratch_db, "upgrade", PARENT_REVISION)

    conn = psycopg2.connect(scratch_db)
    try:
        before = _column_row(conn, TABLE, COLUMN)
    finally:
        conn.close()

    _require_alembic(scratch_db, "upgrade", THIS_REVISION)
    return {"url": scratch_db, "before": before}


@pytest.fixture()
def pg(migrated: dict):
    """A connection to the migrated scratch database, rolled back per test."""
    conn = psycopg2.connect(migrated["url"])
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# the migration
# ---------------------------------------------------------------------------


def test_the_column_did_not_exist_before_this_revision(migrated: dict) -> None:
    assert migrated["before"] is None, (
        f"{TABLE}.{COLUMN} already existed at {PARENT_REVISION}; this migration "
        "is not what creates it and every arm below proves nothing"
    )


def test_the_migration_adds_a_nullable_timestamptz_with_no_default(pg) -> None:
    """Nullable and defaultless, checked on the SERVER rather than the model.

    The model's `Mapped[Optional[...]]` is a Python-side promise; a
    `server_default` would fabricate a stamp for every historical row the moment
    the release ran, which is gotcha #53 written into a schema, and only the
    catalogue can say whether one is there.
    """
    row = _column_row(pg, TABLE, COLUMN)
    assert row is not None, f"{TABLE}.{COLUMN} missing after upgrade"
    data_type, is_nullable, column_default = row
    assert data_type == "timestamp with time zone", data_type
    assert is_nullable == "YES", is_nullable
    assert column_default is None, column_default


def test_the_migration_adds_no_index(pg) -> None:
    """Deliberate, and asserted so a well-meaning edit has to argue with it.

    `futures_outcomes` is 5.46M rows on production. A non-concurrent
    `CREATE INDEX` holds ACCESS EXCLUSIVE for minutes against a ~5-minute
    release timeout (gotcha #31, the May 22 outage), and `CONCURRENTLY` is not
    available inside Alembic's transaction.
    """
    with pg.cursor() as cur:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname='public' AND tablename=%s AND indexdef LIKE %s",
            (TABLE, f"%{COLUMN}%"),
        )
        assert cur.fetchall() == []


def test_the_undo_line_really_puts_it_back(migrated: dict) -> None:
    """`alembic downgrade containers_phase1` — the line in the note to Alex.

    It leaves the scratch database one revision down, and the module-scoped
    fixture will not rebuild it, so this arm re-upgrades before returning rather
    than relying on where it happens to sit in the run order. pytest executes in
    DEFINITION order, not alphabetical, so a comment claiming "this one runs
    last" would be wrong as well as load-bearing.
    """
    _require_alembic(migrated["url"], "downgrade", PARENT_REVISION)
    conn = psycopg2.connect(migrated["url"])
    try:
        assert _column_row(conn, TABLE, COLUMN) is None, (
            "the downgrade left the column behind — the undo line in the "
            "alex-inbox note does not do what it says"
        )
    finally:
        conn.close()
    # Put it back so a re-run of the module in the same session is not left
    # sitting on the parent revision.
    _require_alembic(migrated["url"], "upgrade", THIS_REVISION)


# ---------------------------------------------------------------------------
# the refusals, as Postgres evaluates them
# ---------------------------------------------------------------------------


def _literal(expr) -> str:
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _evaluate(pg, stored, new_probability, observed_at=None):
    """Run the real stamp expression over a real row and read the value back.

    The expression is rendered exactly as the task code renders it, then the
    column reference is bound to a one-row scratch relation. That keeps the
    thing under test the SAME object the polls use — a hand-written SQL string
    here would be a second copy of the predicate, which is the failure
    `price_change_stamp`'s docstring exists to prevent.
    """
    expr = _literal(
        price_observed_at_value(
            FuturesOutcome.price_observed_at, new_probability, observed_at=observed_at
        )
    )
    with pg.cursor() as cur:
        cur.execute(
            f"SELECT {expr} FROM (SELECT %s::timestamptz AS price_observed_at) "
            f"AS {TABLE}",
            (stored,),
        )
        return cur.fetchone()[0]


def test_greatest_ignores_null_so_a_first_observation_populates(pg) -> None:
    """The claim the whole design rests on, executed.

    If `GREATEST(NULL, now())` were NULL, every first observation would write
    NULL, the column would never populate, and #3879's census would read the
    whole table as unreachable — a total failure indistinguishable from the
    defect it measures.
    """
    got = _evaluate(pg, stored=None, new_probability=0.42)
    assert got is not None, "GREATEST(NULL, now()) came back NULL"


def test_a_null_price_leaves_the_stored_stamp_exactly_as_it_was(pg) -> None:
    """Refusal 1 on the server: `NULL IS NOT NULL` must be FALSE, not NULL.

    A three-valued-logic surprise sends the unpriced null-out down the THEN
    branch and stamps a fresh observation of nothing.
    """
    stored = dt.datetime(2026, 2, 19, 7, 15, tzinfo=dt.timezone.utc)
    got = _evaluate(pg, stored=stored, new_probability=None)
    assert got == stored


def test_a_null_price_on_a_never_observed_row_stays_null(pg) -> None:
    """The same refusal where the ELSE branch is itself NULL.

    `kalshi.py` creates unpriced legs deliberately; polling one again must not
    invent a first observation for it.
    """
    assert _evaluate(pg, stored=None, new_probability=None) is None


def test_a_stale_replay_cannot_un_freshen_a_current_row(pg) -> None:
    """Refusal 3, and the reason refusal 2's parameter is not a loaded gun."""
    fresh = dt.datetime(2026, 9, 8, 18, 0, tzinfo=dt.timezone.utc)
    ancient = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
    got = _evaluate(pg, stored=fresh, new_probability=0.42, observed_at=ancient)
    assert got == fresh, "a historical replay moved the stamp backwards"


def test_a_newer_replay_does_advance_the_stamp(pg) -> None:
    """The other direction, so `GREATEST` is not passing by always keeping the
    stored value — which a `COALESCE(stamp, …)` bug would also do."""
    stored = dt.datetime(2026, 2, 19, 7, 15, tzinfo=dt.timezone.utc)
    newer = dt.datetime(2026, 9, 8, 18, 0, tzinfo=dt.timezone.utc)
    got = _evaluate(pg, stored=stored, new_probability=0.42, observed_at=newer)
    assert got == newer


def test_a_priced_observation_with_no_instant_advances_to_now(pg) -> None:
    """The live-writer path: no `observed_at`, so the stamp is the server clock,
    and it must beat a stored value from February rather than keep it."""
    stored = dt.datetime(2026, 2, 19, 7, 15, tzinfo=dt.timezone.utc)
    got = _evaluate(pg, stored=stored, new_probability=0.42)
    assert got > stored
