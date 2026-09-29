"""#9522 + #9527 — through the real routes: the dropdown's tennis row reads
"Michelsen v Alcaraz", and a "vs" query finds the game.

THE DEFECT, production 2026-09-29 ~02:10Z: `alcaraz` offered *Michelsen at Alcaraz*
(15320475, tennis_atp), a home side a tennis match does not have.

THE TARGET: the tennis row and an MMA row read " v ", away first.
THE STRAWMAN swaps the rule for the old inline `"{away} at {home}"`: the row is
production's *Michelsen at Alcaraz* again, so the target case testifies.
THE CONTROL: an MLB game in the same database keeps " at ".

#9527, production 2026-09-29 ~02:25Z: `red sox vs yankees` returned no game on
either route while `red sox at yankees` returned the Wild Card game. THE TARGET:
`vs`, `vs.`, `v` and `@` find it on both. THE STRAWMAN empties the connector
set: zero games again. And the tennis row's new text, typed back as a query
(a saved recent search), still finds its match — the reason the two ship
together.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_individual_sport_v_pg_9522.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9522 typeahead real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

TENNIS = "tennis_atp"
MMA = "mma_mixed_martial_arts"
MLB = "baseball_mlb"


async def _seed(session) -> dict[str, int]:
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team

    now = datetime.now(timezone.utc)
    tennis = Sport(key=TENNIS, name="ATP")
    mma = Sport(key=MMA, name="MMA")
    mlb = Sport(key=MLB, name="MLB")
    session.add_all([tennis, mma, mlb])
    await session.flush()

    teams = {
        name: Team(sport_id=sport.id, name=name, abbreviation=abbr, alternate_names=alts)
        for name, sport, abbr, alts in [
            ("Boston Red Sox", mlb, "BOS", ["Red Sox"]),
            ("New York Yankees", mlb, "NYY", ["Yankees"]),
        ]
    }
    session.add_all(teams.values())
    await session.flush()

    def _game(sport, away, home, when):
        return Event(
            sport_id=sport.id,
            away_team_name=away,
            home_team_name=home,
            away_team_id=teams[away].id if away in teams else None,
            home_team_id=teams[home].id if home in teams else None,
            commence_time=when,
            status="scheduled",
        )

    games = {
        "tennis": _game(tennis, "Michelsen", "Alcaraz", now + timedelta(hours=23)),
        "mma": _game(mma, "Conor McGregor", "Paddy Pimblett", now + timedelta(days=3)),
        "mlb": _game(mlb, "Boston Red Sox", "New York Yankees", now + timedelta(hours=22)),
    }
    session.add_all(games.values())
    await session.flush()
    # Production's competition for the seven (2026-09-29): Polymarket's inning
    # and total markets all SAY "vs.", so a scorer reading the whole query
    # could rank every one of them above the game that does not.
    for i, suffix in enumerate(["", ": O/U 8.5", *[f" - {n}th Inning Winner" for n in range(3, 10)]]):
        market = FuturesMarket(
            source="polymarket",
            external_id=f"pm-9527-{i}",
            name=f"Boston Red Sox vs. New York Yankees{suffix}",
            market_type="duel",
            status="open",
            resolution_date=now + timedelta(days=1),
        )
        session.add(market)
        await session.flush()
        for name, price in (("Boston Red Sox", 0.48), ("New York Yankees", 0.52)):
            session.add(FuturesOutcome(
                market_id=market.id,
                external_id=f"pm-9527-{i}:{name}",
                name=name,
                current_probability=price,
            ))
    await session.commit()
    return {k: g.id for k, g in games.items()}


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
        ids = await _seed(session)

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

                async def _do(q: str) -> list[str]:
                    resp = await client.get("/api/events/typeahead", params={"q": q})
                    assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                    return [
                        r["text"] for r in resp.json()["suggestions"]
                        if r.get("type") == "event"
                    ]

                async def _search(q: str) -> list[int]:
                    resp = await client.get("/api/events/search", params={"q": q})
                    assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                    return [r["id"] for r in resp.json().get("results") or []]

                _do.search = _search
                _do.ids = ids
                yield _do
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_the_tennis_row_reads_v(typeahead):
    """The production specimen: `alcaraz`."""
    events = await typeahead("alcaraz")
    assert "Michelsen v Alcaraz" in events, events
    assert "Michelsen at Alcaraz" not in events, events


async def test_a_fight_reads_v(typeahead):
    events = await typeahead("mcgregor")
    assert "Conor McGregor v Paddy Pimblett" in events, events


async def test_the_strawman_reproduces_production(typeahead, monkeypatch):
    """With the old inline rule, the row is production's `Michelsen at Alcaraz`."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_typeahead_event_text", lambda away, home, _key: f"{away} at {home}"
    )
    events = await typeahead("alcaraz")
    assert "Michelsen at Alcaraz" in events, events


async def test_a_team_sport_keeps_at(typeahead):
    """The control: the same database, an MLB game, unchanged."""
    events = await typeahead("red sox")
    assert "Boston Red Sox at New York Yankees" in events, events


VS_QUERIES = [
    "red sox vs yankees",
    "yankees vs red sox",
    "red sox vs. yankees",
    "red sox v yankees",
    "red sox @ yankees",
]


@pytest.mark.parametrize("q", VS_QUERIES)
async def test_a_vs_query_finds_the_game_in_the_dropdown(typeahead, q):
    """#9527's production specimen, and its spellings."""
    events = await typeahead(q)
    assert "Boston Red Sox at New York Yankees" in events, (q, events)


@pytest.mark.parametrize("q", VS_QUERIES)
async def test_a_vs_query_finds_the_game_on_the_search_page(typeahead, q):
    ids = await typeahead.search(q)
    assert typeahead.ids["mlb"] in ids, (q, ids)


async def test_the_connector_strawman_reproduces_production(typeahead, monkeypatch):
    """With no connectors dropped, `red sox vs yankees` finds no game again.

    The SEARCH half only. On this three-game database the dropdown still
    reaches the game without the fix — its trigram arm fires whenever a team
    row matched and no game did, and with two MLB clubs in the table that arm
    has nothing to lose to. Production served 0 games (debug_timing showed
    `events_query` ran and `fuzzy_and_concepts` did not). The dropdown's proof
    is that its term list is now IDENTICAL to `red sox at yankees`'s, which
    production already serves correctly (the test below the control)."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_MATCHUP_CONNECTORS", frozenset())
    assert typeahead.ids["mlb"] not in await typeahead.search("red sox vs yankees")


async def test_the_at_control_is_unchanged(typeahead):
    """`at` was always dropped; it still finds the game on both routes."""
    assert "Boston Red Sox at New York Yankees" in await typeahead("red sox at yankees")
    assert typeahead.ids["mlb"] in await typeahead.search("red sox at yankees")


async def test_the_tennis_rows_own_text_finds_its_match(typeahead):
    """The dropdown saves a tapped row's text as a recent search; typed back
    into search, "Michelsen v Alcaraz" must still find the match."""
    assert typeahead.ids["tennis"] in await typeahead.search("Michelsen v Alcaraz")


def test_the_dropdown_terms_for_vs_equal_the_terms_for_at():
    """The dropdown's production oracle: `red sox at yankees` returns the game
    on production today, and `vs` now hands the filters the same term list."""
    from app.routes.events import _strip_search_scaffolding as strip

    for connector in ("vs", "vs.", "v", "@", "versus"):
        assert strip(f"red sox {connector} yankees".split()) == strip(
            "red sox at yankees".split()
        ), connector
