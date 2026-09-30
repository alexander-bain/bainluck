"""#9051 — the fold's revision vector orders two reads of a folded blend, on real Postgres.

## the ship

A removed source stops influencing the held headline and chart, and valid
survivor quotes and re-admissions still land.

## what these cases prove, and why each needs a server

* R1  the trigger bumps the row's revision when its bag changes, and ONLY then
      (another column, or an identical bag, leaves it alone). The trigger is
      plpgsql, so no fake can run it.
* R2  COMMIT order, not statement order: writer A updates first and holds its
      transaction; writer B's UPDATE waits on A's row lock; A commits; B's
      RETURNING reports A's revision + 1. Two clocks could order these either
      way. The revision cannot.
* R3  Codex's twin case (twin-contract/CONTRACT-REVIEW.md) through the REAL
      fold helper: the canonical removes ESPN, the twin removes Kalshi, each
      committed separately. A fold read between the two commits and one read
      after them serve different numbers, and the later vector DOMINATES the
      earlier one in every component. The scalar max removal clock this
      replaces could not tell them apart.
* R4  a nonvenue writer's frame carries the revision its own UPDATE returned,
      equal to what is now stored.
* R5  the migration's own upgrade installs exactly the column + trigger the
      model's `after_create` does, and its downgrade removes them.
* R6  (CERT-3625) a canonical row the route loaded BEFORE two removals
      committed is not folded stale beside the fresh twin: the fold reads every
      row it folds in one statement.

Runs where `SEARCH_TEST_DATABASE_URL` is set (CI `search-recall`).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #9051 fold-revision gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

CANON, TWIN = 905101, 905102
STAMP = "2026-09-27T06:00:00+00:00"


def _reading(value):
    return {"value": value, "updated_at": STAMP}


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import models as _registers_every_table  # noqa: F401
    from app.models.models import Event, Sport
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    start = datetime.now(timezone.utc) - timedelta(minutes=30)
    async with Session() as session:
        session.add(Sport(id=9051, key="soccer_epl", name="EPL"))
        await session.flush()
        session.add_all(
            [
                Event(
                    id=CANON,
                    sport_id=9051,
                    home_team_name="Arsenal",
                    away_team_name="Chelsea",
                    commence_time=start,
                    status="live",
                    win_probability_sources={
                        "polymarket": _reading(0.4),
                        "espn": _reading(0.8),
                    },
                ),
                Event(
                    id=TWIN,
                    sport_id=9051,
                    home_team_name="Arsenal",
                    away_team_name="Chelsea",
                    commence_time=start,
                    status="live",
                    event_tags=[f"provenance:duplicate-of:{CANON}"],
                    win_probability_sources={"kalshi": _reading(0.8)},
                ),
            ]
        )
        await session.commit()
    yield engine, Session
    await engine.dispose()


async def _rev(Session, event_id):
    async with Session() as session:
        return (
            await session.execute(
                text("SELECT win_probability_sources_rev FROM events WHERE id = :id"),
                {"id": event_id},
            )
        ).scalar_one()


async def _drop_source(Session, event_id, source):
    async with Session() as session:
        rev = (
            await session.execute(
                text(
                    "UPDATE events SET win_probability_sources = "
                    "win_probability_sources - :s WHERE id = :id "
                    "RETURNING win_probability_sources_rev"
                ),
                {"s": source, "id": event_id},
            )
        ).scalar_one()
        await session.commit()
        return rev


async def _fold(Session):
    from app.models.models import Event
    from app.utils.aggregation import compute_aggregate_probability
    from app.utils.proven_duplicates import (
        FoldedBlendView,
        folded_probability_sources_with_revision,
    )

    async with Session() as session:
        event = await session.get(Event, CANON)
        sources, vector = await folded_probability_sources_with_revision(
            session, event
        )
        value = compute_aggregate_probability(
            FoldedBlendView(event, sources), event.status
        )
        return value, vector, sources


def _dominates(later, earlier):
    return (
        later.keys() == earlier.keys()
        and all(later[k] >= earlier[k] for k in later)
        and any(later[k] > earlier[k] for k in later)
    )


class TestTheRevisionIsTheDatabasesCommitOrder:
    async def test_r1_only_a_changed_bag_moves_the_revision(self, pg):
        _engine, Session = pg
        assert await _rev(Session, CANON) == 0
        async with Session() as session:
            await session.execute(
                text("UPDATE events SET home_score = 1 WHERE id = :id"), {"id": CANON}
            )
            await session.execute(
                text(
                    "UPDATE events SET win_probability_sources = "
                    "win_probability_sources WHERE id = :id"
                ),
                {"id": CANON},
            )
            await session.commit()
        assert await _rev(Session, CANON) == 0, "an unchanged bag moved the revision"
        assert await _drop_source(Session, CANON, "espn") == 1
        # A writer cannot set the revision alongside a bag change.
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE events SET win_probability_sources = '{}'::jsonb, "
                    "win_probability_sources_rev = 99 WHERE id = :id"
                ),
                {"id": CANON},
            )
            await session.commit()
        assert await _rev(Session, CANON) == 2

    async def test_r2_the_second_writer_to_commit_gets_the_higher_revision(self, pg):
        _engine, Session = pg
        a = Session()
        b = Session()
        try:
            rev_a = (
                await a.execute(
                    text(
                        "UPDATE events SET win_probability_sources = "
                        "win_probability_sources - 'espn' WHERE id = :id "
                        "RETURNING win_probability_sources_rev"
                    ),
                    {"id": CANON},
                )
            ).scalar_one()

            async def _b():
                rev = (
                    await b.execute(
                        text(
                            "UPDATE events SET win_probability_sources = "
                            "win_probability_sources - 'polymarket' WHERE id = :id "
                            "RETURNING win_probability_sources_rev"
                        ),
                        {"id": CANON},
                    )
                ).scalar_one()
                await b.commit()
                return rev

            waiting = asyncio.create_task(_b())
            await asyncio.sleep(0.5)
            assert not waiting.done(), "B did not wait on A's row lock"
            await a.commit()
            rev_b = await asyncio.wait_for(waiting, timeout=10)
        finally:
            await a.close()
            await b.close()
        assert (rev_a, rev_b) == (1, 2)
        assert await _rev(Session, CANON) == 2

    async def test_r3_the_twin_removals_are_ordered_where_a_max_clock_was_not(
        self, pg
    ):
        _engine, Session = pg
        before_value, before, _ = await _fold(Session)
        assert before == {str(CANON): 0, str(TWIN): 0}
        assert before_value == pytest.approx(0.8)  # median of 0.4, 0.8, 0.8

        await _drop_source(Session, CANON, "espn")
        mid_value, mid, _ = await _fold(Session)
        assert mid == {str(CANON): 1, str(TWIN): 0}
        assert mid_value == pytest.approx(0.6)  # PM 0.4 + twin Kalshi 0.8

        await _drop_source(Session, TWIN, "kalshi")
        after_value, after, after_sources = await _fold(Session)
        assert after == {str(CANON): 1, str(TWIN): 1}
        assert set(after_sources) == {"polymarket"}
        assert after_value == pytest.approx(0.4)

        # The client's rule: the later read dominates both earlier ones.
        assert _dominates(mid, before)
        assert _dominates(after, mid)
        assert not _dominates(mid, after), "the older fold would be adopted"

    async def test_r6_a_canonical_loaded_before_a_commit_is_not_folded_stale(
        self, pg
    ):
        """CERT-3625's interleaving. The route loads the canonical at revision
        0; another session then commits the canonical's ESPN removal and the
        twin's Kalshi removal. The fold must read the canonical in the SAME
        statement as the twin: at fb9713bec4 it served the loaded bag (ESPN
        still in it) beside the fresh twin under `{canonical: 0, twin: 1}`."""
        from app.models.models import Event
        from app.utils.proven_duplicates import (
            folded_probability_sources_with_revision,
        )

        _engine, Session = pg
        async with Session() as session:
            event = await session.get(Event, CANON)
            assert event.win_probability_sources_rev == 0
            assert "espn" in event.win_probability_sources
            await _drop_source(Session, CANON, "espn")
            await _drop_source(Session, TWIN, "kalshi")
            sources, vector = await folded_probability_sources_with_revision(
                session, event
            )
        assert vector == {str(CANON): 1, str(TWIN): 1}, vector
        assert set(sources) == {"polymarket"}, sources

    async def test_r4_a_nonvenue_frame_names_the_revision_its_update_returned(
        self, pg
    ):
        from app.models.models import Event
        from app.utils.nonvenue_live_push import (
            _READY,
            write_nonvenue_probability,
        )

        _engine, Session = pg
        async with Session() as session:
            event = await session.get(Event, CANON)
            await write_nonvenue_probability(session, event, "betting", 0.55)
            await session.commit()
            frames = session.info.get(_READY, [])
        assert len(frames) == 1, frames
        stored = await _rev(Session, CANON)
        assert stored == 1
        assert frames[0]["rev"] == {str(CANON): stored}


class TestTheMigrationInstallsTheSameTrigger:
    async def test_r5_upgrade_and_downgrade(self, pg):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        engine, Session = pg
        path = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "wps_rev_trigger.py"
        )
        spec = importlib.util.spec_from_file_location("wps_rev_trigger", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        def _run(sync_conn, step):
            ctx = MigrationContext.configure(sync_conn)
            with Operations.context(ctx):
                step()

        async def _catalog():
            async with engine.connect() as conn:
                col = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM information_schema.columns "
                            "WHERE table_name = 'events' "
                            "AND column_name = 'win_probability_sources_rev'"
                        )
                    )
                ).scalar_one()
                trg = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM pg_trigger WHERE tgname = "
                            "'trg_bump_win_probability_sources_rev' AND NOT tgisinternal"
                        )
                    )
                ).scalar_one()
                return col, trg

        assert await _catalog() == (1, 1), "create_all did not install the trigger"
        async with engine.begin() as conn:
            await conn.run_sync(_run, migration.downgrade)
        assert await _catalog() == (0, 0)
        async with engine.begin() as conn:
            await conn.run_sync(_run, migration.upgrade)
        assert await _catalog() == (1, 1)
        assert await _rev(Session, CANON) == 0
        assert await _drop_source(Session, CANON, "espn") == 1
