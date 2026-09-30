"""#9435 — typing `giants` shows the New York Giants' own game under their card.

THE DEFECT, production 2026-09-28 18:2xZ, `GET /api/events/typeahead?q=giants`:
the New York Giants card, then four Yomiuri/Lotte Giants games and no New York
Giants game. The upcoming-games fetch (8 rows, soonest first) held the Giants'
Oct 4 game as row 8, behind five NPB rows, a KBO row and an AFLW row. Because it
was fetched, #5201's rescue arm stayed off (`debug_timing` ran
`lead_team_todays_final_query` and no `lead_team_next_match_query`), and the
four-slot cut dropped it before anything was scored.

THE TARGET: the Giants' game is the first event, directly under their card.
THE STRAWMAN replaces the ordering with the identity: the dropdown then serves
production's list (four namesake games, no Giants game), so the target testifies.
THE CONTROL is `cardinals`, whose only fixture is that same game: the ordering
runs (the lead team has a fixture) and the list is identical with and without it.

WHY POSTGRES: the defect is the fetch's ORDER BY + LIMIT meeting the pool cut,
and the gate that should have rescued it reads the fetched rows; a session double
sees none of that.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_lead_fixture_survives_the_cut_pg_9435.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9435 typeahead real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

NFL = "americanfootball_nfl"
NPB = "baseball_npb"
KBO = "baseball_kbo"
AFLW = "aussierules_aflw"

GIANTS_GAME = "Arizona Cardinals at New York Giants"

#: (sport, away, home, hours from now) — production's fetch, in its order.
_NAMESAKES = [
    (NPB, "Hiroshima Toyo Carp", "Yomiuri Giants", 15),
    (KBO, "Kiwoom Heroes", "Lotte Giants", 15.5),
    (NPB, "Yomiuri Giants", "Hanshin Tigers", 63),
    (NPB, "Yomiuri Giants", "Tokyo Yakult Swallows", 87),
    (AFLW, "Essendon Bombers", "GWS GIANTS", 105),
    (NPB, "Yokohama BayStars", "Yomiuri Giants", 111),
    (NPB, "Chunichi Dragons", "Yomiuri Giants", 120),
]


async def _seed(session):
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc)
    sports = {key: Sport(key=key, name=key) for key in (NFL, NPB, KBO, AFLW)}
    session.add_all(sports.values())
    await session.flush()

    # The nickname as an alternate name, as production carries it (team 547:
    # `['Giants']`): it is what makes `giants` resolve the club.
    teams = {
        name: Team(sport_id=sports[NFL].id, name=name, abbreviation=abbr,
                   alternate_names=[name.rsplit(" ", 1)[-1]])
        for name, abbr in [("New York Giants", "NYG"), ("Arizona Cardinals", "ARI")]
    }
    session.add_all(teams.values())
    await session.flush()

    session.add_all([
        *(
            Event(sport_id=sports[sport].id, away_team_name=away, home_team_name=home,
                  commence_time=now + timedelta(hours=hrs), status="scheduled")
            for sport, away, home, hrs in _NAMESAKES
        ),
        Event(sport_id=sports[NFL].id,
              away_team_name="Arizona Cardinals", home_team_name="New York Giants",
              away_team_id=teams["Arizona Cardinals"].id,
              home_team_id=teams["New York Giants"].id,
              commence_time=now + timedelta(hours=143), status="scheduled"),
    ])
    await session.commit()


@pytest.fixture
async def typeahead():
    """The real route, the real schema, the seed above; Redis patched out."""
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.main import app
    from app.services.database import Base, get_db, get_db_rw

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await _seed(session)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    try:
        with patch(
            "app.tasks.redis_state.get_redis_client",
            side_effect=RuntimeError("no redis"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:

                async def _do(q: str, **params) -> dict:
                    resp = await client.get(
                        "/api/events/typeahead", params={"q": q, **params}
                    )
                    assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                    return resp.json()

                yield _do
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _events(body: dict) -> list[str]:
    return [r["text"] for r in body["suggestions"] if r.get("type") == "event"]


def _texts(body: dict) -> list[str]:
    return [r["text"] for r in body["suggestions"]]


async def test_the_giants_game_is_the_first_event_under_the_card(typeahead):
    body = await typeahead("giants", debug_timing=1)
    texts = _texts(body)
    assert texts[0] == "New York Giants", texts
    assert _events(body)[:1] == [GIANTS_GAME], texts
    # The production path: the fetch held the game, so the rescue arm stayed off.
    assert "lead_team_next_match_query" not in body["debug_timing"], body["debug_timing"]


async def test_the_strawman_reproduces_production(typeahead, monkeypatch):
    """Without the ordering: four namesake games and no Giants game."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_typeahead_lead_fixtures_first",
                        lambda events, lead_ids: events)
    events = _events(await typeahead("giants"))
    assert GIANTS_GAME not in events, events
    assert len(events) == 4, events


async def test_a_team_whose_game_already_leads_is_unchanged(typeahead, monkeypatch):
    """The control: `cardinals` has one fixture and it is already in the four."""
    from app.routes import events as events_module

    armed = await typeahead("cardinals")
    assert GIANTS_GAME in _events(armed), _texts(armed)
    monkeypatch.setattr(events_module, "_typeahead_lead_fixtures_first",
                        lambda events, lead_ids: events)
    assert _texts(await typeahead("cardinals")) == _texts(armed)
