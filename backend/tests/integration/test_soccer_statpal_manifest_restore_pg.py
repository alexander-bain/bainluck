"""Soccer's first stamp: backup -> new row -> REAL apply -> restore, on real Postgres.

## the defect this exists for

CERT-2207 BLOCKed `scripts/soccer_statpal_stamp_3366.py` because its undo was not
exact. `cmd_apply` accepts a backup for `BACKUP_MAX_AGE` (45 minutes) and then
lets the live stamper choose its own candidates. Normal ingestion creates soccer
rows the whole time, so the apply can stamp a row the backup never saw. The
restore then derived ownership from the pre-image — "empty at backup, populated
now" — which classified that row's column as `outside_backup` and left it
populated, while its anchor, equally absent from the pre-image, was classified
deletable.

    events.statpal_fixture_id = '777777'     <- kept
    event_provider_anchors     'soccer:777777' <- deleted

A populated column with no anchor: the exact orphan `_write_link` writes both
halves to avoid, produced by the undo that exists to prevent it.

The repair (`SOCCER-3366-RESTORE-USES-EXACT-APPLY-MANIFEST`) makes the writer
record what it wrote — `StampRun.committed_writes`, plus `apply_run_id` in each
anchor's `claim_context`, written in the same per-row transaction — and has the
restore replay those exact pairs under a CAS.

CERT-2211 then found the half that repair missed. `record_anchor` writes
`claim_context` on the INSERT and never on the conflict path, so a column write
against an anchor that was ALREADY on file got no `apply_run_id` at all — its
only record was `StampRun.committed_writes`, in memory until the whole pass
banks. Lose the process before `_bank` and the committed write was un-undoable:
the restore planned zero changes and reported success. The follow-on repair
(`SOCCER-3366-CONFIRMED-ANCHOR-WRITE-HAS-DURABLE-MANIFEST`) attributes that write
on the incumbent under `column_write_run_id`, in the same transaction, and the
undo owes such a row exactly one half — clear the column, leave the anchor.

## why this gate needs a real server

The pure planner is unit-tested in
`tests/test_soccer_statpal_stamp_d51_rails_3366.py`. What only Postgres decides:

1. **`claim_context->>'apply_run_id' = :run_id` actually selects.** The durable
   half of the attribution is a JSONB path read against a column
   `record_anchor` writes through `CAST(:claim_context AS jsonb)`. A dict in a
   mock compares equal to itself no matter how it would have serialised; only
   the server says whether the key round-trips and whether the `->>` finds it.
2. **`record_anchor` writes `claim_context` on INSERT and never on conflict.**
   That asymmetry is the whole reason the run id can be trusted as "this
   invocation inserted this row" — and it is a property of `ON CONFLICT DO
   NOTHING` against `uq_anchor_source_id`, not of the Python around it.
3. **The CAS clears nothing when the value moved.** `UPDATE ... WHERE
   statpal_fixture_id = :written` returning rowcount 0 for a row another writer
   changed is the server's answer; a mock returns whatever rowcount it is told.
4. **`= ANY(:ids)` binds a Python list.** `_state_now` reads by id rather than
   re-reading the window; that bind form is asyncpg/Postgres-specific and a
   sqlite spelling of it would pass a statement Postgres refuses.
5. **The apply commits per row (gotcha #13).** The manifest is appended after
   each commit, so "what the manifest says" versus "what is on disk" is only a
   real question against a real transaction boundary.
6. **`NOT (claim_context ? 'k')` is NULL, not true, on a NULL column.** The
   attribution's "first writer owns it" guard would then match no row and
   silently attribute nothing while the column write still committed. Python
   has no equivalent of that trap — `'k' not in {}` is simply true — so a mock
   cannot fail this the way a server can.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs. The
`search-recall` job provides the container and its "Verify the gate is actually
armed" step is what stops a skipped gate reading as a passing one.

## the corpus

Four soccer rows, each paired with the defect it catches:

* **`backed_up`** — present when the backup was taken. The ordinary case, here
  so a repair that fixes the gap by breaking the normal path cannot pass.
* **`born_in_the_gap`** — INSERTed after the backup and before the apply. This
  is the CERT-2207 row. Both halves must come back.
* **`foreign`** — present at backup, empty then, and populated by a DIFFERENT
  writer (no `apply_run_id`) between apply and restore. Both halves must
  survive. This is the sibling case the BLOCK required, and it is what stops a
  repair that simply deletes every soccer StatPal anchor it can see.
* **`confirmed_row`** — CERT-2211. A null column whose anchor is ALREADY on
  file, so `record_anchor` conflicts and our claim context is discarded: the
  committed column write gets no `apply_run_id`, and its only record was the
  in-memory manifest. Lose the process before `_bank` and the restore planned
  zero changes and left the write standing. Now attributed on the incumbent
  under `column_write_run_id`, so the undo owes exactly one half — clear the
  column, LEAVE the anchor.

Rows 2 and 4 are the two halves of the same lesson, from opposite directions:
the undo must reach a write the backup never saw, and must not reach a
correspondence this pass did not create. Each has a PREMISE test asserting the
apply really does write the row, so no undo assertion can pass vacuously.
"""

