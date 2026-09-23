"""#8132's D51(b) undo, EXECUTED against a real PostgreSQL.

## why this file exists

`repair_8132_fabricated_win.py` has already been applied to 56 production rows.
D51(b) permits an unattended data repair **because** it "writes a backup first
and ships a one-command restore" — so the grant rests on
`restore_8132_fabricated_win.py` working. Until this gate, that script had no
test that ran it. Its unit band asserts against `restore_src`, the file read as
a **string**: it proves the text contains a compare-and-set, never that one
executes. An undo that has never been run is a claim, not a safeguard.

Everything the undo decides is decided by a server:

1. **`to_regclass` as the whole of "no backup, no write".** The refusal that
   stops the script writing anything on a database the repair never touched.
2. **`rowcount == 1` as the CAS verdict**, and the exit code derived from it.
   Only a server reports how many rows an `UPDATE` actually touched, and the
   difference between 1 and 0 here is the difference between "undone" and
   "someone else's decision was left standing".
3. **The `LEFT JOIN` arm** — a banked leg whose outcome row is gone comes back
   as a NULL, and the plan must report it rather than invent a value.
4. **Three-way state comparison over real column types.** `is_winner` is a
   nullable boolean and `resolution_source` a nullable text; the plan separates
   ALREADY_BACK from RESTORE from DIVERGED by comparing both against two stored
   tuples. A mock returns whatever the author expected.

## what this gate does NOT claim

It does not grade the repair's derivation. `derive()` reads
`settlement_captures` and grades every row against `EXPECTED`, a table of 56
production outcome ids measured on 2026-09-23 — a corpus this gate cannot
reproduce and should not pretend to. What it drives instead is the repair's two
**writing** functions, `bank_pre_image` and `apply_plan`, which is the real
forward write and the true origin of the pre-image the undo reads. The
derivation and the plan's verdicts are the unit band's subject.

## the corpus, and what each leg can fail on

All five legs are seeded as the defect shape — `is_winner = TRUE` with a
resolution source — and all five are repaired by the shipped forward write.
What separates them is what happens to the row AFTERWARDS:

* **`untouched`** — nothing. The only leg the undo may write.
* **`regraded`** — a grader settled it properly after the repair: still
  `is_winner = false`, but the source moved to `manual_grade`. The likeliest
  real divergence, because a repaired leg is precisely a leg someone may since
  have graded for real.
* **`recrowned`** — a price crowner handed the win back (`is_winner = true`,
  `price_crown`). This is #8132's own failure mode, which is why the repair
  refuses to run under a binary without the crowner guard.
* **`vanished`** — the outcome row is deleted. Exercises the `LEFT JOIN`.
* **`drifter`** — moves *between* the plan and the write, which is a different
  code path from `regraded`: the plan says RESTORE and the CAS refuses it.

`test_the_seeded_corpus_can_distinguish_the_wrong_answers` asserts those shapes
before anything is measured, so a later edit to the seed cannot quietly make the
rest vacuous, and `test_an_id_keyed_undo_would_have_stomped_the_spared_rows` is
the strawman: the same sequence without the CAS must produce the damage.

There is no PostgreSQL in the agent sandbox by default, so CI's `search-recall`
job is where this normally runs; its skip detection is what stops a silently
skipped gate reading as a passing one.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8132 undo gate "
        "(CI job `search-recall` provides one)"
    ),
)

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path.

    `scripts/` is not a package and is not on `sys.path` under pytest, so the
    restore's own `sys.path.insert` of its directory is what makes its sibling
    `from repair_8132_fabricated_win import ...` resolve. Loading by path here
    exercises exactly that seam — the same loader the unit band uses.
    """
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_8132_fabricated_win")
restore = _load("restore_8132_fabricated_win")

MARKET_ID = 81320001

#: `key -> (outcome_id, prior resolution_source, the stamp the repair writes)`.
#:
#: Both retraction stamps are present, so the CAS's `= :target` is exercised on
#: each of them rather than on one value twice.
LEGS: dict[str, tuple[int, str, str]] = {
    "untouched": (81321001, "clean_resolution", "api_settlement"),
    "regraded": (81321002, "clean_resolution", "api_settlement"),
    "recrowned": (81321003, "game_score", "ungradeable_result"),
    "vanished": (81321004, "clean_resolution", "api_settlement"),
    "drifter": (81321005, "clean_resolution", "api_settlement"),
}

