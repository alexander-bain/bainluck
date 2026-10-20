"""#11296 — the finished card on `/api/feed` and `/api/leagues/{sport}` carries the page's pregame projection.

Real app, real Postgres, real routes (Discover's clearance condition 3). The
helper's own gates prove selection; this proves the three routes reach a
POSITIVE on real ORM rows. The failure it exists for is the quiet one: a list
route whose rows are loaded or wrapped differently (a deferred column, a view)
would answer ``start_not_from_schedule`` on every card, which is the
always-null delivery #11296 forbids and which no unit fake can see.

One completed NFL final, sportsbook rows on both sides of its listed start: the
rows before it project 25.8 / 22.2 and 25.0 / 22.5 (mean 25.4 / 22.4); the
rows after it, the in-play 31.2 / 23.8 shape of UX's 15328569, must reach no
card. The same object must come back from the event page, the league results
rail and the feed.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` like #11295's sibling, and named by a
step in the ``database-integration`` job.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.models import Event, OddsSnapshot, Sport
from app.utils.odds_math import project_scores

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #11296 list "
            "route gate (the database-integration CI job provides one)"
        ),
    ),
]

_SPORT_KEY = "americanfootball_nfl"
FINAL = 911_296_01

#: (book, home prob, spread, total, minutes from the listed start).
_ROWS = [
    ("draftkings", 0.60, -3.0, 47.0, -600),
    ("draftkings", 0.61, -3.5, 48.0, -10),     # ← draftkings: 25.8 / 22.2
    ("draftkings", 0.90, -7.4, 55.0, 205),     # in-play
    ("fanduel", 0.58, -2.5, 47.5, -30),        # ← fanduel: 25.0 / 22.5
    ("fanduel", 0.90, -7.4, 55.0, 205),        # in-play
]


def _kickoff() -> datetime:
    # A recent final, so the results rail and the feed admit it. Offset FIRST,
    # then truncate (gotcha #44): no branch on the clock.
    return (datetime.now(timezone.utc) - timedelta(hours=6)).replace(
        minute=0, second=0, microsecond=0
    )


@pytest.fixture
async def pg_engine():
    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=True))
    yield engine
    async with engine.begin() as conn:
        await conn.execute(delete(OddsSnapshot).where(OddsSnapshot.event_id == FINAL))
        await conn.execute(delete(Event).where(Event.id == FINAL))
    await engine.dispose()


@pytest.fixture
def no_caches(monkeypatch):
    """Every Redis touch degrades to a miss and no in-process cache answers."""
    from app.routes import events as events_route
    from app.tasks import redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: None)
    events_route._event_detail_cache.clear()
    yield
    events_route._event_detail_cache.clear()


@pytest.fixture
async def client(pg_engine, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _real_get_db():
        async with AsyncSession(pg_engine, expire_on_commit=False) as session:
            yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _real_get_db
    app.dependency_overrides[get_db_rw] = _real_get_db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


async def _seed(pg_engine, kickoff):
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        sport_id = (
            await s.execute(select(Sport.id).where(Sport.key == _SPORT_KEY))
        ).scalar_one_or_none()
        if sport_id is None:
            sport = Sport(key=_SPORT_KEY, name="NFL", active=True)
            s.add(sport)
            await s.flush()
            sport_id = sport.id
        await s.execute(delete(OddsSnapshot).where(OddsSnapshot.event_id == FINAL))
        await s.execute(delete(Event).where(Event.id == FINAL))
        s.add(
            Event(
                id=FINAL,
                sport_id=sport_id,
                external_id=f"pg11296-{FINAL}",
                home_team_name="Tampa Bay Buccaneers",
                away_team_name="Green Bay Packers",
                commence_time=kickoff,
                commence_time_source="odds_api",
                status="completed",
                home_score=31,
                away_score=38,
                completed_at=kickoff + timedelta(hours=3, minutes=30),
                opening_home_probability=0.58,
                opening_away_probability=0.42,
            )
        )
        await s.flush()
        for book, prob, spread, total, minutes in _ROWS:
            home, away = project_scores(spread, total)
            captured = kickoff + timedelta(minutes=minutes)
            s.add(
                OddsSnapshot(
                    event_id=FINAL, bookmaker=book,
                    captured_at=captured, valid_until=captured,
                    home_win_probability=prob, away_win_probability=round(1 - prob, 4),
                    home_spread=spread, over_under=total,
                    projected_home_score=home, projected_away_score=away,
                    reading_count=1,
                )
            )
        await s.commit()


def _expected(kickoff):
    return {
        "projected_home_score": 25.4,
        "projected_away_score": 22.4,
        "kind": "last_before_scheduled_start",
        "boundary": "scheduled_start",
        "boundary_at": kickoff.isoformat(),
        "earliest_captured_at": (kickoff - timedelta(minutes=30)).isoformat(),
        "latest_captured_at": (kickoff - timedelta(minutes=10)).isoformat(),
        "source": "sportsbooks",
        "basis": "consensus_spread_total",
        "bookmaker_count": 2,
        "unit": "points",
        "period": "full_game",
    }


async def test_the_event_page_serves_the_pregame_projection(pg_engine, client, no_caches):
    kickoff = _kickoff()
    await _seed(pg_engine, kickoff)
    body = (await client.get(f"/api/events/{FINAL}")).json()
    assert body["pregame_projection"] == _expected(kickoff)
    # The control: the in-play pair is what current_odds serves on this final.
    assert body["current_odds"]["projected_home_score"] == 31.2


async def test_the_league_results_rail_serves_the_same_object(pg_engine, client, no_caches):
    kickoff = _kickoff()
    await _seed(pg_engine, kickoff)
    body = (await client.get(f"/api/leagues/{_SPORT_KEY}")).json()
    cards = [c for c in body.get("recent_results") or [] if c.get("id") == FINAL]
    assert cards, [c.get("id") for c in body.get("recent_results") or []]
    assert cards[0]["pregame_projection"] == _expected(kickoff)
    assert "projected_home_score" not in (cards[0].get("current_odds") or {})


async def test_the_feed_card_serves_the_same_object(pg_engine, client, no_caches):
    kickoff = _kickoff()
    await _seed(pg_engine, kickoff)
    body = (await client.get("/api/feed?mode=sports&limit=200")).json()
    cards = [
        i["data"] for i in body.get("items") or []
        if i.get("type") == "event" and (i.get("data") or {}).get("id") == FINAL
    ]
    assert cards, [((i.get("data") or {}).get("id"), i.get("type")) for i in body.get("items") or []][:20]
    assert cards[0]["pregame_projection"] == _expected(kickoff)
    assert "projected_home_score" not in (cards[0].get("current_odds") or {})


async def test_a_slow_read_costs_the_feed_card_this_key_and_nothing_else(
    pg_engine, monkeypatch
):
    """#11295's C1 on the D2 attach: the server cancels the read inside its bound.

    The statement is swapped for a five-second sleep that takes the same binds.
    Under the feed's bound (100 ms here) the server cancels it (57014); the card
    keeps its probabilities, answers ``read_failed`` (never printed), the attach
    returns well inside the sleep, and the session is usable with its own timeout
    untouched. ``read_failed`` rather than ``start_not_from_schedule`` also proves
    the real ORM row reached the statement.
    """
    from sqlalchemy import text

    from app.routes import feed
    from app.utils import card_projected_pair as cpp
    from app.utils import pregame_projection as pp

    kickoff = _kickoff()
    await _seed(pg_engine, kickoff)
    monkeypatch.setattr(
        pp,
        "PREGAME_PROJECTION_SQL",
        "SELECT pg_sleep(5) WHERE cast(:ids as integer[]) IS NOT NULL "
        "AND cast(:cutoffs as timestamptz[]) IS NOT NULL",
    )
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        events = (
            (await s.execute(select(Event).where(Event.id == FINAL))).scalars().all()
        )
        before = (await s.execute(text("SHOW statement_timeout"))).scalar_one()
        item = {
            "type": "event",
            "data": {
                "id": FINAL,
                "status": "completed",
                "sport": _SPORT_KEY,
                "current_odds": {"home_probability": 0.58, "away_probability": 0.42},
            },
        }
        remaining = (cpp.CARD_PROJECTION_DEADLINE_MARGIN_MS + 100) / 1000
        started = datetime.now(timezone.utc)
        await feed._attach_pregame_projections(s, [item], events, remaining_s=remaining)
        took = (datetime.now(timezone.utc) - started).total_seconds()
        assert took < 3.0
        assert "pregame_projection" not in item["data"]
        assert item["data"]["pregame_projection_unavailable"] == "read_failed"
        assert item["data"]["current_odds"] == {
            "home_probability": 0.58,
            "away_probability": 0.42,
        }
        assert (await s.execute(text("SELECT 1"))).scalar_one() == 1
        assert (await s.execute(text("SHOW statement_timeout"))).scalar_one() == before