import importlib.util
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres CERT-2207 "
        "manifest-restore round trip (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

#: ONE real-clock read, offsets only — deliberately not a pinned date (gotcha
#: #44). `_latest_backup` reads the banked backup through `read_snapshot`, whose
#: `DEFAULT_MAX_AGE_S` is 168h against the REAL clock, so a fixed 2026-09-08
#: would pass this week and then start failing in seven days when `cmd_apply`
#: correctly refuses a backup it now considers stale. A gate that expires goes
#: red for a reason that has nothing to do with the code it guards.
_NOW = datetime.now(UTC)

#: The apply runs now; the backup was taken 10 minutes ago, which is inside
#: `BACKUP_MAX_AGE` — the point is that a VALID backup is still not a complete
#: one.
APPLY_AT = _NOW
BACKUP_AT = _NOW - timedelta(minutes=10)

#: A day out. Candidate selection is driven by the FIXTURE start times
#: (`window_start = min(starts) - CANDIDATE_SLACK`), and the seeded rows carry
#: exactly this instant, so the window holds them whatever the clock says.
KICKOFF = _NOW + timedelta(days=1)

SPORT_ID = 1
BACKED_UP = 301
BORN_IN_THE_GAP = 302
FOREIGN = 303
#: CERT-2211: a null column whose anchor is ALREADY on file, so `record_anchor`
#: takes the conflict path and the column write gets no `apply_run_id`.
CONFIRMED_ROW = 304

#: `fallback_id_3` is what soccer anchors on — NOT `fixture_id` (#3800).
FIX_BACKED_UP = "9000001"
FIX_BORN = "9000002"
FIX_FOREIGN = "9000003"
FIX_CONFIRMED = "9000004"


def _load_script():
    path = (
        Path(__file__).resolve().parents[2] / "scripts" / "soccer_statpal_stamp_3366.py"
    )
    spec = importlib.util.spec_from_file_location("soccer_statpal_stamp_3366_pg", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rails = _load_script()


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )


@pytest.fixture
def pg_schema():
    """Real Postgres with the real schema, dropped and rebuilt."""
    from sqlalchemy import create_engine, text

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_engine(_sync_url(DB_URL))
    with engine.begin() as c:
        Base.metadata.drop_all(c)
        Base.metadata.create_all(c)
        c.execute(
            text(
                "INSERT INTO sports (id, key, name, active) "
                "VALUES (:id, 'soccer_epl', 'EPL', true)"
            ),
            {"id": SPORT_ID},
        )
    engine.dispose()
    yield


