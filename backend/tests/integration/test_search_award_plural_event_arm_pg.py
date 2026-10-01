"""`oscars` stops listing fighters named Oscar as games, proved through both routes on real Postgres.

Production 2026-10-01 (`oscars`, 119 searches / 90 days):

    /api/events/search?q=oscars     GAMES (2): Ricardo Rafael Sandoval v Oscar Collazo (boxing)
                                               Igor Cavalcanti v Oscar Ravello (MMA, a fortnight
                                               old, "No result reported")
    /api/events/typeahead?q=oscars  row 2: Genaro Alberto Olivieri v Pedro Boscardin Dias (tennis)

`_SEARCH_TERM_SYNONYMS` expands `oscars` to `oscar` so the plural reaches the
singular-named award markets. The participant-name arms read the same expansion,
so `%oscar%` reached the fighters and the inside of "Boscardin"; the dropdown's FTS
arm also stems `oscars` to `oscar` by itself. The fix keeps the expansion on the
market arms only (`_event_arm_expanded`) and drops the dropdown's event FTS arm for
these queries (`_names_person_name_award`).

Why Postgres: the `%oscar%` ILIKE and the `oscars` -> `oscar` stem are Postgres
facts. The strawman case empties the person-name set and asserts the games return,
so the cases measure the fix and not an empty seed.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres award-plural "
            "event-arm contract (CI job `search-recall` provides one)"
        ),
    ),
]

COLLAZO = "Sandoval v Collazo"
BOSCARDIN = "Olivieri v Boscardin"
FIGHT_HOME, FIGHT_AWAY = "Oscar Collazo", "Ricardo Rafael Sandoval"
TENNIS_HOME, TENNIS_AWAY = "Pedro Boscardin Dias", "Genaro Alberto Olivieri"
BEST_PICTURE = "Oscar Winner: Best Picture"


@pytest.fixture
async def maker():
    """Clean schema per test — the database is shared with the whole job."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()


@pytest.fixture
async def http(maker):
    """The real app and database. Redis raises, so every ask is a cache miss —
    the strawman asks the same query the ship case asks."""
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no redis in the recall gate"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def _get(path: str, q: str) -> dict:
                resp = await client.get(path, params={"q": q})
                assert resp.status_code == 200, f"{path} {q!r} -> {resp.status_code}"
                return resp.json()

            yield _get

    app.dependency_overrides.clear()


async def _seed(session):
    """Production's shapes, relative clocks (gotcha #44): the fight and the
    tennis match are both inside the dropdown's upcoming window."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    sports = {
        key: Sport(key=key, name=key)
        for key in ("boxing_boxing", "tennis_other", "entertainment_awards")
    }
    session.add_all(sports.values())
    await session.flush()

    session.add(Event(sport_id=sports["boxing_boxing"].id, home_team_name=FIGHT_HOME,
                      away_team_name=FIGHT_AWAY, commence_time=now + timedelta(days=1),
                      status="scheduled", event_tags=["provenance:source:espn"]))
    session.add(Event(sport_id=sports["tennis_other"].id, home_team_name=TENNIS_HOME,
                      away_team_name=TENNIS_AWAY, commence_time=now + timedelta(hours=6),
                      status="scheduled", event_tags=["provenance:source:espn"]))

    market = FuturesMarket(source="kalshi", external_id="KXOSCARPIC-27",
                           name=BEST_PICTURE, status="open",
                           resolution_date=now + timedelta(days=150))
    session.add(market)
    await session.flush()
    for name, p in (("The Odyssey", 0.49), ("Hamnet", 0.2)):
        session.add(FuturesOutcome(market_id=market.id, external_id=f"KXOSCARPIC-27:{name}",
                                   name=name, current_probability=p))
    await session.commit()


def _search_games(payload) -> set[str]:
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    out = set()
    for e in payload["results"]:
        names = {e.get("home_team"), e.get("away_team")}
        if FIGHT_HOME in names:
            out.add(COLLAZO)
        if TENNIS_HOME in names:
            out.add(BOSCARDIN)
    return out


def _typeahead_games(payload) -> set[str]:
    assert "suggestions" in payload, f"no `suggestions` key; got {sorted(payload)}"
    out = set()
    for s in payload["suggestions"]:
        if s.get("type") != "event":
            continue
        if FIGHT_HOME in (s.get("text") or ""):
            out.add(COLLAZO)
        if TENNIS_HOME in (s.get("text") or ""):
            out.add(BOSCARDIN)
    return out


async def test_search_oscars_lists_no_fighter_named_oscar(maker, http):
    async with maker() as session:
        await _seed(session)

    payload = await http("/api/events/search", "oscars")
    assert _search_games(payload) == set(), payload["results"]
    # The expansion still does its job on the market arm.
    assert BEST_PICTURE in [f["name"] for f in payload["futures"]]


async def test_typeahead_oscars_offers_no_game(maker, http):
    async with maker() as session:
        await _seed(session)

    payload = await http("/api/events/typeahead", "oscars")
    assert _typeahead_games(payload) == set(), payload["suggestions"]


async def test_typing_the_fighters_name_still_finds_his_fight(maker, http):
    """Control: the singular is a person's name, and it still reaches him."""
    async with maker() as session:
        await _seed(session)

    assert COLLAZO in _search_games(await http("/api/events/search", "oscar collazo"))
    assert COLLAZO in _typeahead_games(await http("/api/events/typeahead", "collazo"))


async def test_strawman_without_the_guard_the_games_come_back(maker, http, monkeypatch):
    """Empty the person-name set and both defects return on this seed — so the
    two cases above measure the fix, not a seed nothing could match."""
    import app.routes.events as events

    monkeypatch.setattr(events, "_PERSON_NAME_AWARD_PLURALS", frozenset())
    async with maker() as session:
        await _seed(session)

    assert COLLAZO in _search_games(await http("/api/events/search", "oscars"))
    assert BOSCARDIN in _typeahead_games(await http("/api/events/typeahead", "oscars"))