#: The pre-image every leg must be restorable to: the fabricated win.
PRE_IMAGE = {name: (True, prior) for name, (_, prior, _) in LEGS.items()}

#: What the forward write leaves behind.
POST_REPAIR = {name: (False, target) for name, (_, _, target) in LEGS.items()}


def _sync_url(url: str) -> str:
    """The same database through psycopg2, for the one arm that needs a second
    connection from inside a synchronous callback."""
    return url.replace("+asyncpg", "").replace("postgresql+psycopg2", "postgresql")


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


async def _clear(conn) -> None:
    """Remove this file's own rows and its runtime DDL — by id, never by DROP.

    Two separate reasons, and both are about the database being SHARED.

    `search-recall` runs every real-Postgres gate in sequence against ONE
    database, so `Base.metadata.drop_all` here is not a local reset: it raises
    `DependentObjectsStillExistError` on the foreign keys of whatever a sibling
    gate left, and when it does not raise it deletes their rows. Delete by id
    instead (measured convention: #7147, #2772, the #836/#837 blend race).

    `backup_8132_fabricated_win` IS dropped, because it is this file's own
    runtime DDL rather than shared schema — it is created on demand by
    `bank_pre_image` and is not on `Base.metadata`, so nothing else would ever
    clean it. Dropped on the way IN so no arm inherits another arm's pre-image,
    and on the way OUT so the next gate finds the database as this one did.
    """
    await conn.execute(text(f"DROP TABLE IF EXISTS {repair.BACKUP_TABLE}"))
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = :m"), {"m": MARKET_ID}
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = :m"), {"m": MARKET_ID}
    )


@pytest.fixture
async def pg_engine():
    """Real Postgres holding the real definitions of the tables this gate uses.

    A NAMED SUBSET, not `Base.metadata.create_all`, and the reason is the one
    `test_completed_espn_final_is_not_repoisoned_7147_pg.py` records: the full
    metadata carries a `NULLS NOT DISTINCT` index, which is PostgreSQL 15
    syntax, so whole-schema `create_all` dies on a developer's Homebrew
    Postgres 14 and confines the gate to CI. A gate that can be run where the
    code is written is a gate that gets run — and this one grades an undo whose
    forward half is already applied to production.

    The subset is built from the real models, so `is_winner`'s nullability and
    `resolution_source`'s type are the production ones; `sports`, `teams`,
    `venues` and `events` are here only because the two tables under test carry
    foreign keys into them.

    Function-scoped for the reason the #6215 gate gives: `pytest.ini` leaves
    `asyncio_default_fixture_loop_scope` unset, so a module-scoped async fixture
    would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "futures_markets",
            "futures_outcomes",
        )
    ]
    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await _clear(conn)
        await engine.dispose()


@pytest.fixture
async def session(pg_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # Both scripts refuse to run anywhere but the producer app, and that refusal
    # is checked before anything else. Set it once for the whole file; the arm
    # that grades the refusal unsets it again.
    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        await _seed(s)
        yield s


async def _seed(s) -> None:
    """Insert the corpus through the ORM.

    The ORM and not raw INSERT: `futures_markets` carries client-side defaults a
    raw INSERT would silently omit, and `test_pg_gate_seed_completeness.py`'s
    raw-INSERT arm keys on the presence of `INSERT INTO`.
    """
    from app.models import FuturesMarket, FuturesOutcome

    s.add(
        FuturesMarket(
            id=MARKET_ID,
            source="kalshi",
            external_id="KX8132GATE",
            name="#8132 undo gate board",
            category="championship",
            market_tier=5,
            status="resolved",
        )
    )
    for name, (oid, prior, _) in LEGS.items():
        s.add(
            FuturesOutcome(
                id=oid,
                market_id=MARKET_ID,
                external_id=f"KX8132GATE-{name.upper()}",
                name=name,
                # The defect shape: a win the venue never declared.
                is_winner=True,
                resolution_source=prior,
            )
        )
    await s.commit()


async def _state(s) -> dict[str, tuple]:
    """`(is_winner, resolution_source)` per leg, by name. A deleted row is None."""
    rows = (
        await s.execute(
            text(
                "SELECT id, is_winner, resolution_source FROM futures_outcomes "
                "WHERE market_id = :m"
            ),
            {"m": MARKET_ID},
        )
    ).all()
    by_id = {int(r[0]): (r[1], r[2]) for r in rows}
    return {name: by_id.get(oid) for name, (oid, _, _) in LEGS.items()}


def _writable(only: tuple[str, ...] | None = None) -> list[dict]:
    """The plan rows the forward write consumes, in `derive()`'s own shape."""
    names = only if only is not None else tuple(LEGS)
    return [
        {
            "outcome_id": LEGS[name][0],
            "market_id": MARKET_ID,
            "ticker": f"KX8132GATE-{name.upper()}",
            "is_winner": True,
            "prior_source": LEGS[name][1],
            "target_source": LEGS[name][2],
            "verdict": repair.REPAIR,
            "why": "",
        }
        for name in names
    ]


