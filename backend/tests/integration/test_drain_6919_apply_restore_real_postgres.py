"""#6919 — the attended drain's WRITE and its D51 UNDO, executed on a real PostgreSQL.

## why this file exists, stated precisely

`test_repair_6919_stranded_settled_drain.py` carries sixteen guards and every one
of them is a pure-function test: `classify`, `venue_says_settled`,
`backup_is_exact`, `wrong_app_refusal`. They are the right tool for "which rows
does this script *decide* to touch", and they are what proved the gate refuses
the Pokrovskoe and Romania ladders.

**Not one of them executes a statement.** `restore_6919_stranded_settled_polymarket_markets.py`
had no test of any kind before this file. That matters more here than it would
anywhere else in the repo, because D51(b) is what permits this repair to be
applied to production unattended, and D51(b) permits it *because there is a
backup and a one-command undo*. An undo that has never been run is a claim, not
a safeguard — and the failure mode of a broken undo is that you discover it in
the minute you need it, on rows you have already changed.

Five behaviours in this pair are the SERVER's, and a stub session fakes every
one of them because the stub is also the thing deciding what comes back:

* **`RETURNING settled_at` on the repair's compare-and-swap.** The value it hands
  back is what the manifest records as `set_settled_at`, and what the restore
  later compare-and-swaps against. Derived instead of returned it would be a
  guess about a `COALESCE`.
* **`COALESCE(settled_at, :now)` over a stored value.** A row that already
  carried a stamp must keep it, or the manifest records a move that did not
  happen and the undo writes a lie back.
* **`rowcount` / `fetchone() is None` as the CAS verdict.** "Did this write
  land" is produced by the driver from an executed statement; both scripts
  branch on it, and both branches are unreachable under a stub.
* **`to_regclass(...) IS NOT NULL`** is the whole of "no backup, no write".
* **`settled_at IS NOT DISTINCT FROM :set_settled_at` in the undo's CAS.** The
  clause that makes the undo decline a row another rail moved after the repair.

## the arm that is the reason for the file

`test_the_undo_leaves_alone_a_row_another_rail_moved_after_the_repair`.

The restore's docstring states, at length, that it restores from the MANIFEST and
not from the backup, because a snapshot cannot record *which script* changed a
row — so a snapshot-driven undo re-opens a market that
`sync_polymarket_resolved_status` or the CLOB websocket closed legitimately in
the meantime. That lesson is inherited from CERT-2439, which blocked #4586's
restore for exactly it.

Until this file, that reasoning existed only as prose. The arm executes it: a row
is drained, a second writer then re-stamps it, and the undo must leave it
resolved, keep its manifest entry, and report it as declined. Deleting the
`IS NOT DISTINCT FROM` half of the CAS is a change that every existing test in
this repo passes and this arm does not.

## it runs the SHIPPED scripts, never a retyped copy

Every arm calls `repair.run(...)` and `restore.run(...)` with `get_task_session`
pointed at the test database. The SQL is never restated here — a gate that
re-types the UPDATE proves the typist agreed with themselves. Only the venue
half is substituted (`venue_event`), because it is an HTTP call to Gamma and the
sixteen unit guards already own what it returns.

## the corpus: three rows, two of which must drain

All three satisfy `_CANDIDATE_SQL`'s structural gate — Polymarket, not
`resolved`, at least one leg, no leg with a NULL `resolution_source` — so all
three reach the venue question and the gate is the only thing separating them.

* **`PLAIN`** — `status='open'`, `settled_at` NULL, one graded winner, venue
  closed. The shape of all five production specimens (60755454/56/59/66/68).
  **Drains.** Its undo is the one that must write NULL *back*: a row left
  wearing a settlement time for a settlement that has been withdrawn is the
  defect the restore's `old_settled_at` column exists to prevent.
* **`STAMPED`** — the same, but already carrying a `settled_at` from a day
  earlier. **Drains**, and the `COALESCE` must not move the stamp, which makes
  `old_settled_at == set_settled_at` and the undo a no-op on that column *by
  construction* rather than by luck.
* **`LIVE`** — every leg graded, and the venue still lists the event open. The
  Pokrovskoe shape. **Must never be planned, backed up, closed or manifested.**
  It is here so that an arm asserting "2 rows moved" cannot pass by moving three.
"""

from __future__ import annotations

import contextlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6919 drain "
        "apply/restore gate (CI job `search-recall` provides one)"
    ),
)

