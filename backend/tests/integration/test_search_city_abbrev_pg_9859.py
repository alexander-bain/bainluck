"""#9859 — `sf giants` finds the San Francisco Giants, proved through the route on real Postgres.

Production 2026-09-30 15:4xZ, `/api/events/search`::

    sf giants    0 teams   games led by San Francisco 49ers @ New York Giants
    la kings     0 teams   3rd game Los Angeles Lakers @ Sacramento Kings
    la angels    teams: Los Angeles Clippers, LA Galaxy   (not the Angels)
    ny rangers / kc royals / tb rays / la dodgers / ...   0 teams

while the dropdown offered each club. The game rails already spell `sf` out per
word; the Teams gate is full-text over the whole typed query, and `sf` is not a
word of "San Francisco Giants". With no team card, #9044's split-words key never
armed, so `sf` on the 49ers plus `giants` on New York led the games.

The fix ADDS the spelled-out city beside the typed query (gate + SQL rank) and
lets the card's scorer see each club's name with its city abbreviated. The
Kalshi case asserts the typed `la` still reaches `LA Kings vs COL Avalanche`.

Why Postgres: the Teams gate is pure FTS, and `angels` stemming to the stem of
"Angeles" (the `la angels` → Clippers defect) is a Postgres fact. SQLite serves
neither.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres city-abbreviation "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

SF_GIANTS = "San Francisco Giants"
NINERS = "San Francisco 49ers"
NY_GIANTS = "New York Giants"
DODGERS = "Los Angeles Dodgers"
KINGS = "Los Angeles Kings"
SAC_KINGS = "Sacramento Kings"
LAKERS = "Los Angeles Lakers"
AVS = "Colorado Avalanche"
ANGELS = "Los Angeles Angels"
MARINERS = "Seattle Mariners"
CLIPPERS = "Los Angeles Clippers"
GALAXY = "LA Galaxy"
RANGERS = "New York Rangers"
KALSHI_KINGS = "LA Kings vs COL Avalanche: Spread"


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
async def search(maker):
    """`GET /api/events/search` against the real app and database.

    Redis raises, so every ask is a cache miss — the strawman case asks the
    same query the ship case asks, and a live cache would answer it from the
    fixed run.
    """
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
        ) as http:

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def _market(session, source, external_id, name, now):
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=source,
        external_id=external_id,
        name=name,
        status="open",
        resolution_date=now + timedelta(days=30),
    )
    session.add(market)
    await session.flush()
    # A market with no outcomes is served by no spelling at all (#6977's note).
    for outcome_name in ("Yes", "No"):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{external_id}:{outcome_name}",
                name=outcome_name,
                current_probability=0.5,
            )
        )


async def _seed(session):
    """Production's shapes, relative clocks (gotcha #44). The cross-club game is
    always the SOONEST, so today's order (upcoming, soonest first) leads with it
    unless the split-words key sinks it. The Clippers and the Galaxy store both
    spellings of their city as aliases, which is what let `la angels` card them."""
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc)
    sports = {
        key: Sport(key=key, name=key)
        for key in ("baseball_mlb", "americanfootball_nfl", "icehockey_nhl",
                    "basketball_nba", "soccer_usa_mls")
    }
    session.add_all(sports.values())
    await session.flush()

    def team(sport, name, abbreviation, aliases=None):
        session.add(Team(sport_id=sports[sport].id, name=name,
                         abbreviation=abbreviation, alternate_names=aliases))

    def game(sport, away, home, days):
        session.add(Event(sport_id=sports[sport].id, away_team_name=away,
                          home_team_name=home, commence_time=now + timedelta(days=days),
                          status="scheduled", event_tags=["provenance:source:espn"]))

    team("baseball_mlb", SF_GIANTS, "SF")
    team("americanfootball_nfl", NINERS, "SF")
    team("americanfootball_nfl", NY_GIANTS, "NYG")
    team("baseball_mlb", DODGERS, "LAD")
    team("icehockey_nhl", KINGS, "LAK")
    team("basketball_nba", SAC_KINGS, "SAC")
    team("basketball_nba", LAKERS, "LAL", ["LA Lakers"])
    team("baseball_mlb", ANGELS, "LAA")
    team("basketball_nba", CLIPPERS, "LAC", ["LA Clippers", "Los Angeles Clippers"])
    team("soccer_usa_mls", GALAXY, "LA", ["Los Angeles Galaxy"])
    team("icehockey_nhl", RANGERS, "NYR")

    game("americanfootball_nfl", NINERS, NY_GIANTS, 1)
    game("baseball_mlb", DODGERS, SF_GIANTS, 2)
    game("basketball_nba", LAKERS, SAC_KINGS, 1)
    game("icehockey_nhl", KINGS, AVS, 2)
    game("baseball_mlb", ANGELS, MARINERS, 2)
    game("icehockey_nhl", RANGERS, "Boston Bruins", 2)
    await _market(session, "kalshi", "KXNHLSPREAD-26OCT01LAKCOL", KALSHI_KINGS, now)
    await session.commit()


def _games(payload) -> list[str]:
    """In SERVED order — the defect is an order."""
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [f"{e['away_team']} @ {e['home_team']}" for e in payload["results"]]


def _teams(payload) -> list[str]:
    assert "teams" in payload, f"no `teams` key; got {sorted(payload)}"
    return [t["name"] for t in payload["teams"]]


def _futures(payload) -> list[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return sorted(f["name"] for f in payload["futures"])


SF_GAME = f"{DODGERS} @ {SF_GIANTS}"
SPLIT_SF = f"{NINERS} @ {NY_GIANTS}"
KINGS_GAME = f"{KINGS} @ {AVS}"
SPLIT_KINGS = f"{LAKERS} @ {SAC_KINGS}"


@pytest.mark.parametrize("typed", ["sf giants", "SF Giants"])
async def test_sf_giants_cards_the_club_and_leads_with_its_game(maker, search, typed):
    async with maker() as session:
        await _seed(session)

    payload = await search(typed)
    assert _teams(payload) == [SF_GIANTS]
    games = _games(payload)
    assert games[0] == SF_GAME, games
    assert payload["query"] == typed, "`q` is echoed as typed"


async def test_la_kings_cards_the_club_and_sinks_the_lakers_at_sacramento(maker, search):
    async with maker() as session:
        await _seed(session)

    payload = await search("la kings")
    assert _teams(payload) == [KINGS]
    games = _games(payload)
    assert games[0] == KINGS_GAME, games
    # The typed `la` still reaches Kalshi's spelling of the market.
    assert KALSHI_KINGS in _futures(payload)


async def test_la_angels_leads_the_card_with_the_angels(maker, search):
    async with maker() as session:
        await _seed(session)

    payload = await search("la angels")
    teams = _teams(payload)
    assert teams and teams[0] == ANGELS, teams
    assert _games(payload)[0] == f"{ANGELS} @ {MARINERS}"


@pytest.mark.parametrize("typed, club", [("ny rangers", RANGERS), ("la dodgers", DODGERS)])
async def test_other_city_abbreviations_card_their_club(maker, search, typed, club):
    async with maker() as session:
        await _seed(session)

    assert _teams(await search(typed))[:1] == [club]


async def test_a_club_named_with_its_abbreviation_keeps_its_card(maker, search):
    """`la galaxy`: the stored name IS the abbreviation, and still leads."""
    async with maker() as session:
        await _seed(session)

    assert _teams(await search("la galaxy"))[:1] == [GALAXY]


async def test_without_the_rewrite_production_comes_back(maker, search, monkeypatch):
    """The strawman on this rig: the rewrite made a no-op brings back production's
    page — no card for `sf giants`, the 49ers @ New York game first, and the
    Clippers leading `la angels`. Proves the cases above measure the fix."""
    from app.routes import events as ev

    monkeypatch.setattr(ev, "city_abbreviation_query", lambda q: None)
    async with maker() as session:
        await _seed(session)

    sf = await search("sf giants")
    assert _teams(sf) == []
    assert _games(sf)[0] == SPLIT_SF
    assert _games(await search("la kings")).index(SPLIT_KINGS) < _games(
        await search("la kings")
    ).index(KINGS_GAME)
    assert _teams(await search("la angels"))[:1] != [ANGELS]


# ── Negatives (CERT-3880 follow-up `9859-CITY-ABBREVIATION-NEGATIVE-PG-CONTROL`) ──
#
# The rewrite fires on a LEADING table key in front of more words, and nowhere
# else. Each case below asks the route twice on the same rows — once as shipped,
# once with the rewrite made a no-op (production before #9859) — and requires the
# same teams and the same games in the same order. `no` and `ok` are table keys
# (`new orleans`, `oklahoma`) that open ordinary phrases; a New Orleans club and
# an Oklahoma City club are seeded so a rewrite that leaked would have one to card.

PELICANS = "New Orleans Pelicans"
THUNDER = "Oklahoma City Thunder"


async def _seed_with_ambiguous_cities(session):
    from app.models.models import Sport, Team

    await _seed(session)
    nba = (await session.execute(
        Sport.__table__.select().where(Sport.key == "basketball_nba")
    )).first()
    session.add_all([
        Team(sport_id=nba.id, name=PELICANS, abbreviation="NOP"),
        Team(sport_id=nba.id, name=THUNDER, abbreviation="OKC"),
    ])
    await session.commit()


def _page(payload) -> tuple[list[str], list[str]]:
    return _teams(payload), _games(payload)


NEGATIVES = [
    "sf",            # bare: asks for more than one club
    "la",
    "giants sf",     # trailing: the city comes first in a club's name
    "kings la",
    "no kings",      # `no` opens a phrase, not a New Orleans club
    "no hitter",
    "ok computer",   # `ok` opens a phrase, not an Oklahoma club
]


async def test_negatives_serve_the_page_production_served(maker, search, monkeypatch):
    from app.routes import events as ev

    async with maker() as session:
        await _seed_with_ambiguous_cities(session)

    # `no`/`ok` phrases take the rewritten path — the city arm joins their SQL
    # and the scorer sees abbreviated names — so equality below is earned there,
    # not granted by a key that never fires. Bare and trailing inputs never fire.
    fired = {q: ev.city_abbreviation_query(q) for q in NEGATIVES}
    assert fired["no kings"] == "new orleans kings"
    assert fired["ok computer"] == "oklahoma computer"
    assert [q for q, r in fired.items() if r is None] == ["sf", "la", "giants sf", "kings la"]

    shipped = {q: _page(await search(q)) for q in NEGATIVES}
    monkeypatch.setattr(ev, "city_abbreviation_query", lambda q: None)
    before = {q: _page(await search(q)) for q in NEGATIVES}

    assert shipped == before
    for q in ("no kings", "no hitter"):
        assert PELICANS not in shipped[q][0], (q, shipped[q])
    assert THUNDER not in shipped["ok computer"][0], shipped["ok computer"]


async def test_a_rewritten_city_still_cards_its_club_on_this_seed(maker, search):
    """The control for the case above, on the same rows: with the rewrite on,
    `okc thunder` cards the Thunder (and cards nothing with it off), so the
    negatives are not passing because this seed cannot card a rewritten club.
    (`no pelicans` cannot testify: `no` is a stopword, so the typed query alone
    reaches the Pelicans.)"""
    async with maker() as session:
        await _seed_with_ambiguous_cities(session)

    assert _teams(await search("okc thunder"))[:1] == [THUNDER]
