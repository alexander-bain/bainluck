"""The status task lets go of a row it has just promoted. #10090, real Postgres.

``transition_event_statuses`` used to hold every row its scheduled → live arm
promoted until the WHOLE pass committed — through the staleness, resume and
repair arms and their two ``LAST_POST_COMMENCE_SNAPSHOT_SQL`` reads. A blend
write landing on a game that had just gone live queued behind that lock: in
production (v5774, event 15331682) the stamp statement was cancelled five times
at its 500 ms ``lock_timeout`` while a 13 s pass ran. The pass now commits the
completed promotion before those reads, and drops the rows it loaded, so every
later arm reads what is in the table rather than what it saw before the commit.

Each case seeds one scheduled game whose reported start has passed, runs the
real ``_transition_event_statuses_impl``, and acts from inside the pass at the
suspended arm's entry, which is after the staleness arm's history read:

* THE SHIP: a concurrent writer (500 ms ``lock_timeout``, as the blend stamp
  runs) updates the promoted row. RED before: the pass still holds the row.
* THE FRESH READ: that writer leaves the row the bogus-final shape the repair
  arm exists for (``completed`` 0-0, no ``completed_at``). The repair arm, later
  in the same pass, must read and repair it. RED with a commit and no expunge:
  the identity map hands the arm the pre-commit copy (``live``, no score), the
  arm's writes match that copy, nothing is flushed, and the counter claims a
  repair the table never received.
* THE FAILURE BOUNDARY, pinned because it is a choice: a later arm failing no
  longer undoes a promotion that had completed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

#: The #7617 step's disposable database, the same one #8755 and #9588 reuse.
#: This file drops and creates only the tables it names.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres status-task "
        "row-release contract (CI job `search-recall` provisions a disposable one)"
    ),
)

#: A key the concurrent writer adds, as a venue's blend stamp would.
WRITER_SOURCE = {"kalshi": {"home_win_prob": 0.66}}
WRITER_SOURCE_JSON = json.dumps(WRITER_SOURCE)


@pytest.fixture
async def seeded():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, Sport
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "event_provider_anchors",
            "odds_snapshots",
            "win_prob_snapshots",
            "futures_markets",
            "futures_outcomes",
        )
    ]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        nba = Sport(key="basketball_nba", name="NBA")
        session.add(nba)
        await session.flush()
        game = Event(
            sport_id=nba.id,
            home_team_name="Boston Celtics",
            away_team_name="New York Knicks",
            commence_time=datetime.now(timezone.utc) - timedelta(minutes=10),
            commence_time_source="espn",
            espn_id="401999001",
            status="scheduled",
            win_probability_sources={"espn": {"home_win_prob": 0.617}},
        )
        session.add(game)
        await session.commit()
        event_id = game.id

    yield engine, maker, event_id

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


async def _run_pass(maker, during_later_arms):
    """Run the real pass; ``during_later_arms`` runs at the suspended arm's entry."""
    import contextlib
    from unittest.mock import patch

    import app.tasks.espn_sync as espn_sync

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    original = espn_sync._return_held_suspended_rows

    async def _hooked(session, suspended_events, now, stats):
        await during_later_arms()
        return await original(session, suspended_events, now, stats)

    with patch("app.tasks.base.get_task_session", _session), patch.object(
        espn_sync, "_return_held_suspended_rows", _hooked
    ):
        return await espn_sync._transition_event_statuses_impl()


async def _concurrent_write(engine, event_id, values_sql) -> str:
    """One UPDATE on its own connection under the blend stamp's lock budget."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await conn.execute(
                text(f"UPDATE events SET {values_sql} WHERE id = :id"),
                {"id": event_id, "src": WRITER_SOURCE_JSON},
            )
        return "written"
    except DBAPIError as exc:
        if "lock timeout" in str(exc) or "LockNotAvailable" in repr(exc):
            return "lock_timeout"
        raise


async def _row(maker, event_id):
    from sqlalchemy import select

    from app.models.models import Event

    async with maker() as session:
        return (
            await session.execute(
                select(
                    Event.status,
                    Event.home_score,
                    Event.away_score,
                    Event.win_probability_sources,
                ).where(Event.id == event_id)
            )
        ).one()


@needs_postgres
async def test_a_blend_write_reaches_a_just_promoted_row_during_the_later_arms(seeded):
    engine, maker, event_id = seeded
    outcome = {}

    async def _blend_write():
        outcome["write"] = await _concurrent_write(
            engine,
            event_id,
            "win_probability_sources = "
            "COALESCE(win_probability_sources, '{}'::jsonb) || CAST(:src AS jsonb)",
        )

    stats = await _run_pass(maker, _blend_write)

    assert stats["scheduled_to_live"] == 1
    assert outcome["write"] == "written", (
        "the pass still held the row it promoted while its later arms ran, so a "
        "blend stamp under a 500 ms lock budget was refused"
    )
    row = await _row(maker, event_id)
    assert row.status == "live"
    assert row.win_probability_sources["kalshi"] == WRITER_SOURCE["kalshi"]
    assert row.win_probability_sources["espn"] == {"home_win_prob": 0.617}


@needs_postgres
async def test_a_later_arm_reads_the_row_as_committed_not_as_first_loaded(seeded):
    engine, maker, event_id = seeded
    outcome = {}

    async def _bogus_final():
        outcome["write"] = await _concurrent_write(
            engine,
            event_id,
            "status = 'completed', home_score = 0, away_score = 0, "
            "completed_at = NULL, win_probability_sources = "
            "COALESCE(win_probability_sources, '{}'::jsonb) || CAST(:src AS jsonb)",
        )

    stats = await _run_pass(maker, _bogus_final)

    assert outcome["write"] == "written"
    row = await _row(maker, event_id)
    assert stats["repaired_bogus_completed"] == 1
    assert (row.status, row.home_score, row.away_score) == ("live", None, None), (
        "the repair arm counted a repair the table never received: it was handed "
        "the pre-commit copy of the row, so its writes changed nothing"
    )
    assert row.win_probability_sources["kalshi"] == WRITER_SOURCE["kalshi"]


@needs_postgres
async def test_a_later_arm_failing_keeps_the_completed_promotion(seeded):
    _engine, maker, event_id = seeded

    async def _fail():
        raise RuntimeError("a later arm failed")

    with pytest.raises(RuntimeError, match="a later arm failed"):
        await _run_pass(maker, _fail)

    row = await _row(maker, event_id)
    assert row.status == "live"


@needs_postgres
async def test_the_control_a_pass_with_nothing_concurrent_promotes_once(seeded):
    _engine, maker, event_id = seeded

    async def _nothing():
        return None

    stats = await _run_pass(maker, _nothing)

    assert stats["scheduled_to_live"] == 1
    assert stats["repaired_bogus_completed"] == 0
    row = await _row(maker, event_id)
    assert (row.status, row.home_score, row.away_score) == ("live", None, None)
    assert row.win_probability_sources == {"espn": {"home_win_prob": 0.617}}
