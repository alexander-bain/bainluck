"""#4586's undo reverts only what the repair moved — on a REAL PostgreSQL.

CERT-2439's required repair, `4586-RESTORE-CAS-PRESERVES-LATER-RELINKS`.

## the defect this gate exists for

`repair_4586_stranded_voided_event_markets.py` moves a stranded market off a
voided phantom event and onto the real fixture, compare-and-swapping on the link
it planned so that a market the live matcher relinked in between is SKIPPED
rather than dragged back from stale state. That half was right.

The undo was not. It restored from the row-snapshot backup alone:

    UPDATE futures_markets f SET event_id = b.event_id
      FROM bak_4586_futures_markets b
     WHERE b.id = f.id AND f.event_id IS DISTINCT FROM b.event_id

"differs from its backup" is true for a row this repair moved AND for a row
something else moved after the backup was taken — including the very rows the
forward compare-and-swap correctly declined to touch. So the one-command D51
undo would put a market the repair never moved back onto the voided phantom,
destroying a newer, legitimate matcher decision. The grader reproduced it
against the exact predicate: market 1 on target 20 (backup 10) and market 2
independently relinked to 30 (backup 11) restored to `[(1, 10), (2, 11)]`, where
`[(1, 10), (2, 30)]` is required.

The fix is a manifest — one row per SUCCESSFUL forward move, written in the same
transaction as the move — and a restore that compare-and-swaps on
`event_id = target_event_id`.

## why this cannot be a unit test

`tests/test_repair_4586_stranded_voided_event_markets.py` asserts the clause is
in the SQL text. That is not the claim. The claim is that the three-row
population comes out RIGHT, and the parts that decide it are the server's:

1. **`ON CONFLICT (market_id) DO UPDATE`** on the manifest — a real unique
   constraint, and the "repaired, restored, repaired again" case depends on the
   later row replacing the earlier one rather than being dropped.
2. **The join in `_PLAN_SQL` and the CAS in `_RESTORE_SQL` agreeing about which
   rows exist.** A market in the backup but NOT in the manifest must be
   invisible; a market in the manifest but moved off its target must be visible
   in the plan and declined by the write. Those are two different mechanisms
   producing the same outcome, and only an executing planner settles both.
3. **`flush_receipts` appending a durable `market_link_changes` row.** The old
   restore wrote no receipt at all and its docstring claimed a later matcher
   pass would add one — false under gotcha #15, since an already-linked market
   is never time-window re-matched. "Exactly one reverse receipt" is a row count
   in a real table.

The three markets are the three outcomes, and each one fails differently:

| market | state after the repair | manifest | must end on | why |
|---|---|---|---|---|
| A | moved old -> target | yes | **old** | the ordinary undo |
| B | forward CAS declined, matcher moved it old -> third | **no** | **third** | the reported defect |
| C | moved old -> target, matcher then moved it to third | yes | **third** | the CAS clause |

Run against the old predicate, B comes back as `old` — that is the block.

There is no local PostgreSQL in the agent sandbox, so CI is the environment that
runs this; the `search-recall` job provides the container and its skip-detection
step is what stops a skipped gate reading as a passing one.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #4586 restore-CAS contract "
        "(CI job `search-recall` provides one)"
    ),
)

_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path — they are not a package."""
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_4586_stranded_voided_event_markets")
restore = _load("restore_4586_stranded_voided_event_markets")

#: The three events. `PHANTOM` is the voided, id-less row the markets were
#: stranded on; `TARGET` is the real fixture the repair moves them to; `THIRD`
#: is where the live matcher independently puts B and C.
PHANTOM, TARGET, THIRD = 900_001, 900_002, 900_003

#: `A` restores, `B` and `C` must not. Ids are explicit so the assertions can
#: name them rather than depend on insertion order.
MKT_A, MKT_B, MKT_C = 800_001, 800_002, 800_003


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # 🔴 BEFORE `drop_all`, NOT AFTER, and the real server is the only thing
        # that can tell you so. `bak_create` is
        # `CREATE TABLE ... (LIKE futures_markets INCLUDING DEFAULTS)`, and
        # INCLUDING DEFAULTS copies `id`'s `nextval('futures_markets_id_seq')`
        # — so the backup table holds a dependency on a sequence OWNED BY
        # `futures_markets`, and dropping that table raises
        # `DependentObjectsStillExistError`. Neither table is in `Base.metadata`,
        # so `drop_all` never removes them itself and the SECOND test in this
        # file inherits the first one's leftovers.
        #
        # Measured, first CI execution of this file: test 1 passed and tests
        # 2-5 all ERRORed at setup with "cannot drop table futures_markets
        # because other objects depend on it / default value for column id of
        # table bak_4586_futures_markets depends on sequence
        # futures_markets_id_seq". No sqlite replay can reproduce it.
        for tbl in (repair.BAK_TABLE, repair.MANIFEST_TABLE):
            await conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


