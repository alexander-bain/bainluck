"""#8586: ``mark_resolved_futures`` never date-resolves a market whose event is
live or has not started — against a REAL Postgres server.

The date is the thing that is wrong in that case. Medvedev–Royer's two Kalshi
markets carried a start-shaped ``resolution_date`` (08:00Z) and the 08:15Z run
resolved them 16 minutes into play; the page's headline read "No price".

Why a real server: the task's UPDATE merges a ``jsonb`` stamp with ``||`` and
screens on a correlated ``NOT EXISTS`` over ``events``; SQLite can host neither.

Every row below has an open status and a PAST ``resolution_date``, so every one
of them was resolved before this fix. Each control differs from a subject in
one column, so a gate that spared everything, or nothing, fails here.

Clock: ``_mark_resolved_impl(now=NOW)`` — fixed, offset rather than truncated
(gotcha #44).
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8586 "
            "mark_resolved_futures gate (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

NOW = datetime(2026, 9, 25, 8, 15, tzinfo=timezone.utc)
PAST_DATE = NOW - timedelta(minutes=15)  # the start-shaped date: 08:00Z
FUTURE_DATE = NOW + timedelta(days=14)


@pytest.fixture
async def pg_session(monkeypatch):
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base
    from app.tasks import futures as futures_mod

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _task_session():
        async with maker() as s:
            yield s

    monkeypatch.setattr(futures_mod, "get_task_session", _task_session)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _sport(session):
    """`sports.active` is NOT NULL with a PYTHON-side default — a raw INSERT
    bypasses it, so it is named."""
    return (await session.execute(text("""
                INSERT INTO sports (key, name, active)
                VALUES ('tennis_atp', 'ATP', TRUE)
                ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """))).scalar()


async def _event(session, *, status, commence):
    sport_id = await _sport(session)
    return (
        await session.execute(
            text("""
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, commence_time, status)
                VALUES (:sport, 'Medvedev', 'Royer', :commence, :status)
                RETURNING id
                """),
            {"sport": sport_id, "commence": commence, "status": status},
        )
    ).scalar()


async def _market(session, *, ext, event_id, resolution_date=PAST_DATE):
    """`market_metadata` is CAST: an untyped NULL into jsonb fails inference."""
    return (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     external_id, event_id, resolution_date, market_metadata)
                VALUES
                    (:name, 'kalshi', 'game_prop', TRUE, 'open',
                     :ext, :event_id, :rd, CAST(:metadata AS jsonb))
                RETURNING id
                """),
            {
                "name": f"#8586 {ext}",
                "ext": ext,
                "event_id": event_id,
                "rd": resolution_date,
                "metadata": None,
            },
        )
    ).scalar()


async def _status(session, market_id):
    return (
        await session.execute(
            text("SELECT status FROM futures_markets WHERE id = :id"),
            {"id": market_id},
        )
    ).scalar()


async def _run(session):
    from app.tasks.futures import _mark_resolved_impl

    await session.commit()
    stats = await _mark_resolved_impl(now=NOW)
    assert stats["errors"] == [], stats
    return stats


async def test_a_live_match_keeps_its_market_open(pg_session):
    live = await _event(pg_session, status="live", commence=PAST_DATE)
    m = await _market(pg_session, ext="KXATPMATCH-26SEP25MEDROY", event_id=live)

    await _run(pg_session)

    assert await _status(pg_session, m) == "open", (
        "the market of a LIVE event was date-resolved — its page loses its "
        "only price mid-match (#8586)"
    )


async def test_an_unstarted_match_keeps_its_market_open(pg_session):
    """Andreeva–Fernandez was resolved before it began (starts 10:30Z)."""
    ahead = await _event(
        pg_session, status="scheduled", commence=NOW + timedelta(hours=2, minutes=15)
    )
    m = await _market(pg_session, ext="KXWTAMATCH-26SEP25ANDFER", event_id=ahead)

    await _run(pg_session)

    assert await _status(pg_session, m) == "open"


async def test_the_controls_still_resolve(pg_session):
    """The belt must not strand what the task exists to clean up (gotcha #33).

    * a finished event — same market, event `completed`;
    * a stale `scheduled` event whose start has PASSED — differs from the
      unstarted subject only in the start, so the gate reads the clock, not the
      word 'scheduled';
    * an unlinked market — no event to consult.
    """
    done = await _event(pg_session, status="completed", commence=PAST_DATE)
    stale = await _event(
        pg_session, status="scheduled", commence=NOW - timedelta(hours=3)
    )
    m_done = await _market(pg_session, ext="KXATPMATCH-DONE", event_id=done)
    m_stale = await _market(pg_session, ext="KXATPMATCH-STALE", event_id=stale)
    m_free = await _market(pg_session, ext="KXATPMATCH-FREE", event_id=None)

    stats = await _run(pg_session)

    assert await _status(pg_session, m_done) == "resolved"
    assert await _status(pg_session, m_stale) == "resolved"
    assert await _status(pg_session, m_free) == "resolved"
    assert stats["marked_resolved"] == 3, stats


async def test_the_date_screen_is_unchanged(pg_session):
    """A future date on a finished event stays open, as before."""
    done = await _event(pg_session, status="completed", commence=PAST_DATE)
    m = await _market(
        pg_session, ext="KXATPMATCH-LATER", event_id=done, resolution_date=FUTURE_DATE
    )

    await _run(pg_session)

    assert await _status(pg_session, m) == "open"