async def _apply_the_repair(s, only: tuple[str, ...] | None = None) -> None:
    """The SHIPPED forward write, in the documented order: bank, then update."""
    rows = _writable(only)
    await repair.bank_pre_image(s, rows)
    stats = await repair.apply_plan(s, rows)
    await s.commit()
    assert stats == {"written": len(rows), "concurrent_drift": 0}, stats


@contextlib.asynccontextmanager
async def _yield(s):
    yield s


def _point_at(s, monkeypatch) -> None:
    """Point the shipped undo's session factory at this database.

    🪤 It must be patched on the RESTORE MODULE, not on `app.tasks.base`.
    `restore_8132_fabricated_win` does `from app.tasks.base import
    get_task_session` at import time, which binds the function into its own
    namespace — patching the source module afterwards is inert, and the script
    would quietly open a second connection to whatever `DATABASE_URL` names.
    (Sibling gates patch `base` because their scripts import inside the
    function; the two forms are not interchangeable.)

    The redirect is self-proving: nothing but this database has the pre-image
    table, so a misdirected run would find no backup and exit 2.
    """
    monkeypatch.setattr(restore, "get_task_session", lambda: _yield(s))


async def _restore(s, monkeypatch, *, apply: bool) -> int:
    """Execute the SHIPPED undo. Returns its exit code."""
    _point_at(s, monkeypatch)
    return await restore.run(apply)


# ── the corpus is capable of failing ────────────────────────────────────────


@needs_postgres
async def test_the_seeded_corpus_can_distinguish_the_wrong_answers(session):
    assert await _state(session) == PRE_IMAGE

    await _apply_the_repair(session)

    # The BEFORE of the undo differs from its target on every leg, so "restored"
    # is a real assertion and not a state the row was already in.
    after = await _state(session)
    assert after == POST_REPAIR
    for name in LEGS:
        assert after[name] != PRE_IMAGE[name]

    # Both retraction stamps are present, so `= :target` is decidable here.
    assert {v[2] for v in LEGS.values()} == {"api_settlement", "ungradeable_result"}

    # The pre-image really was banked by the shipped function, not by the test.
    banked = (
        await session.execute(
            text(f"SELECT count(*) FROM {repair.BACKUP_TABLE}")
        )
    ).scalar_one()
    assert int(banked) == len(LEGS)


# ── the round trip ──────────────────────────────────────────────────────────


@needs_postgres
async def test_the_undo_puts_back_exactly_what_the_repair_wrote(session, monkeypatch):
    await _apply_the_repair(session, only=("untouched",))

    assert await _restore(session, monkeypatch, apply=True) == 0

    after = await _state(session)
    assert after["untouched"] == PRE_IMAGE["untouched"]
    # Both columns, not just the flag: a restore that put `is_winner` back and
    # left the retraction stamp standing would leave the row self-contradictory.
    assert after["untouched"] == (True, "clean_resolution")


@needs_postgres
async def test_a_dry_run_writes_nothing(session, monkeypatch):
    await _apply_the_repair(session, only=("untouched",))

    assert await _restore(session, monkeypatch, apply=False) == 0

    assert (await _state(session))["untouched"] == POST_REPAIR["untouched"]


@needs_postgres
async def test_a_second_apply_is_a_no_op(session, monkeypatch):
    """The idempotence claim, which is entirely the compare-and-set."""
    await _apply_the_repair(session, only=("untouched",))
    assert await _restore(session, monkeypatch, apply=True) == 0
    before = await _state(session)

    assert await _restore(session, monkeypatch, apply=True) == 0

    assert await _state(session) == before


