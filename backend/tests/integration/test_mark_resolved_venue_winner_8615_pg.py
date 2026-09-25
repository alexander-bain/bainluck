"""#8615: ``mark_resolved_futures`` resolves an open one-winner board that the
venue has already graded — against a REAL Postgres server.

The reader's specimen: search served "Who will be confirmed as Fed chair?
Kevin Warsh >99%" as a live question on 9/25. Every leg was graded
``api_settlement`` on 7/15 (Warsh the winner); the row stayed ``open`` under
Kalshi's 2029 backstop date because the only Kalshi status writer needs the
venue's nested legs, and the venue now answers ``markets: []``.

Why a real server: the statement reads ``market_metadata->'shape'`` with
``->>`` and ``?``, merges a ``jsonb`` stamp with ``||`` and screens on
correlated ``EXISTS`` over outcomes and events; SQLite can host none of it.

Every row below is ``open`` with a FUTURE ``resolution_date``, so the date
statement never touches it: whatever resolves here resolved on the new
statement. Each control differs from the subject in ONE input.

Clock: ``_mark_resolved_impl(now=NOW)`` — fixed (gotcha #44).
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8615 "
            "mark_resolved_futures gate (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

NOW = datetime(2026, 9, 25, 14, 15, tzinfo=timezone.utc)
BACKSTOP = datetime(2029, 1, 8, 15, 0, tzinfo=timezone.utc)

#: The specimen's stored shape, verbatim from production row 2558995.
ONE_WINNER_SHAPE = {
    "v": 2,
    "shape": "field",
    "evidence": ["exactly_one_structured", "expected_winners:1", "mutually_exclusive:true"],
    "confidence": "high",
    "expected_winners": 1,
}

#: The ladder that rejected the broader "every stored leg graded" rule:
#: `KX10YRDIRHM-26SEP30H`, 25/25 stored rungs graded YES, 6 more trading.
LADDER_SHAPE = {
    "v": 2,
    "shape": "field",
    "evidence": [],
    "confidence": "low",
    "expected_winners": None,
}


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


async def _event(session, *, status, commence):
    """`sports.active` is NOT NULL with a PYTHON-side default — named."""
    sport_id = (await session.execute(text("""
                INSERT INTO sports (key, name, active)
                VALUES ('tennis_atp', 'ATP', TRUE)
                ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """))).scalar()
    return (
        await session.execute(
            text("""
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, commence_time, status)
                VALUES (:sport, 'A', 'B', :commence, :status)
                RETURNING id
                """),
            {"sport": sport_id, "commence": commence, "status": status},
        )
    ).scalar()


async def _board(
    session,
    *,
    ext,
    shape=ONE_WINNER_SHAPE,
    legs=(("W", True, "api_settlement"), ("L", False, "api_settlement")),
    event_id=None,
):
    """A market plus its legs; each leg is (suffix, is_winner, resolution_source)."""
    market_id = (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     external_id, event_id, resolution_date, market_metadata)
                VALUES
                    (:name, 'kalshi', 'politics', TRUE, 'open',
                     :ext, :event_id, :rd, CAST(:metadata AS jsonb))
                RETURNING id
                """),
            {
                "name": f"#8615 {ext}",
                "ext": ext,
                "event_id": event_id,
                "rd": BACKSTOP,
                "metadata": json.dumps({"shape": shape}) if shape else None,
            },
        )
    ).scalar()
    for suffix, won, source in legs:
        await session.execute(
            text("""
                INSERT INTO futures_outcomes
                    (market_id, external_id, name, current_probability,
                     is_winner, resolution_source)
                VALUES (:m, :ext, :name, :p, :won, :src)
                """),
            {
                "m": market_id,
                "ext": f"{ext}-{suffix}",
                "name": suffix,
                "p": 0.9995 if won else 0.0,
                "won": won,
                "src": source,
            },
        )
    return market_id


async def _row(session, market_id):
    return (
        await session.execute(
            text("""
                SELECT status, settled_at, market_metadata
                FROM futures_markets WHERE id = :id
                """),
            {"id": market_id},
        )
    ).one()


