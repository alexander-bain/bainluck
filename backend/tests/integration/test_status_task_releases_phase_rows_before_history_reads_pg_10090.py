"""The status task lets go of the rows it suspends before its history reads. #10090.

``transition_event_statuses`` (every 60 s) runs ``LAST_POST_COMMENCE_SNAPSHOT_SQL``
twice inside its suspend/resume phase: once over every long-running live game,
once over every suspended game of the last 48 h. The holder watch recorded that
read at 19.6-20.9 s on production (2026-10-28 23:43Z, 2026-10-29 00:01Z), with
the transaction already holding ``events`` rows and both venue arms' blend
writes queued behind it. Two writes in that phase could be held through it:

* the venue-settlement CAS (rung 2) — a live game whose winner market settled —
  ran before the FIRST read;
* the staleness arm's suspensions, flushed by the suspended-row SELECT, ran
  before the SECOND read.

The pass now commits before each read. Real Postgres, real
``_transition_event_statuses_impl``; a concurrent writer under the blend
stamp's 500 ms ``lock_timeout`` acts at the start of each read.

* THE SHIP, twice: the writer reaches the row each arm just wrote. RED before.
* THE FAILURE BOUNDARY, pinned because it is a choice: a failure in the second
  read no longer undoes either suspension.
* THE CONTROL: with nothing concurrent the pass makes exactly these two
  suspensions and leaves the blend untouched.

Tables are created and dropped by name in ``DELAY_CONTRACT_DATABASE_URL``, the
same disposable database the sibling ``..._releases_started_rows_pg_10090``
uses.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

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
SEEDED_SOURCES = {"espn": {"home_win_prob": 0.617}}

#: The rung-2 specimen of ``test_a_venue_settlement_ends_the_match_2591``: the
#: match market itself, settled by the venue with a competitor as winner.
SETTLED_MATCH = ("Huskies eSport vs. BIG Academy", "KXCS2GAME-26SEP211400HUSKBIGA")

#: The marker both reads carry; the hook counts them in order.
HISTORY_READ_MARKER = "AS last_snap"


@pytest.fixture
async def seeded():
    """One live game the venue has settled, one live game long past its bound."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
    from app.services.database import Base
    from app.tasks.config import SPORT_MAX_DURATIONS

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

    now = datetime.now(timezone.utc)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        esports = Sport(key="esports_cs2", name="CS2")
        nfl = Sport(key="americanfootball_nfl", name="NFL")
        session.add_all([esports, nfl])
        await session.flush()
        settled = Event(
            sport_id=esports.id,
            home_team_name="Huskies eSport",
            away_team_name="BIG Academy",
            # The 2591 specimen's 67 minutes: inside every wall-clock bound, so
            # only the venue's word can take it off the board.
            commence_time=now - timedelta(minutes=67),
            status="live",
            win_probability_sources=dict(SEEDED_SOURCES),
        )
        # Past the sport maximum plus the net's margin, with a score so it is
        # an observed game, and no play snapshot: the staleness arm suspends it.
        stale = Event(
            sport_id=nfl.id,
            home_team_name="Tampa Bay Stale",
            away_team_name="Cleveland Stale",
            commence_time=now
            - timedelta(hours=SPORT_MAX_DURATIONS["americanfootball"] + 0.7),
            status="live",
            home_score=19,
            away_score=23,
            win_probability_sources=dict(SEEDED_SOURCES),
        )
        session.add_all([settled, stale])
        await session.flush()
        market = FuturesMarket(
            source="kalshi",
            external_id=SETTLED_MATCH[1],
            name=SETTLED_MATCH[0],
            status="resolved",
            event_id=settled.id,
        )
        session.add(market)
        await session.flush()
        session.add_all([
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{SETTLED_MATCH[1]}-HUSK",
                name="Huskies eSport",
                is_winner=True,
                resolution_source="api_settlement",
            ),
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{SETTLED_MATCH[1]}-BIGA",
                name="BIG Academy",
                is_winner=False,
                resolution_source="api_settlement",
            ),
        ])
        await session.commit()
        ids = {"settled": settled.id, "stale": stale.id}

    yield engine, maker, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


