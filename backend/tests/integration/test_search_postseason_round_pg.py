"""`wild card` finds this week's MLB Wild Card games and series markets.

THE DEFECT, read on production Monday 2026-09-28 07:5xZ: `/search?q=wild card`
served ZERO games with four MLB Wild Card series opening the next day, and its
futures led with the NCAAB and NCAAF championship markets — `wild` inside
Wild·cats, `card` inside Card·inals, two outcome names. No stored text names
the round; Kalshi's tickers do (`_POSTSEASON_ROUND_ALIASES`).

THE STRAWMAN empties the round map: `wild card` goes back to no games and
college futures on top.
THE CONTROLS: the two clubs' regular-season meeting (same ticker pair, played
before the series was listed) is not a Wild Card game; a team word beside the
phrase narrows it; `red sox` still reaches that regular-season game by name.

WHY THE ROUTE AND POSTGRES: the rule is a correlated EXISTS with `substr` /
`concat` over two aliases of `futures_markets`, wired inside two route bodies.

Times are offsets from now, never branches (clock_sweep rule).
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres postseason-round "
            "gate (CI job `search-recall` provides one)"
        ),
    ),
]

MLB = "baseball_mlb"

# (away, home) -> (ticker team pair, kickoff hours from now)
WILD_CARD_GAMES = {
    ("Boston Red Sox", "New York Yankees"): ("BOSNYY", 30),
    ("Chicago Cubs", "San Diego Padres"): ("CHCSD", 32),
    ("Philadelphia Phillies", "Atlanta Braves"): ("PHIATL", 20),
}
# Same pair as the Red Sox series, played BEFORE the series was listed.
REGULAR_SEASON = ("Boston Red Sox", "New York Yankees")
# An MLB game with a linked game ticker and no series of its round.
NOT_IN_THE_ROUND = ("Seattle Mariners", "Texas Rangers")

SERIES_NAMES = {
    "BOSNYY": "Boston vs New York Y",
    "CHCSD": "Chicago C vs San Diego",
    "PHIATL": "Philadelphia vs Atlanta",
}
COLLEGE_MARKETS = {
    "NCAAB Championship Winner": ("Kentucky Wildcats", "Louisville Cardinals"),
    "NCAAF Championship Winner": ("Arizona Wildcats", "Stanford Cardinal"),
}


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.now(timezone.utc)
    listed = now - timedelta(days=3)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        mlb = Sport(key=MLB, name="MLB", group="Baseball", active=True)
        session.add(mlb)
        await session.flush()

        def game(away, home, start, status, game_ticker, n):
            ev = Event(
                sport_id=mlb.id,
                external_id=f"round-{n}",
                home_team_name=home,
                away_team_name=away,
                commence_time=start,
                status=status,
                # A finished game with no score is a blank card search declines.
                home_score=5 if status == "completed" else None,
                away_score=3 if status == "completed" else None,
            )
            session.add(ev)
            return ev, game_ticker

        rows = []
        for n, ((away, home), (pair, hours)) in enumerate(WILD_CARD_GAMES.items()):
            rows.append(game(
                away, home, now + timedelta(hours=hours), "scheduled",
                f"KXMLBGAME-26SEP292000{pair}", n,
            ))
        rows.append(game(
            *REGULAR_SEASON, now - timedelta(days=6), "completed",
            "KXMLBGAME-26SEP221905BOSNYY", 10,
        ))
        rows.append(game(
            *NOT_IN_THE_ROUND, now + timedelta(hours=26), "scheduled",
            "KXMLBGAME-26SEP292100SEATEX", 11,
        ))
        await session.flush()
        for ev, ticker in rows:
            session.add(FuturesMarket(
                source="kalshi", external_id=ticker, event_id=ev.id,
                name=f"Game 1: {ev.away_team_name} vs {ev.home_team_name}",
                status="open", resolution_date=now + timedelta(days=5),
            ))

        for pair, label in SERIES_NAMES.items():
            for family, title in (
                ("KXMLBSERIES", "Series Winner"),
                ("KXMLBSERIESGAMES", "Series Total Games"),
            ):
                series = FuturesMarket(
                    source="kalshi", external_id=f"{family}-26{pair}WC",
                    name=f"{title}: {label}", status="open",
                    resolution_date=now + timedelta(days=30), created_at=listed,
                )
                session.add(series)
                await session.flush()
                for outcome, p in (("Yes", 0.55), ("No", 0.45)):
                    session.add(FuturesOutcome(
                        market_id=series.id, name=outcome, current_probability=p,
                        external_id=f"{series.external_id}:{outcome}",
                    ))

        for i, (name, outcomes) in enumerate(COLLEGE_MARKETS.items()):
            market = FuturesMarket(
                source="kalshi", external_id=f"KXNCAACHAMP-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=150),
                market_tier=1,
            )
            session.add(market)
            await session.flush()
            for outcome in outcomes:
                session.add(FuturesOutcome(
                    market_id=market.id, external_id=f"{market.external_id}:{outcome}",
                    name=outcome, current_probability=0.3,
                ))
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def get(maker):
    """`GET` either screen against the real app and the real database."""
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

            async def _get(path: str, q: str) -> dict:
                resp = await http.get(f"/api/events/{path}", params={"q": q})
                assert resp.status_code == 200, f"{path} {q!r} -> {resp.status_code}"
                return resp.json()

            yield _get

    app.dependency_overrides.clear()


ALL_GAMES = set(WILD_CARD_GAMES) | {REGULAR_SEASON, NOT_IN_THE_ROUND}


def _search_games(payload: dict) -> list[tuple[str, str]]:
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [(r["away_team"], r["home_team"]) for r in payload["results"]]


def _search_futures(payload: dict) -> list[str]:
    return [f["name"] for f in payload.get("futures") or []]


def _typeahead_games(payload: dict) -> set[tuple[str, str]]:
    assert "suggestions" in payload, f"no `suggestions` key; got {sorted(payload)}"
    by_text = {f"{a} at {h}": (a, h) for a, h in ALL_GAMES}
    return {
        by_text[s["text"]]
        for s in payload["suggestions"]
        if s.get("type") == "event" and s.get("text") in by_text
    }


def _typeahead_futures(payload: dict) -> list[str]:
    return [
        s["text"] for s in payload["suggestions"]
        if s.get("type") not in ("event", "team")
    ]


@pytest.mark.parametrize("q", ["wild card", "Wild Card", "wildcard", "mlb wild card"])
async def test_search_serves_the_rounds_games_and_nothing_else(get, q):
    games = _search_games(await get("search", q))
    assert set(games) == set(WILD_CARD_GAMES), (
        f"{q!r} should serve exactly the Wild Card games: {games}"
    )


@pytest.mark.parametrize("q", ["wild card", "wildcard"])
async def test_search_futures_lead_with_the_series_not_college(get, q):
    futures = _search_futures(await get("search", q))
    series = {f"{t}: {label}" for label in SERIES_NAMES.values()
              for t in ("Series Winner", "Series Total Games")}
    assert futures, f"{q!r} served no futures"
    head = futures[: len(series)]
    assert set(head) == series, f"{q!r} futures head is not the round's series: {futures}"


@pytest.mark.parametrize("q", ["wild card", "wildcard"])
async def test_the_dropdown_offers_the_rounds_games(get, q):
    payload = await get("typeahead", q)
    games = _typeahead_games(payload)
    assert games and games <= set(WILD_CARD_GAMES), (
        f"typeahead {q!r} offered {games}"
    )
    assert NOT_IN_THE_ROUND not in games


async def test_a_team_word_narrows_the_round(get):
    """Control: `yankees wild card` is the Yankees' series, not all three."""
    games = _search_games(await get("search", "yankees wild card"))
    assert games == [("Boston Red Sox", "New York Yankees")], games