#: A day before the pass, so a restamp would be unmistakable rather than a
#: rounding difference.
PRIOR_STAMP = datetime(2026, 9, 17, 17, 30, tzinfo=timezone.utc)

PLAIN, STAMPED, LIVE = 69191001, 69191002, 69191003

#: Every row the drain must close, and the one it must not. Named once so no arm
#: can drift from the docstring.
MUST_DRAIN = (PLAIN, STAMPED)
MUST_SURVIVE = (LIVE,)

#: Gamma EVENT ids. `venue_event` is keyed on `external_id`, so the fake venue
#: below answers per row through the same door the real one does.
EXT = {PLAIN: "1004380", STAMPED: "1004381", LIVE: "1004382"}

BAK_TABLE = "bak_6919_futures_markets"
MANIFEST_TABLE = "bak_6919_repair_manifest"


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


async def _drop_runtime_tables(engine) -> None:
    """Remove the repair's runtime DDL. Setup AND teardown, and teardown is the
    one that is load-bearing for the rest of the job.

    `bak_create` is `CREATE TABLE ... (LIKE futures_markets INCLUDING DEFAULTS)`,
    and `INCLUDING DEFAULTS` copies `id`'s default EXPRESSION — which is
    `nextval('futures_markets_id_seq')`. The backup table therefore holds a
    dependency on the SOURCE table's sequence, so while it exists

        DROP TABLE futures_markets

    fails with `DependentObjectsStillExistError`. Neither table is on
    `Base.metadata`, so `drop_all` cannot see either one.

    The `search-recall` job runs its real-Postgres gates in sequence against ONE
    database, and the next gate's fixture begins by dropping the schema. Leaving
    these two tables behind therefore does not fail THIS file — it fails the
    gate that runs after it, several hundred lines away, with an error naming
    neither #6919 nor this test. Measured: with setup-only cleanup, this file
    passed 10/10 and `test_search_diacritic_fold_pg_6977.py` then raised 5
    errors, locally and in CI alike.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {MANIFEST_TABLE}"))
        await conn.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt.

    Cleans the repair's runtime tables on the way IN so no arm inherits another
    arm's manifest, and on the way OUT so the database is left exactly as it was
    found — see :func:`_drop_runtime_tables` for why the second one matters to a
    gate this file never mentions.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(_asyncpg_url(DB_URL))
    await _drop_runtime_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            yield s
    finally:
        await _drop_runtime_tables(engine)
        await engine.dispose()


async def _seed(session):
    """Insert the corpus through the ORM.

    The ORM and not raw INSERT: `futures_markets` carries client-side defaults
    a raw INSERT would not apply, and `test_pg_gate_seed_completeness.py`'s
    raw-INSERT arm keys on the presence of `INSERT INTO`.
    """
    from app.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)
    # (id, settled_at)
    for mid, settled_at in ((PLAIN, None), (STAMPED, PRIOR_STAMP), (LIVE, None)):
        session.add(
            FuturesMarket(
                id=mid,
                source="polymarket",
                external_id=EXT[mid],
                name=f"seed market {mid}",
                llm_sport_category="baseball",
                market_tier=5,
                status="open",
                settled_at=settled_at,
                event_id=None,
                commence_time=now - timedelta(hours=6),
            )
        )
    # Every leg graded — that is what puts all three past the structural gate and
    # leaves the venue question as the only discriminator.
    for oid, mid, winner in (
        (69191101, PLAIN, True),
        (69191102, STAMPED, True),
        (69191103, LIVE, True),
    ):
        session.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"{EXT[mid]}_yes",
                name="Yes",
                is_winner=winner,
                resolution_source="api_settlement",
            )
        )
    await session.commit()


def _venue(closed: bool) -> dict:
    """A Gamma answer in the shape `classify` reads."""
    return {
        "reachable": True,
        "event_closed": closed,
        "event_active": not closed,
        "children": 1,
        "children_closed": 1 if closed else 0,
        "end_date": None,
        "reason": "",
    }


@contextlib.asynccontextmanager
async def _yield(session):
    yield session


def _point_at(module, session, monkeypatch):
    """Point the shipped script's session factory at this database."""
    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", lambda: _yield(session))
    return module