# ── the rows the undo must refuse to undo ───────────────────────────────────


@needs_postgres
async def test_the_undo_spares_a_leg_a_grader_regraded_after_the_repair(
    session, monkeypatch
):
    """The clause the whole D51(b) grant turns on.

    A repaired leg is precisely a leg some grader may since have settled
    properly. An undo that stomps that decision to put a fabricated win back is
    not an undo.
    """
    await _apply_the_repair(session, only=("untouched", "regraded"))
    await session.execute(
        text(
            "UPDATE futures_outcomes SET resolution_source = 'manual_grade' "
            "WHERE id = :i"
        ),
        {"i": LEGS["regraded"][0]},
    )
    await session.commit()

    assert await _restore(session, monkeypatch, apply=True) == 0

    after = await _state(session)
    assert after["regraded"] == (False, "manual_grade"), "the undo stomped a grader"
    # ...and the leg beside it was still restored, so this is not a whole-run
    # refusal being read as per-row care.
    assert after["untouched"] == PRE_IMAGE["untouched"]


@needs_postgres
async def test_the_undo_spares_a_leg_a_price_crowner_handed_back(
    session, monkeypatch
):
    """#8132's own failure mode, arriving from the other direction.

    A crowner that re-crowns a repaired leg reinstates the win under a DIFFERENT
    stamp. The row is no longer what the repair wrote, so the undo leaves it —
    the fabricated win here is the crowner's to answer for, not the backup's.
    """
    await _apply_the_repair(session, only=("untouched", "recrowned"))
    await session.execute(
        text(
            "UPDATE futures_outcomes SET is_winner = true, "
            "resolution_source = 'price_crown' WHERE id = :i"
        ),
        {"i": LEGS["recrowned"][0]},
    )
    await session.commit()

    assert await _restore(session, monkeypatch, apply=True) == 0

    after = await _state(session)
    assert after["recrowned"] == (True, "price_crown")
    assert after["untouched"] == PRE_IMAGE["untouched"]


@needs_postgres
async def test_an_id_keyed_undo_would_have_stomped_the_spared_rows(session):
    """The strawman, so the two arms above are not passing for free.

    The same sequence with the CAS deleted — an undo keyed on `outcome_id`
    alone, which is the obvious way to write one — must produce the damage. If
    this ever goes green, the divergence is no longer reproducible here and
    those arms have stopped testing what they say.
    """
    await _apply_the_repair(session, only=("regraded",))
    await session.execute(
        text(
            "UPDATE futures_outcomes SET resolution_source = 'manual_grade' "
            "WHERE id = :i"
        ),
        {"i": LEGS["regraded"][0]},
    )
    await session.commit()

    await session.execute(
        text(f"""
            UPDATE futures_outcomes fo
            SET is_winner = b.prior_is_winner,
                resolution_source = b.prior_source
            FROM {repair.BACKUP_TABLE} b
            WHERE fo.id = b.outcome_id
        """)
    )
    await session.commit()

    assert (await _state(session))["regraded"] == PRE_IMAGE["regraded"], (
        "an id-keyed undo did not stomp the grader, so the CAS arms above are "
        "proving something easier than they claim"
    )


@needs_postgres
async def test_a_missing_outcome_row_is_reported_not_invented(session, monkeypatch):
    """The `LEFT JOIN` arm: a banked leg whose row is gone.

    `NO_BACKUP` here reads oddly — the backup is present and the OUTCOME is
    missing — but the behaviour is the one that matters: no `INSERT`, no
    resurrection, and the row named in the report.
    """
    await _apply_the_repair(session, only=("untouched", "vanished"))
    await session.execute(
        text("DELETE FROM futures_outcomes WHERE id = :i"),
        {"i": LEGS["vanished"][0]},
    )
    await session.commit()

    assert await _restore(session, monkeypatch, apply=True) == 0

    after = await _state(session)
    assert after["vanished"] is None, "the undo re-created a deleted outcome row"
    assert after["untouched"] == PRE_IMAGE["untouched"]


# ── the write-time race, which is a different path from a diverged plan ─────