async def _seed(conn) -> None:
    """The three events, the three markets, the backup, and the manifest.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status` and
    `sports.active` are NOT NULL carrying a **client-side `default=`**, applied
    by the ORM and invisible to a raw INSERT — omitting one raises
    `NotNullViolation` rather than silently taking the default.
    `tests/test_pg_gate_seed_completeness.py` parses these INSERTs against the
    live ORM metadata; this file is registered in its `COVERED` tuple.
    """
    await conn.execute(
        text(
            "INSERT INTO sports (id, key, name, active) VALUES "
            "(1, 'americanfootball_nfl', 'NFL', true)"
        )
    )
    # The phantom is `voided` and id-less, which is what stranded the markets;
    # the other two are ordinary scheduled fixtures.
    for eid, status, external in (
        (PHANTOM, "voided", None),
        (TARGET, "scheduled", "espn-target"),
        (THIRD, "scheduled", "espn-third"),
    ):
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, "
                "away_team_name, commence_time, status, external_id) "
                "VALUES (:id, 1, 'Seahawks', 'Patriots', :ct, :st, :x)"
            ),
            {
                "id": eid,
                "ct": datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc),
                "st": status,
                "x": external,
            },
        )

    # PRE-repair state: all three stranded on the voided phantom. The sequence
    # below then plays the repair and the matcher forward in the real order,
    # rather than asserting a hand-built "after" — a seed that states the
    # outcome cannot show that the outcome is reachable.
    for mid in (MKT_A, MKT_B, MKT_C):
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, mutually_exclusive, status, event_id) "
                "VALUES (:id, 'polymarket', :x, :n, 'game', true, 'open', :e)"
            ),
            {"id": mid, "x": f"pm-4586-{mid}", "n": f"market {mid}", "e": PHANTOM},
        )

    # 1. `--backup` copies EVERY in-scope row, B included. Through the repair's
    #    own statement, so the backup this gate reasons about is the backup the
    #    script actually takes.
    await conn.execute(text(repair.SQL["bak_create"]))
    await conn.execute(text(repair.SQL["bak_index"]))
    await conn.execute(
        text(repair.SQL["bak_copy"]), {"ids": [MKT_A, MKT_B, MKT_C]}
    )
    await conn.execute(text(repair.SQL["man_create"]))

    # 2. The live matcher relinks B while the repair is between plan and write.
    await conn.execute(
        text("UPDATE futures_markets SET event_id = :t WHERE id = :m"),
        {"t": THIRD, "m": MKT_B},
    )

    # 3. `--apply`, through the repair's own compare-and-swap and its own
    #    manifest statement. B's CAS finds `event_id != PHANTOM` and declines,
    #    so B gets no manifest row — which is the entire fix.
    for mid in (MKT_A, MKT_B, MKT_C):
        res = await conn.execute(
            text(repair.SQL["repoint"]),
            {"mid": mid, "old": PHANTOM, "new": TARGET},
        )
        if (res.rowcount or 0) == 0:
            continue
        await conn.execute(
            text(repair.SQL["man_record"]),
            {"mid": mid, "old": PHANTOM, "new": TARGET,
             "now": datetime.now(timezone.utc)},
        )

    # 4. ...and afterwards the matcher moves C off the target too.
    await conn.execute(
        text("UPDATE futures_markets SET event_id = :t WHERE id = :m"),
        {"t": THIRD, "m": MKT_C},
    )


async def _links(conn) -> dict[int, int]:
    rows = (
        await conn.execute(
            text("SELECT id, event_id FROM futures_markets ORDER BY id")
        )
    ).all()
    return {r.id: r.event_id for r in rows}


async def _run_restore(engine, monkeypatch, *, apply: bool) -> None:
    """Drive the REAL `restore.run` against this engine.

    Not a re-implementation of the predicate: a test that re-spells the SQL
    grades its own copy, and the copy is the one thing that cannot be wrong.
    """
    import contextlib

    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.tasks.base as base

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _sess():
        async with maker() as s:
            yield s

    monkeypatch.setattr(base, "get_task_session", _sess)
    await restore.run(apply)