async def _run(session):
    from app.tasks.futures import _mark_resolved_impl

    await session.commit()
    stats = await _mark_resolved_impl(now=NOW)
    assert stats["errors"] == [], stats
    return stats


async def test_a_venue_graded_one_winner_board_resolves(pg_session):
    """The Fed-chair specimen: resolved, stamped, settled, counted."""
    m = await _board(pg_session, ext="KXFEDCHAIRCONFIRM")

    stats = await _run(pg_session)

    status, settled_at, metadata = await _row(pg_session, m)
    assert status == "resolved", (
        "a one-winner board the venue already graded stayed open — search "
        "keeps serving 'Kevin Warsh >99%' as a live question (#8615)"
    )
    assert settled_at is not None
    gate = metadata["resolution_gate"]
    assert gate["proof_kind"] == "winner" and gate["task"] == "mark_resolved_futures"
    assert metadata["shape"] == ONE_WINNER_SHAPE, "the stamp clobbered the shape"
    assert stats["marked_resolved_venue_winner"] == 1, stats
    assert stats["marked_resolved"] == 0, (
        "the date statement's count moved on a future-dated row", stats
    )


async def test_a_ladder_with_every_stored_rung_graded_stays_open(pg_session):
    """Our legs can be a subset of the venue's: KX10YRDIRHM-26SEP30H."""
    m = await _board(
        pg_session,
        ext="KX10YRDIRHM-26SEP30H",
        shape=LADDER_SHAPE,
        legs=[(f"T{i}", True, "api_settlement") for i in range(25)],
    )

    await _run(pg_session)

    assert (await _row(pg_session, m)).status == "open"


async def test_each_one_column_control_stays_open(pg_session):
    """Each differs from the subject in exactly one input."""
    medium = dict(ONE_WINNER_SHAPE, confidence="medium")
    not_exclusive = dict(
        ONE_WINNER_SHAPE, evidence=["exactly_one_structured", "expected_winners:1"]
    )
    two_winners = dict(ONE_WINNER_SHAPE, expected_winners=2)
    ids = {
        "winner graded by a non-venue source": await _board(
            pg_session,
            ext="CTRL-SRC",
            legs=(("W", True, "price_inferred"), ("L", False, "api_settlement")),
        ),
        "no winner leg": await _board(
            pg_session,
            ext="CTRL-NOWIN",
            legs=(("W", False, "api_settlement"), ("L", False, "api_settlement")),
        ),
        "winner is NULL (ungraded)": await _board(
            pg_session,
            ext="CTRL-NULL",
            legs=(("W", None, None), ("L", False, "api_settlement")),
        ),
        "confidence medium": await _board(pg_session, ext="CTRL-CONF", shape=medium),
        "not mutually exclusive": await _board(
            pg_session, ext="CTRL-MEX", shape=not_exclusive
        ),
        "expected_winners 2": await _board(pg_session, ext="CTRL-EW", shape=two_winners),
        "no shape at all": await _board(pg_session, ext="CTRL-NOSHAPE", shape=None),
    }

    stats = await _run(pg_session)

    still_open = {k: (await _row(pg_session, v)).status for k, v in ids.items()}
    assert all(s == "open" for s in still_open.values()), still_open
    assert stats["marked_resolved_venue_winner"] == 0, stats


async def test_the_event_graph_screen_holds_for_this_statement_too(pg_session):
    """#8586's belt: a live or unstarted event keeps its market open; a
    finished one does not."""
    live = await _event(pg_session, status="live", commence=NOW - timedelta(hours=1))
    ahead = await _event(
        pg_session, status="scheduled", commence=NOW + timedelta(hours=2)
    )
    done = await _event(
        pg_session, status="completed", commence=NOW - timedelta(hours=5)
    )
    m_live = await _board(pg_session, ext="EV-LIVE", event_id=live)
    m_ahead = await _board(pg_session, ext="EV-AHEAD", event_id=ahead)
    m_done = await _board(pg_session, ext="EV-DONE", event_id=done)

    stats = await _run(pg_session)

    assert (await _row(pg_session, m_live)).status == "open"
    assert (await _row(pg_session, m_ahead)).status == "open"
    assert (await _row(pg_session, m_done)).status == "resolved"
    assert stats["marked_resolved_venue_winner"] == 1, stats