@needs_postgres
async def test_a_row_that_moves_between_the_plan_and_the_write_is_reported(
    session, monkeypatch
):
    """`rowcount == 0` is the only thing that can see this, and it sets exit 1.

    `regraded` above diverges at PLAN time — the SELECT sees it and the row is
    never a candidate. This is the other half: the plan says RESTORE and the row
    moves before the `UPDATE` reaches it. Nothing but the server's report of how
    many rows it touched can tell the two apart, and the difference is visible to
    an operator as the exit code.

    🪤 The drift is committed from a SECOND connection inside the script's own
    `print`, which is the only seam between the plan's SELECT and the write
    loop. psycopg2 and not the async session because the callback is
    synchronous. If a later edit moves every print after the loop this arm does
    not go quietly vacuous: the drift would then land before the SELECT, the row
    would plan as DIVERGED, the exit code would be 0 and the assertion below
    would fail loudly.
    """
    import psycopg2

    await _apply_the_repair(session, only=("drifter",))

    fired = []

    def _drift_then_print(*args, **kwargs):
        if not fired:
            fired.append(True)
            conn = psycopg2.connect(_sync_url(DB_URL))
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE futures_outcomes SET resolution_source = "
                        "'manual_grade' WHERE id = %s",
                        (LEGS["drifter"][0],),
                    )
                conn.commit()
            finally:
                conn.close()

    # `print` is resolved as a module global before the builtin, so this binds
    # for the duration of the call and nothing else in the process is affected.
    monkeypatch.setattr(restore, "print", _drift_then_print, raising=False)

    code = await _restore(session, monkeypatch, apply=True)

    assert fired, "the injection point never ran — the arm proved nothing"
    assert code == 1, "concurrent drift did not reach the operator's exit code"
    assert (await _state(session))["drifter"] == (False, "manual_grade"), (
        "the CAS overwrote a row that moved after the plan was built"
    )


# ── the refusals, which must happen before anything is written ──────────────


@needs_postgres
async def test_no_backup_table_means_no_write_and_exit_2(session, monkeypatch):
    """`to_regclass` is the whole of this, and it is the guard that stops the
    script writing on a database the repair never ran against."""
    before = await _state(session)
    assert (
        await session.execute(
            text("SELECT to_regclass(:n)"), {"n": repair.BACKUP_TABLE}
        )
    ).scalar() is None, "the fixture left a pre-image behind"

    assert await _restore(session, monkeypatch, apply=True) == 2

    assert await _state(session) == before


@needs_postgres
async def test_the_wrong_app_refuses_before_reading_the_database(
    session, monkeypatch
):
    """Notice 47(c): the attended invocation on the named app IS the gate."""
    await _apply_the_repair(session, only=("untouched",))
    before = await _state(session)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")

    assert await _restore(session, monkeypatch, apply=True) == 2

    assert await _state(session) == before


# ── a recorded limit, pinned so widening the population cannot miss it ──────


@needs_postgres
async def test_a_null_prior_source_comes_back_as_the_empty_string(
    session, monkeypatch
):
    """NOT a bug report — a pinned limit, and the reason it is not being fixed.

    `_population_sql` selects `COALESCE(fo.resolution_source, '')`, and
    `backup_8132_fabricated_win.prior_source` is `TEXT NOT NULL`, so a leg whose
    source was NULL banks `''` and is restored as `''`. NULL and `''` are not the
    same thing to a reader: #4788's render rule prints no verdict for
    `resolution_source IS NULL`, and an empty string is not null.

    It is unreachable for the cohort the repair exists for — all 56 rows in
    `EXPECTED` carry a real source — but it IS reachable under `--include-new`,
    which is why it is pinned here rather than left to be discovered. Fixing it
    means a nullable backup column, and that table already holds the 56-row
    production pre-image; changing its DDL under a banked backup is a worse risk
    than the lossiness. Whoever widens this population owns the decision.
    """
    oid = LEGS["untouched"][0]
    await session.execute(
        text("UPDATE futures_outcomes SET resolution_source = NULL WHERE id = :i"),
        {"i": oid},
    )
    await session.commit()

    rows = _writable(only=("untouched",))
    rows[0]["prior_source"] = ""  # what `derive()` would have produced
    await repair.bank_pre_image(session, rows)
    await repair.apply_plan(session, rows)
    await session.commit()

    assert await _restore(session, monkeypatch, apply=True) == 0

    assert (await _state(session))["untouched"] == (True, ""), (
        "the NULL round-tripped after all — drop this pin and say so"
    )