async def _repair(session, monkeypatch, *, backup=False, apply=False) -> int:
    """Execute the SHIPPED repair. Returns its exit code."""
    from scripts import repair_6919_stranded_settled_polymarket_markets as repair

    _point_at(repair, session, monkeypatch)
    # LIVE is the only row the venue still lists open; the other two are closed.
    monkeypatch.setattr(
        repair, "venue_event",
        lambda ext: _venue(closed=(ext != EXT[LIVE])),
    )
    # The real pause is a courtesy to Gamma's limiter and buys this gate nothing.
    monkeypatch.setattr(repair, "VENUE_PAUSE", 0)
    return await repair.run(SimpleNamespace(backup=backup, apply=apply))


async def _restore(session, monkeypatch, *, apply=False) -> int:
    """Execute the SHIPPED undo. Returns its exit code."""
    from scripts import restore_6919_stranded_settled_polymarket_markets as restore

    _point_at(restore, session, monkeypatch)
    return await restore.run(SimpleNamespace(apply=apply))


async def _rows(session) -> dict[int, tuple]:
    from sqlalchemy import text

    res = await session.execute(text(
        "SELECT id, status, settled_at FROM futures_markets ORDER BY id"
    ))
    return {r.id: (r.status, r.settled_at) for r in res.fetchall()}


async def _count(session, table) -> int:
    from sqlalchemy import text

    res = await session.execute(text(f"SELECT to_regclass('{table}') IS NOT NULL"))
    if not res.scalar_one():
        return 0
    res = await session.execute(text(f"SELECT count(*) FROM {table}"))
    return int(res.scalar_one())


async def _manifest(session) -> dict[int, tuple]:
    from sqlalchemy import text

    if not await _count(session, MANIFEST_TABLE):
        return {}
    res = await session.execute(text(
        f"SELECT market_id, old_status, old_settled_at, set_settled_at "
        f"FROM {MANIFEST_TABLE} ORDER BY market_id"
    ))
    return {
        r.market_id: (r.old_status, r.old_settled_at, r.set_settled_at)
        for r in res.fetchall()
    }


async def _drain(session, monkeypatch) -> None:
    """The attended sequence exactly as an operator runs it: backup, then apply."""
    assert await _repair(session, monkeypatch, backup=True) == 0
    assert await _repair(session, monkeypatch, apply=True) == 0


@needs_postgres
@pytest.mark.asyncio
class TestTheWriteLands:
    async def test_only_the_planned_rows_move_and_the_live_ladder_survives(
        self, session, monkeypatch
    ):
        await _seed(session)
        before = await _rows(session)
        await _drain(session, monkeypatch)
        after = await _rows(session)

        for mid in MUST_DRAIN:
            assert after[mid][0] == "resolved", f"{mid} should have drained"
        for mid in MUST_SURVIVE:
            assert after[mid] == before[mid], (
                f"{mid} is open at the venue and must not have been touched"
            )

    async def test_the_backup_table_inherits_the_sources_sequence_so_teardown_is_required(
        self, session, monkeypatch
    ):
        """Pin the reason `_drop_runtime_tables` runs on the way out.

        `INCLUDING DEFAULTS` copies `id`'s default EXPRESSION, so the backup
        table depends on `futures_markets_id_seq` and blocks
        `DROP TABLE futures_markets` for as long as it exists. That is a fact
        about the SHIPPED `bak_create`, not about this file, and it is asserted
        here so that deleting the teardown reds an arm whose name says why —
        rather than reddening the next gate in the job with an error naming
        neither #6919 nor this test.
        """
        from sqlalchemy import text

        await _seed(session)
        assert await _repair(session, monkeypatch, backup=True) == 0

        default = (await session.execute(text(
            "SELECT column_default FROM information_schema.columns "
            f"WHERE table_name = '{BAK_TABLE}' AND column_name = 'id'"
        ))).scalar_one()
        assert default and "futures_markets_id_seq" in default, (
            "if the backup stops inheriting the source's sequence this arm may "
            "be retired — but check the teardown before retiring it"
        )

    async def test_the_backup_and_manifest_hold_the_drained_rows_and_only_those(
        self, session, monkeypatch
    ):
        await _seed(session)
        await _drain(session, monkeypatch)

        assert await _count(session, BAK_TABLE) == len(MUST_DRAIN)
        assert sorted(await _manifest(session)) == sorted(MUST_DRAIN)

    async def test_a_stamp_that_was_already_set_is_not_moved_by_the_coalesce(
        self, session, monkeypatch
    ):
        await _seed(session)
        await _drain(session, monkeypatch)

        after = await _rows(session)
        assert after[STAMPED][1] == PRIOR_STAMP, (
            "COALESCE(settled_at, :now) must leave a stamp that was already set"
        )
        old_status, old_at, set_at = (await _manifest(session))[STAMPED]
        assert old_status == "open"
        assert old_at == set_at == PRIOR_STAMP, (
            "the manifest must record the value RETURNING handed back, so the "
            "undo's column write is a no-op by construction for this row"
        )

    async def test_the_plain_row_is_stamped_and_the_manifest_remembers_the_null(
        self, session, monkeypatch
    ):
        await _seed(session)
        await _drain(session, monkeypatch)

        after = await _rows(session)
        assert after[PLAIN][1] is not None, "the drain stamps an unstamped row"
        old_status, old_at, set_at = (await _manifest(session))[PLAIN]
        assert (old_status, old_at) == ("open", None)
        assert set_at == after[PLAIN][1]