async def _run_pass(maker, at_history_read):
    """Run the real pass; ``at_history_read(n)`` runs as history read ``n`` starts.

    No flush in the hook: the read is a ``text()`` statement, which does not
    autoflush, so the rows locked at the hook are exactly the rows the read
    would have run under.
    """
    import contextlib
    from unittest.mock import patch

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    import app.tasks.espn_sync as espn_sync

    reads = {"n": 0}

    class _TaskSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            if HISTORY_READ_MARKER in str(statement):
                reads["n"] += 1
                await at_history_read(reads["n"])
            return await super().execute(statement, *args, **kwargs)

    task_maker = async_sessionmaker(
        maker.kw["bind"], class_=_TaskSession, expire_on_commit=False
    )

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with task_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    with patch("app.tasks.base.get_task_session", _session):
        stats = await espn_sync._transition_event_statuses_impl()
    return stats, reads["n"]


async def _blend_write(engine, event_id) -> str:
    """One blend-shaped UPDATE on its own connection under a 500 ms lock budget."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await conn.execute(
                text(
                    "UPDATE events SET win_probability_sources = "
                    "COALESCE(win_probability_sources, '{}'::jsonb) "
                    "|| CAST(:src AS jsonb) WHERE id = :id"
                ),
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
                select(Event.status, Event.win_probability_sources).where(
                    Event.id == event_id
                )
            )
        ).one()


@needs_postgres
async def test_a_blend_write_reaches_a_venue_settled_row_during_the_live_history_read(
    seeded,
):
    engine, maker, ids = seeded
    outcome = {}

    async def _at_read(n):
        if n == 1:
            outcome["write"] = await _blend_write(engine, ids["settled"])

    stats, reads = await _run_pass(maker, _at_read)

    assert reads == 2
    assert stats["suspended_by_venue_settlement"] == 1
    assert outcome["write"] == "written", (
        "the pass held the row its venue-settlement arm had just suspended "
        "through the live-game history read, so a blend stamp under a 500 ms "
        "lock budget was refused"
    )
    row = await _row(maker, ids["settled"])
    assert row.status == "suspended"
    assert row.win_probability_sources["kalshi"] == WRITER_SOURCE["kalshi"]
    assert row.win_probability_sources["espn"] == SEEDED_SOURCES["espn"]


@needs_postgres
async def test_a_blend_write_reaches_a_stale_suspended_row_during_the_resume_history_read(
    seeded,
):
    engine, maker, ids = seeded
    outcome = {}

    async def _at_read(n):
        if n == 2:
            outcome["write"] = await _blend_write(engine, ids["stale"])

    stats, reads = await _run_pass(maker, _at_read)

    assert reads == 2
    assert stats["live_to_suspended"] == 1
    assert outcome["write"] == "written", (
        "the pass held the row its staleness arm had just suspended through the "
        "suspended-game history read, so a blend stamp under a 500 ms lock "
        "budget was refused"
    )
    row = await _row(maker, ids["stale"])
    assert row.status == "suspended"
    assert row.win_probability_sources["kalshi"] == WRITER_SOURCE["kalshi"]
    assert row.win_probability_sources["espn"] == SEEDED_SOURCES["espn"]


@needs_postgres
async def test_a_failed_resume_history_read_keeps_both_completed_suspensions(seeded):
    _engine, maker, ids = seeded

    async def _at_read(n):
        if n == 2:
            raise RuntimeError("the resume history read failed")

    with pytest.raises(RuntimeError, match="the resume history read failed"):
        await _run_pass(maker, _at_read)

    assert (await _row(maker, ids["settled"])).status == "suspended"
    assert (await _row(maker, ids["stale"])).status == "suspended"


@needs_postgres
async def test_the_control_a_pass_with_nothing_concurrent_suspends_both_once(seeded):
    _engine, maker, ids = seeded

    async def _nothing(_n):
        return None

    stats, reads = await _run_pass(maker, _nothing)

    assert reads == 2
    assert stats["suspended_by_venue_settlement"] == 1
    assert stats["live_to_suspended"] == 1
    assert stats["suspended_to_live"] == 0
    for key in ("settled", "stale"):
        row = await _row(maker, ids[key])
        assert row.status == "suspended"
        assert row.win_probability_sources == SEEDED_SOURCES