async def test_the_regular_season_meeting_is_not_a_wild_card_game(get):
    """Control: same ticker pair, played before the series was listed.

    It is still found by the clubs' names, so its absence from `wild card` is
    the round rule refusing it, not the fixture failing to reach it.
    """
    by_name = _search_games(await get("search", "red sox"))
    assert by_name.count(REGULAR_SEASON) == 2, by_name  # regular season + WC game 1
    games = _search_games(await get("search", "wild card"))
    assert games.count(REGULAR_SEASON) == 1, games


async def test_without_the_round_map_wild_card_is_the_old_answer(get, monkeypatch):
    """Strawman: the fixture reproduces production's empty games list."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_POSTSEASON_ROUND_ALIASES", {})
    payload = await get("search", "wild card")
    assert _search_games(payload) == []
    futures = _search_futures(payload)
    assert not {n for n in futures if n.startswith("Series ")}, futures
    assert set(futures) == set(COLLEGE_MARKETS), futures


# #9333 dropdown half, production 2026-09-28 on `7cb0bae4`: both typed words sit
# inside these NAMES (Seyboth `Wild` · Bos`card`in, `Wildcard` Gaming), so the
# dropdown led with them and the round's series came fifth.
NAME_COLLISIONS = (
    ("polymarket", "Curitiba: Thiago Seyboth Wild vs Pedro Boscardin Dias", 90_000),
    ("polymarket", "Wildcard Gaming vs. M80", 40_000),
)


async def _add_name_collisions(maker) -> set[str]:
    from app.models.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)
    async with maker() as session:
        for i, (source, name, volume) in enumerate(NAME_COLLISIONS):
            market = FuturesMarket(
                source=source, external_id=f"collision-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=2),
                market_tier=1, volume=volume,
            )
            session.add(market)
            await session.flush()
            session.add(FuturesOutcome(
                market_id=market.id, external_id=f"collision-{i}:yes",
                name="Yes", current_probability=0.6,
            ))
        await session.commit()
    return {name for _source, name, _volume in NAME_COLLISIONS}


@pytest.mark.parametrize("q", ["wild card", "wildcard"])
async def test_the_dropdown_leads_with_the_series_not_name_collisions(get, maker, q):
    collisions = await _add_name_collisions(maker)
    futures = _typeahead_futures(await get("typeahead", q))
    assert futures and futures[0].startswith("Series "), (
        f"typeahead {q!r} futures do not lead with the round's series: {futures}"
    )
    seen_collision = False
    for name in futures:
        seen_collision = seen_collision or name in collisions
        assert not (seen_collision and name.startswith("Series ")), (
            f"typeahead {q!r} put a name collision above a series market: {futures}"
        )


async def test_the_collisions_still_answer_their_own_names(get, maker):
    """Control: the partition orders; it hides nothing from a query about them."""
    await _add_name_collisions(maker)
    futures = _typeahead_futures(await get("typeahead", "wildcard gaming"))
    assert "Wildcard Gaming vs. M80" in futures, futures


async def test_without_the_round_partition_the_collisions_lead(get, maker, monkeypatch):
    """Strawman: the fixture reproduces production's dropdown order."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_postseason_round_series_first", lambda markets, _terms: markets
    )
    monkeypatch.setattr(
        events_module, "_futures_postseason_round_order_key", lambda _terms: None
    )
    collisions = await _add_name_collisions(maker)
    futures = _typeahead_futures(await get("typeahead", "wild card"))
    assert futures and futures[0] in collisions, futures