@needs_postgres
@pytest.mark.asyncio
class TestNoBackupNoWrite:
    async def test_apply_refuses_when_the_backup_table_does_not_exist(
        self, session, monkeypatch
    ):
        await _seed(session)
        before = await _rows(session)

        assert await _repair(session, monkeypatch, apply=True) == 1
        assert await _rows(session) == before, "D51: no undo, no write"
        assert await _count(session, MANIFEST_TABLE) == 0


@needs_postgres
@pytest.mark.asyncio
class TestTheUndo:
    async def test_the_undo_returns_every_row_to_exactly_its_pre_repair_state(
        self, session, monkeypatch
    ):
        await _seed(session)
        before = await _rows(session)

        await _drain(session, monkeypatch)
        assert await _rows(session) != before, "strawman: the drain must have moved something"

        assert await _restore(session, monkeypatch, apply=True) == 0
        assert await _rows(session) == before, (
            "the undo must return status AND settled_at, on every row"
        )

    async def test_the_undo_writes_the_null_back_and_does_not_leave_a_withdrawn_stamp(
        self, session, monkeypatch
    ):
        await _seed(session)
        await _drain(session, monkeypatch)
        assert (await _rows(session))[PLAIN][1] is not None

        await _restore(session, monkeypatch, apply=True)

        assert (await _rows(session))[PLAIN][1] is None, (
            "a row whose settlement has been withdrawn may not keep wearing a "
            "settlement time"
        )

    async def test_a_spent_manifest_row_is_removed_so_a_second_undo_is_a_no_op(
        self, session, monkeypatch
    ):
        await _seed(session)
        await _drain(session, monkeypatch)
        await _restore(session, monkeypatch, apply=True)

        assert await _manifest(session) == {}
        after_first = await _rows(session)
        assert await _restore(session, monkeypatch, apply=True) == 0
        assert await _rows(session) == after_first

    async def test_a_plan_only_run_reports_and_changes_nothing(
        self, session, monkeypatch
    ):
        await _seed(session)
        await _drain(session, monkeypatch)
        drained = await _rows(session)

        assert await _restore(session, monkeypatch, apply=False) == 0
        assert await _rows(session) == drained
        assert sorted(await _manifest(session)) == sorted(MUST_DRAIN)

    async def test_the_undo_leaves_alone_a_row_another_rail_moved_after_the_repair(
        self, session, monkeypatch
    ):
        """The CERT-2439 lesson, executed instead of quoted.

        `sync_polymarket_resolved_status` and the CLOB websocket close Polymarket
        rows on their own schedule. A row this repair drained, which one of them
        then re-stamped, is no longer the repair's move to undo — and an undo
        built on the backup snapshot could not tell the difference.
        """
        from sqlalchemy import text

        await _seed(session)
        await _drain(session, monkeypatch)

        # A second writer moves PLAIN after the drain, as the live rails do.
        later = datetime.now(timezone.utc) + timedelta(minutes=5)
        await session.execute(
            text("UPDATE futures_markets SET settled_at = :t WHERE id = :mid"),
            {"t": later, "mid": PLAIN},
        )
        await session.commit()

        assert await _restore(session, monkeypatch, apply=True) == 0

        after = await _rows(session)
        assert after[PLAIN] == ("resolved", later), (
            "the undo must not overwrite a newer decision"
        )
        assert after[STAMPED][0] == "open", (
            "and it must still undo the row that DID NOT move"
        )

        manifest = await _manifest(session)
        assert sorted(manifest) == [PLAIN], (
            "the declined row keeps its manifest entry; the undone row's is spent"
        )