@needs_postgres
async def test_restore_reverts_only_rows_still_on_the_repair_target_and_receipts_only_successes(
    pg_engine, monkeypatch
):
    """CERT-2439's required test, in one pass over the three-row population."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
        before = await _links(conn)

    assert before == {MKT_A: TARGET, MKT_B: THIRD, MKT_C: THIRD}, before

    await _run_restore(pg_engine, monkeypatch, apply=True)

    async with pg_engine.begin() as conn:
        after = await _links(conn)
        # `new_event_id`, NOT `linked_event_id`: `link_change_row` maps the
        # receipt's `linked_event_id` onto the history table's `new_event_id`,
        # and the two names are one rename apart in a file nobody re-reads.
        changes = (
            await conn.execute(
                text(
                    "SELECT market_id, previous_event_id, new_event_id, "
                    "actor, phase, outcome "
                    "FROM market_link_changes ORDER BY market_id"
                )
            )
        ).all()

    assert after[MKT_A] == PHANTOM, (
        "the market this repair moved was not put back — the undo does not undo"
    )
    assert after[MKT_B] == THIRD, (
        "THE REPORTED DEFECT: a market the forward CAS SKIPPED was reverted by "
        "the undo, destroying a newer matcher decision. It is in the backup and "
        "must not be in the manifest."
    )
    assert after[MKT_C] == THIRD, (
        "a market that moved off its repair target after the repair was "
        "reverted anyway — the restore's compare-and-swap did not hold"
    )

    assert len(changes) == 1, (
        f"expected exactly one reverse receipt, got {len(changes)}: {changes}"
    )
    (row,) = changes
    assert row.market_id == MKT_A
    assert row.previous_event_id == TARGET, (
        "the reverse receipt does not name the target it moved back FROM"
    )
    assert row.new_event_id == PHANTOM
    assert row.actor == "admin_repair"
    assert row.phase == "admin_repair"
    # `link_change_row` returns None for an outcome outside `_STATEFUL_OUTCOMES`,
    # so a receipt built any other way would silently append nothing and the
    # count above would read 0 for a reason that has nothing to do with the CAS.
    assert row.outcome == "superseded_by_twin_merge"


@needs_postgres
async def test_the_old_difference_predicate_would_fail_this_population(pg_engine):
    """THE CONTROL. Without it the test above could be green on a no-op.

    Every assertion in the required test is also satisfied by a restore that
    does NOTHING AT ALL except move A — and "does nothing" is indistinguishable
    from "declined correctly" unless something shows the population really can
    produce the wrong answer. So the blocked predicate is executed verbatim
    against the same seed and required to get B wrong.

    Note this is the ONLY place the old SQL survives; it is here as a specimen,
    and if the current restore ever starts agreeing with it, the CAS is gone.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        await conn.execute(
            text(
                f"UPDATE futures_markets f "
                f"   SET event_id = b.event_id "
                f"  FROM {repair.BAK_TABLE} b "
                f" WHERE b.id = f.id "
                f"   AND f.event_id IS DISTINCT FROM b.event_id"
            )
        )
        after = await _links(conn)

    assert after[MKT_B] == PHANTOM, (
        "the blocked predicate no longer reproduces the defect, so the required "
        "test above is no longer discriminating — re-derive both"
    )
    assert after[MKT_C] == PHANTOM


@needs_postgres
async def test_a_dry_run_moves_nothing_and_writes_no_receipt(pg_engine, monkeypatch):
    """The plan must be readable without being destructive.

    D51's rehearsal step is the whole reason an unattended repair is allowed.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        before = await _links(conn)

    await _run_restore(pg_engine, monkeypatch, apply=False)

    async with pg_engine.begin() as conn:
        assert await _links(conn) == before
        n = (
            await conn.execute(text("SELECT count(*) FROM market_link_changes"))
        ).scalar_one()
    assert n == 0


@needs_postgres
async def test_the_undo_is_idempotent(pg_engine, monkeypatch):
    """Run twice, and the second run restores nothing and receipts nothing.

    The first run leaves A on the phantom, which is no longer its manifest
    target, so the CAS declines on the second pass by the same clause that
    protects C. A second receipt here would mean the audit trail records a move
    that did not happen.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    await _run_restore(pg_engine, monkeypatch, apply=True)
    async with pg_engine.begin() as conn:
        once = await _links(conn)

    await _run_restore(pg_engine, monkeypatch, apply=True)
    async with pg_engine.begin() as conn:
        twice = await _links(conn)
        n = (
            await conn.execute(text("SELECT count(*) FROM market_link_changes"))
        ).scalar_one()

    assert once == twice, once
    assert n == 1, f"the second run wrote another receipt: {n}"


@needs_postgres
async def test_a_repaired_then_restored_then_repaired_market_uses_the_LATEST_target(
    pg_engine, monkeypatch
):
    """`ON CONFLICT DO UPDATE`, and why `DO NOTHING` is the same bug one level down.

    A market can legitimately be moved twice. If the manifest kept the FIRST
    target, the restore would compare-and-swap against a link two moves stale:
    it would decline forever, and the D51 undo would silently stop covering the
    row while still reporting a clean plan.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        # the repair runs again and puts A somewhere new
        await conn.execute(
            text("UPDATE futures_markets SET event_id = :t WHERE id = :m"),
            {"t": THIRD, "m": MKT_A},
        )
        await conn.execute(
            text(repair.SQL["man_record"]),
            {"mid": MKT_A, "old": TARGET, "new": THIRD,
             "now": datetime.now(timezone.utc)},
        )
        rows = (
            await conn.execute(
                text(
                    f"SELECT old_event_id, target_event_id FROM "
                    f"{repair.MANIFEST_TABLE} WHERE market_id = :m"
                ),
                {"m": MKT_A},
            )
        ).all()

    assert len(rows) == 1, "the manifest grew a second row for one market"
    assert (rows[0].old_event_id, rows[0].target_event_id) == (TARGET, THIRD)

    await _run_restore(pg_engine, monkeypatch, apply=True)

    async with pg_engine.begin() as conn:
        after = await _links(conn)
    assert after[MKT_A] == TARGET, (
        "the undo did not follow the latest move — the manifest kept a stale "
        "target and the compare-and-swap declined forever"
    )
