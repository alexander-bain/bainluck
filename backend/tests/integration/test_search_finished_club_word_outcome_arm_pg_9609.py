"""#9609 — `rays` / `mets` show the club's markets, not Senate races and Demon Slayer.

THE DEFECT, read on production 2026-09-29 11:3xZ (`81d59f83`): `/search?q=rays`
FUTURES & MARKETS served five of ten rows through G(rays)on — Alaska Senate,
Amapá Senate 1st/2nd, two "Who will Bernie endorse?" — and `/search?q=mets` four
of six through Ki(mets)u no Yaiba and E(mets) Ihor. None of those NAMES holds the
word; the futures OUTCOME arm reached them through `ILIKE '%rays%'`. #9292 sank
them below the club's own option rows, but there were not enough real rows to
fill ten, so they still filled the page.

Now, when the query is a whole word of a club the page's own teams read returned
(`_is_finished_club_word`), the outcome arm is whole word + expansion — the arm
#9306 serves a round word. /typeahead was already clean on these queries and is
not touched.

THE STRAWMAN removes the rule: the fixture then serves both collision markets.
THE CONTROLS: `heat` keeps its substring arm because a club word it STARTS
exists (Flackwell Heath FC — the reader may still be typing), and `grayson`
still reaches the Senate market through its outcome as a whole word.

WHY THE ROUTE AND POSTGRES: the whole-word arm is a `~*` POSIX regex with
`[[:alnum:]]`, the teams read is the route's own statement, and the arm is wired
inside the route body. SQLite serves neither.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9609 finished-"
            "club-word gate (CI job `search-recall` provides one)"
        ),
    ),
]

ALCS_MARKET = "MLB Playoffs: Team to advance to ALCS"
SENATE = "Alaska Senate Election Winner"
ANIMATED = "PGA Award for Best Animated Theatrical Motion Picture?"
SECRETARY = "South Dakota Secretary of State winner?"

# (external_id, market name, outcome names) — production's own spellings.
SEEDS = [
    ("KXMLBALCS-26", ALCS_MARKET, ["Tampa Bay Rays", "New York Mets"]),
    ("KXSENATEAK-26", SENATE, ["Alan Grayson", "Dan Sullivan"]),
    ("KXPGAANIM-26", ANIMATED, ["Demon Slayer: Kimetsu no Yaiba Infinity Castle", "Zootopia 2"]),
    ("KXSOSSD-26", SECRETARY, ["Heather Hill", "Tom Holmes"]),
]

# (sport key, club name, abbreviation) — the rows the page's teams read returns.
CLUBS = [
    ("baseball_mlb", "Tampa Bay Rays", "TB"),
    ("baseball_mlb", "New York Mets", "NYM"),
    ("basketball_nba", "Miami Heat", "MIA"),
    ("soccer_fa_cup", "Flackwell Heath FC", "FLA"),
]

# (sport key, home, away) — each club has a game, as on production: the events
# rail is NOT empty, so the empty-rail rescue (#5773's `_resolved_teams`) never
# runs and the arm under test is the one that decides.
GAMES = [
    ("baseball_mlb", "Tampa Bay Rays", "Philadelphia Phillies"),
    ("baseball_mlb", "New York Mets", "Washington Nationals"),
    ("basketball_nba", "Miami Heat", "Boston Celtics"),
]


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for external_id, name, outcomes in SEEDS:
            market = FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=name,
                status="open",
                # The route filters `resolution_date IS NULL OR >= now()`.
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
            session.add(market)
            await session.flush()
            for outcome in outcomes:
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{external_id}:{outcome}",
                        name=outcome,
                        current_probability=0.5,
                    )
                )
        sports: dict[str, Sport] = {}
        for sport_key, club, abbreviation in CLUBS:
            if sport_key not in sports:
                sports[sport_key] = Sport(key=sport_key, name=sport_key)
                session.add(sports[sport_key])
                await session.flush()
            session.add(
                Team(sport_id=sports[sport_key].id, name=club, abbreviation=abbreviation)
            )
        for sport_key, home, away in GAMES:
            session.add(
                Event(
                    sport_id=sports[sport_key].id,
                    home_team_name=home,
                    away_team_name=away,
                    commence_time=datetime.now(timezone.utc) + timedelta(days=1),
                    status="scheduled",
                )
            )
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and the real database.

    Redis raises so the response cache misses, as in the sibling gates.
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

            async def _search(q: str, rail: bool = True) -> list[str]:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                payload = resp.json()
                assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
                # The production shape, asserted: the club's game is on the rail.
                games = payload.get("results") or []
                assert games or not rail, f"{q!r}: no games — the empty-rail rescue decides, not #9609"
                return [f.get("name") for f in payload["futures"]]

            yield _search

    app.dependency_overrides.clear()


def _disarm(monkeypatch) -> None:
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_is_finished_club_word", lambda *_a: False)


async def test_rays_serves_the_club_market_and_no_grayson(search):
    names = await search("rays")
    assert ALCS_MARKET in names, (
        f"the Rays' own market must still be served, or this tests nothing: {names}"
    )
    assert SENATE not in names, f"`rays` still reaches a market through G(rays)on: {names}"


async def test_mets_serves_the_club_market_and_no_kimetsu(search):
    names = await search("mets")
    assert ALCS_MARKET in names, (
        f"the Mets' own market must still be served, or this tests nothing: {names}"
    )
    assert ANIMATED not in names, f"`mets` still reaches a market through Ki(mets)u: {names}"


async def test_without_the_rule_the_collisions_come_back(search, monkeypatch):
    """Strawman: the fixture reproduces #9609 with the rule removed."""
    _disarm(monkeypatch)
    assert SENATE in await search("rays")
    assert ANIMATED in await search("mets")


async def test_a_club_word_the_term_only_starts_keeps_the_substring_arm(search):
    """Control: `heat` is a whole word of Miami Heat but the START of Flackwell
    Heath FC, so the reader may still be typing and Heather keeps matching."""
    names = await search("heat")
    assert SECRETARY in names, names


async def test_the_whole_word_still_reaches_the_outcome(search):
    """Control: typing the surname finds the Senate market by its outcome."""
    names = await search("grayson", rail=False)
    assert SENATE in names, names