@pytest.fixture
def session_factory(pg_schema, monkeypatch):
    """Point every `get_task_session` caller at the test database.

    The script, the stamper and `publish_snapshot_standalone` all import it
    inside their functions, so one patch covers the backup, the apply write and
    the restore — which is what makes this a round trip rather than three
    separately-stubbed halves.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _get_task_session():
        async with maker() as session:
            yield session

    import app.tasks.base as task_base

    monkeypatch.setattr(task_base, "get_task_session", _get_task_session)
    yield maker


async def _seed_event(maker, event_id, home, away, *, fixture_id=None):
    from sqlalchemy import text

    async with maker() as s:
        await s.execute(
            text(
                "INSERT INTO events "
                "(id, sport_id, home_team_name, away_team_name, commence_time, "
                "status, statpal_fixture_id) "
                "VALUES (:id, :sport, :home, :away, :when, 'scheduled', :fix)"
            ),
            {
                "id": event_id,
                "sport": SPORT_ID,
                "home": home,
                "away": away,
                "when": KICKOFF,
                "fix": fixture_id,
            },
        )
        await s.commit()


def _stub_statpal(monkeypatch, fixtures):
    """Serve the whole corpus off board offset 1 and nothing anywhere else."""
    import app.tasks.stamp_v1_statpal_fixtures as task

    async def _schedule(sport, day_offset=None):
        return list(fixtures) if day_offset == 1 else []

    async def _live(sport):
        return []

    async def _close():
        return None

    monkeypatch.setattr(
        task,
        "get_statpal_service",
        lambda: SimpleNamespace(
            get_schedule_fixtures=_schedule,
            get_live_fixtures=_live,
            close=_close,
        ),
    )


def _fixture(fallback, home, away):
    from app.services.statpal_api import StatPalFixture

    return StatPalFixture(
        # `fixture_id` is the board's own id; soccer anchors on `fallback_id_3`.
        fixture_id=f"board-{fallback}",
        fallback_id_3=fallback,
        home_team=home,
        away_team=away,
        start_time=KICKOFF,
    )


async def _columns(maker):
    from sqlalchemy import text

    async with maker() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id, statpal_fixture_id FROM events "
                    "WHERE statpal_fixture_id IS NOT NULL ORDER BY id"
                )
            )
        ).fetchall()
    return {r[0]: r[1] for r in rows}


async def _anchors(maker):
    from sqlalchemy import text

    async with maker() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT event_id, source_id FROM event_provider_anchors "
                    "WHERE source = 'statpal' AND source_id LIKE 'soccer:%' "
                    "ORDER BY event_id"
                )
            )
        ).fetchall()
    return {r[0]: r[1] for r in rows}


async def _run_the_round_trip(maker, monkeypatch, *, foreign_writer=False):
    """backup -> new row appears -> real apply -> (foreign write) -> restore."""
    from sqlalchemy import text

    # 1. The row the backup will see.
    await _seed_event(maker, BACKED_UP, "Wrexham", "Cardiff City")
    if foreign_writer:
        await _seed_event(maker, FOREIGN, "Leeds", "Burnley")

    # 2. The backup. Real: it reads the window and banks a durable snapshot.
    assert await rails.cmd_backup(BACKUP_AT) == 0

    # 3. A row created AFTER the backup — the CERT-2207 population.
    await _seed_event(maker, BORN_IN_THE_GAP, "Fulham", "Brentford")

    # 4. The real apply write, through the real stamper.
    # `FOREIGN` is deliberately NOT served to the apply, so the apply never
    # touches it. That is the sibling case: a row the backup saw empty, which
    # somebody else fills in. Under the old derived rule — empty at backup,
    # populated now — it was indistinguishable from ours.
    _stub_statpal(
        monkeypatch,
        [
            _fixture(FIX_BACKED_UP, "Wrexham", "Cardiff City"),
            _fixture(FIX_BORN, "Fulham", "Brentford"),
        ],
    )
    assert await rails.cmd_apply(APPLY_AT) == 0

    run_id = await _latest_apply_identity(maker)

    if foreign_writer:
        # A different writer links `FOREIGN`: both halves, and no
        # `apply_run_id` anywhere in the claim context.
        async with maker() as s:
            await s.execute(
                text("UPDATE events SET statpal_fixture_id = :fix WHERE id = :id"),
                {"fix": FIX_FOREIGN, "id": FOREIGN},
            )
            await s.execute(
                text(
                    "INSERT INTO event_provider_anchors "
                    "(event_id, source, source_id, id_kind, claim_context) "
                    "VALUES (:id, 'statpal', :sid, 'game', "
                    "CAST(:ctx AS jsonb))"
                ),
                {
                    "id": FOREIGN,
                    "sid": f"soccer:{FIX_FOREIGN}",
                    "ctx": '{"written_by": "somebody_else"}',
                },
            )
            await s.commit()

    # 5. The undo.
    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0
    return run_id


async def _latest_apply_identity(maker):
    from sqlalchemy import text

    async with maker() as s:
        row = (
            await s.execute(
                text(
                    "SELECT identity FROM durable_state_snapshots "
                    "WHERE identity LIKE :p ORDER BY generated_at DESC LIMIT 1"
                ),
                {"p": f"{rails.APPLY_IDENTITY_PREFIX}%"},
            )
        ).first()
    assert row is not None, "the apply banked no receipt"
    return row[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_the_apply_stamps_a_row_the_backup_never_saw(
    session_factory, monkeypatch
):
    """The premise. Without this the undo test proves nothing.

    If the apply could not reach a row created after the backup, there would be
    no gap to mis-attribute and CERT-2207 would not exist.
    """
    maker = session_factory
    await _seed_event(maker, BACKED_UP, "Wrexham", "Cardiff City")
    assert await rails.cmd_backup(BACKUP_AT) == 0
    await _seed_event(maker, BORN_IN_THE_GAP, "Fulham", "Brentford")

    _stub_statpal(
        monkeypatch,
        [
            _fixture(FIX_BACKED_UP, "Wrexham", "Cardiff City"),
            _fixture(FIX_BORN, "Fulham", "Brentford"),
        ],
    )
    assert await rails.cmd_apply(APPLY_AT) == 0

    columns = await _columns(maker)
    assert columns == {BACKED_UP: FIX_BACKED_UP, BORN_IN_THE_GAP: FIX_BORN}, (
        "the apply did not reach the row born after the backup — the gap this "
        "gate is about does not exist and every assertion below is vacuous"
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_the_undo_leaves_no_orphan_for_a_row_born_in_the_backup_gap(
    session_factory, monkeypatch
):
    """CERT-2207, stated as the invariant rather than as two counts."""
    maker = session_factory
    await _run_the_round_trip(maker, monkeypatch)

    columns = await _columns(maker)
    anchors = await _anchors(maker)

    assert columns == {}, (
        f"a column survived the undo: {columns}. For {BORN_IN_THE_GAP} this is "
        "the CERT-2207 orphan — populated column, deleted anchor."
    )
    assert anchors == {}, f"an anchor survived the undo: {anchors}"


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_the_anchors_carry_the_run_id_that_makes_the_undo_durable(
    session_factory, monkeypatch
):
    """The attribution is IN the table, not only in the banked receipt.

    This is what lets an apply that died before banking still be undone, and it
    is a JSONB round trip only the server can confirm.
    """
    from sqlalchemy import text

    maker = session_factory
    await _seed_event(maker, BACKED_UP, "Wrexham", "Cardiff City")
    assert await rails.cmd_backup(BACKUP_AT) == 0
    _stub_statpal(monkeypatch, [_fixture(FIX_BACKED_UP, "Wrexham", "Cardiff City")])
    assert await rails.cmd_apply(APPLY_AT) == 0
    run_id = await _latest_apply_identity(maker)

    async with maker() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT event_id FROM event_provider_anchors "
                    "WHERE source = 'statpal' AND source_id LIKE 'soccer:%' "
                    "AND claim_context->>'apply_run_id' = :run_id"
                ),
                {"run_id": run_id},
            )
        ).fetchall()

    assert [r[0] for r in rows] == [BACKED_UP], (
        "the run id did not round-trip through the anchor's claim_context, so "
        "an apply whose receipt is lost could never be undone"
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_an_apply_whose_receipt_is_gone_is_still_fully_undone(
    session_factory, monkeypatch
):
    """Delete the banked manifest and restore anyway, from the anchors alone."""
    from sqlalchemy import text

    maker = session_factory
    await _seed_event(maker, BACKED_UP, "Wrexham", "Cardiff City")
    assert await rails.cmd_backup(BACKUP_AT) == 0
    _stub_statpal(monkeypatch, [_fixture(FIX_BACKED_UP, "Wrexham", "Cardiff City")])
    assert await rails.cmd_apply(APPLY_AT) == 0
    run_id = await _latest_apply_identity(maker)

    async with maker() as s:
        await s.execute(
            text("DELETE FROM durable_state_snapshots WHERE identity = :i"),
            {"i": run_id},
        )
        await s.commit()

    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0
    assert await _columns(maker) == {}
    assert await _anchors(maker) == {}


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_a_foreign_writers_column_and_anchor_both_survive_the_undo(
    session_factory, monkeypatch
):
    """The sibling case: absence from the manifest is the whole protection."""
    maker = session_factory
    await _run_the_round_trip(maker, monkeypatch, foreign_writer=True)

    columns = await _columns(maker)
    anchors = await _anchors(maker)

    assert columns == {FOREIGN: FIX_FOREIGN}, (
        "the undo cleared a column another writer set (or failed to clear its "
        f"own): {columns}"
    )
    assert anchors == {
        FOREIGN: f"soccer:{FIX_FOREIGN}"
    }, f"the undo deleted an anchor it did not write: {anchors}"


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_a_column_another_writer_moved_is_reported_not_dragged_back(
    session_factory, monkeypatch
):
    """The CAS. Ours by the manifest, but no longer holding what we wrote."""
    from sqlalchemy import text

    maker = session_factory
    await _seed_event(maker, BACKED_UP, "Wrexham", "Cardiff City")
    assert await rails.cmd_backup(BACKUP_AT) == 0
    _stub_statpal(monkeypatch, [_fixture(FIX_BACKED_UP, "Wrexham", "Cardiff City")])
    assert await rails.cmd_apply(APPLY_AT) == 0
    run_id = await _latest_apply_identity(maker)

    async with maker() as s:
        await s.execute(
            text("UPDATE events SET statpal_fixture_id = '555555' WHERE id = :id"),
            {"id": BACKED_UP},
        )
        await s.commit()

    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0

    assert await _columns(maker) == {
        BACKED_UP: "555555"
    }, "the undo overwrote a value that is now newer than the one it recorded"
    # The anchor is still unambiguously ours, so it still goes.
    assert await _anchors(maker) == {}


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_the_restore_is_idempotent(session_factory, monkeypatch):
    """Running the undo twice is a no-op, not a second round of deletes."""
    maker = session_factory
    run_id = await _run_the_round_trip(maker, monkeypatch)

    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0
    assert await _columns(maker) == {}
    assert await _anchors(maker) == {}


async def _seed_incumbent_anchor(maker, event_id, fixture_id, *, context=None):
    """An anchor already on file for this event, written by somebody else.

    This is what makes `record_anchor` return CONFIRMED: the correspondence
    exists, so the INSERT conflicts and our claim context — `apply_run_id` and
    all — is discarded. `column_was_already_set` is in the incumbent's context
    deliberately: it is a TRUE statement about the pass that wrote the anchor,
    and a false one about the pass that later fills the column. The undo must
    not read it as its own.
    """
    from sqlalchemy import text

    async with maker() as s:
        await s.execute(
            text(
                "INSERT INTO event_provider_anchors "
                "(event_id, source, source_id, id_kind, claim_context) "
                "VALUES (:id, 'statpal', :sid, 'game', CAST(:ctx AS jsonb))"
            ),
            {
                "id": event_id,
                "sid": f"soccer:{fixture_id}",
                "ctx": (
                    '{"written_by": "an_earlier_anchor_only_pass", '
                    '"column_was_already_set": true}'
                    if context is None
                    else context
                ),
            },
        )
        await s.commit()


async def _claim_context_of(maker, event_id):
    from sqlalchemy import text

    async with maker() as s:
        row = (
            await s.execute(
                text(
                    "SELECT claim_context FROM event_provider_anchors "
                    "WHERE event_id = :id AND source = 'statpal'"
                ),
                {"id": event_id},
            )
        ).first()
    return dict(row[0]) if row and row[0] else None


async def _apply_over_a_confirmed_anchor(maker, monkeypatch):
    """A column write whose anchor was already there — the CERT-2211 path."""
    await _seed_event(maker, CONFIRMED_ROW, "Fulham", "Brentford")
    await _seed_incumbent_anchor(maker, CONFIRMED_ROW, FIX_CONFIRMED)
    assert await rails.cmd_backup(BACKUP_AT) == 0
    _stub_statpal(monkeypatch, [_fixture(FIX_CONFIRMED, "Fulham", "Brentford")])
    assert await rails.cmd_apply(APPLY_AT) == 0
    return await _latest_apply_identity(maker)


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_the_apply_does_write_the_column_over_a_confirmed_anchor(
    session_factory, monkeypatch
):
    """PREMISE. If the apply never reached this row the undo assertions below
    would pass vacuously, exactly as they would have for the backup gap."""
    maker = session_factory
    await _apply_over_a_confirmed_anchor(maker, monkeypatch)

    assert await _columns(maker) == {
        CONFIRMED_ROW: FIX_CONFIRMED
    }, "the apply did not stamp the row, so the CERT-2211 case is untested"
    assert await _anchors(maker) == {CONFIRMED_ROW: f"soccer:{FIX_CONFIRMED}"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_a_confirmed_path_column_write_is_attributed_in_the_database(
    session_factory, monkeypatch
):
    """CERT-2211's mechanism, as a JSONB round trip only the server can confirm.

    `apply_run_id` is absent because `record_anchor` never writes claim_context
    on the conflict path — that absence IS the defect. `column_write_run_id` is
    the durable record that replaces it, and the incumbent's own keys survive it.
    """
    maker = session_factory
    run_id = await _apply_over_a_confirmed_anchor(maker, monkeypatch)

    context = await _claim_context_of(maker, CONFIRMED_ROW)
    assert context is not None
    assert context.get("column_write_run_id") == run_id, (
        "the committed column write left no durable trace: lose the process "
        "before `_bank` and the restore plans nothing and leaves the write"
    )
    assert (
        "apply_run_id" not in context
    ), "the conflict path wrote a claim context it is documented never to write"
    assert (
        context.get("written_by") == "an_earlier_anchor_only_pass"
    ), "the attribution overwrote the incumbent's context instead of merging"


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_a_confirmed_path_write_lost_before_banking_is_still_undone(
    session_factory, monkeypatch
):
    """THE BLOCK'S CASE, end to end on real Postgres.

    Apply -> the receipt never lands -> restore. The column has to come back to
    NULL and the anchor has to stay: this pass wrote one half, so the undo owes
    exactly one half. Before the repair the manifest was in memory only, the
    restore planned zero changes, and the write stood forever.
    """
    from sqlalchemy import text

    maker = session_factory
    run_id = await _apply_over_a_confirmed_anchor(maker, monkeypatch)

    # The process loss: the write is committed, the receipt never banked.
    async with maker() as s:
        await s.execute(
            text("DELETE FROM durable_state_snapshots WHERE identity = :i"),
            {"i": run_id},
        )
        await s.commit()

    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0

    assert (
        await _columns(maker) == {}
    ), "the column write survived its own undo — CERT-2211 unrepaired"
    assert await _anchors(maker) == {
        CONFIRMED_ROW: f"soccer:{FIX_CONFIRMED}"
    }, "the undo deleted a correspondence this apply only confirmed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_the_confirmed_path_undo_is_idempotent(session_factory, monkeypatch):
    """A second undo reports rather than writing, and still spares the anchor."""
    maker = session_factory
    run_id = await _apply_over_a_confirmed_anchor(maker, monkeypatch)

    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0
    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0
    assert await _columns(maker) == {}
    assert await _anchors(maker) == {CONFIRMED_ROW: f"soccer:{FIX_CONFIRMED}"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("pg_schema")
async def test_an_incumbent_with_no_claim_context_is_still_attributed(
    session_factory, monkeypatch
):
    """`claim_context` is nullable, and `NOT (claim_context ? 'k')` is NULL —
    not true — when it is NULL, so an un-COALESCEd guard would match no row and
    attribute nothing. The write would still commit. Only the server settles
    this: in Python the same expression is a plain `not in`.
    """
    maker = session_factory
    await _seed_event(maker, CONFIRMED_ROW, "Fulham", "Brentford")
    await _seed_incumbent_anchor(maker, CONFIRMED_ROW, FIX_CONFIRMED, context=None)

    from sqlalchemy import text

    async with maker() as s:
        await s.execute(
            text(
                "UPDATE event_provider_anchors SET claim_context = NULL "
                "WHERE event_id = :id"
            ),
            {"id": CONFIRMED_ROW},
        )
        await s.commit()

    assert await rails.cmd_backup(BACKUP_AT) == 0
    _stub_statpal(monkeypatch, [_fixture(FIX_CONFIRMED, "Fulham", "Brentford")])
    assert await rails.cmd_apply(APPLY_AT) == 0
    run_id = await _latest_apply_identity(maker)

    context = await _claim_context_of(maker, CONFIRMED_ROW)
    assert context is not None and context.get("column_write_run_id") == run_id, (
        "a NULL claim_context swallowed the attribution — the `?` test needs "
        "COALESCE on both sides"
    )

    async with maker() as s:
        await s.execute(
            text("DELETE FROM durable_state_snapshots WHERE identity = :i"),
            {"i": run_id},
        )
        await s.commit()

    assert await rails.cmd_restore(run_id, apply=True, now=APPLY_AT) == 0
    assert await _columns(maker) == {}
    assert await _anchors(maker) == {CONFIRMED_ROW: f"soccer:{FIX_CONFIRMED}"}
