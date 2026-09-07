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

There is no local PostgreSQL in the agent sandbox, so CI is where this runs. The
`search-recall` job provides the container and its "Verify the gate is actually
armed" step is what stops a skipped gate reading as a passing one.

## the corpus

Three soccer rows, each paired with the defect it catches:

* **`backed_up`** — present when the backup was taken. The ordinary case, here
  so a repair that fixes the gap by breaking the normal path cannot pass.
* **`born_in_the_gap`** — INSERTed after the backup and before the apply. This
  is the CERT-2207 row. Both halves must come back.
* **`foreign`** — present at backup, empty then, and populated by a DIFFERENT
  writer (no `apply_run_id`) between apply and restore. Both halves must
  survive. This is the sibling case the BLOCK required, and it is what stops a
  repair that simply deletes every soccer StatPal anchor it can see.
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

#: `fallback_id_3` is what soccer anchors on — NOT `fixture_id` (#3800).
FIX_BACKED_UP = "9000001"
FIX_BORN = "9000002"
FIX_FOREIGN = "9000003"


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
