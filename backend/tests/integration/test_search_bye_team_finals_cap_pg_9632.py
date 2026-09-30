"""#9632 — a club with nothing left to play keeps only its latest finals on page one.

THE DEFECT, read on production 2026-09-29 ~14:40Z, `/search?q=dodgers` at 390px,
the first day of MLB's postseason: the Dodgers have a first-round bye, so every
game in the 30-day window is a final, and page one opened with 23 of them
(Sep 27 back to Sep 4). The only live questions — World Series (30%) and NL
Champion (42%) — sat below all of them, ~5,500px down. `brewers` the same.

THE SHIP: when a team query's games are ALL finished and the club has live
futures, page one serves the latest `_SEARCH_BYE_FINALS_CAP` finals and page two
starts right after them — every final still reachable, none twice.

THE STRAWMAN disarms the probe: page one then serves every final (the defect).
THE CONTROLS: an upcoming game (`chiefs`), no futures at all, a game-linked
`open` market (Kalshi leaves settled game markets open — gotcha #33), and a
1%-floor outcome each leave the page exactly as it was.

WHY THE ROUTE AND POSTGRES: the probe reads the route's own `event_conditions`
(full-text recall) and the teams statement, then cuts the page with them.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9632 bye-finals "
            "gate (CI job `search-recall` provides one)"
        ),
    ),
]

QUERY = "dodgers"
CLUB = "Los Angeles Dodgers"
MLB = "baseball_mlb"
OPPONENTS = [
    "San Francisco Giants", "Colorado Rockies", "Arizona Diamondbacks",
    "San Diego Padres", "Seattle Mariners", "Chicago Cubs",
    "Cincinnati Reds", "St. Louis Cardinals",
]
FINALS = len(OPPONENTS)  # days -1 .. -8, newest first


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        # Leave nothing behind: the `search-recall` database is shared with the next suite.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and the real database.

    Redis raises so the full-response cache is a miss, as in the sibling gates.
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

            async def _search(q: str, page: int = 1) -> dict:
                resp = await http.get(
                    "/api/events/search", params={"q": q, "page": page}
                )
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def _seed(
    maker,
    *,
    upcoming: bool = False,
    futures: str | None = "season",
    probability: float = 0.30,
) -> dict[int, str]:
    """Eight Dodgers finals, newest first as `final_1` .. `final_8`.

    `futures`: "season" = an open World Series market (no game) carrying the
    club's outcome; "game" = the same outcome on an `open` market tied to the
    newest final; None = no market at all. `upcoming` adds tomorrow's game.
    """
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team

    eastern = ZoneInfo("America/New_York")
    today = datetime.now(timezone.utc).astimezone(eastern).date()
    ids: dict[int, str] = {}
    async with maker() as session:
        mlb = Sport(key=MLB, name="MLB")
        session.add(mlb)
        await session.flush()
        club = Team(sport_id=mlb.id, name=CLUB, abbreviation="LAD")
        session.add(club)
        await session.flush()

        # Every kickoff is 13:00 Eastern on its day, so a past day is past and a
        # future day is future at any hour this runs (gotcha #44).
        rows = [
            (f"final_{n}", OPPONENTS[n - 1], -n, "completed")
            for n in range(1, FINALS + 1)
        ]
        if upcoming:
            rows.append(("next", "Philadelphia Phillies", 1, "scheduled"))
        for label, opponent, day, status in rows:
            kickoff = datetime.combine(
                today + timedelta(days=day), time(13, 0), tzinfo=eastern
            ).astimezone(timezone.utc)
            settled = status == "completed"
            row = Event(
                sport_id=mlb.id,
                home_team_name=CLUB,
                away_team_name=opponent,
                commence_time=kickoff,
                status=status,
                home_score=5 if settled else None,
                away_score=2 if settled else None,
                completed_at=kickoff + timedelta(hours=3) if settled else None,
            )
            session.add(row)
            await session.flush()
            ids[row.id] = label

        if futures is not None:
            newest = next(i for i, label in ids.items() if label == "final_1")
            market = FuturesMarket(
                source="kalshi",
                external_id="KXMLB-26-9632",
                name="MLB World Series Champion 2026",
                status="open",
                resolution_date=datetime.now(timezone.utc) + timedelta(days=30),
                llm_sport_category="baseball",
                category="championship",
                market_tier=1,
                event_id=newest if futures == "game" else None,
            )
            session.add(market)
            await session.flush()
            session.add(FuturesOutcome(
                market_id=market.id, name=CLUB, team_id=club.id,
                current_probability=probability,
                external_id=f"{market.external_id}:LAD",
            ))
        await session.commit()
    return ids


def _labels(payload, ids) -> list[str]:
    """Served game cards, as specimen labels. The key is `results`."""
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [ids[int(e["id"])] for e in payload["results"] if int(e["id"]) in ids]


def _card_leads_with_the_club(payload) -> None:
    teams = [t.get("name") for t in payload.get("teams") or []]
    assert teams and teams[0] == CLUB, (
        f"the specimen needs the TEAMS card to lead with {CLUB} — the probe reads "
        f"that club's outcomes, so without it this tests nothing: {teams}"
    )


ALL_FINALS = [f"final_{n}" for n in range(1, FINALS + 1)]


async def test_a_bye_club_keeps_its_latest_finals_and_page_two_holds_the_rest(
    maker, search,
):
    from app.routes.events import _SEARCH_BYE_FINALS_CAP as CAP

    ids = await _seed(maker)
    first = await search(QUERY)
    _card_leads_with_the_club(first)

    assert _labels(first, ids) == ALL_FINALS[:CAP], _labels(first, ids)
    pagination = first["pagination"]
    assert pagination["total_results"] == FINALS, (
        "the games header must still count every final", pagination,
    )
    assert pagination["total_pages"] == 2 and pagination["has_next"], pagination

    second = await search(QUERY, page=2)
    assert _labels(second, ids) == ALL_FINALS[CAP:], (
        "page two must start right after page one — no final skipped, none twice",
        _labels(second, ids),
    )
    assert second["pagination"]["total_pages"] == 2
    assert not second["pagination"]["has_next"]
    assert second["pagination"]["has_prev"]


async def test_strawman_without_the_probe_every_final_buries_the_futures(
    maker, search, monkeypatch,
):
    """The fixture reproduces #9632 when the cap is disarmed."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_search_bye_team_ids", lambda *_: [])
    ids = await _seed(maker)
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    assert _labels(payload, ids) == ALL_FINALS
    assert payload["pagination"]["total_pages"] == 1


async def test_control_an_upcoming_game_leaves_the_page_as_it_was(maker, search):
    """`chiefs`: a club with a game to play is not a bye club."""
    ids = await _seed(maker, upcoming=True)
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    labels = _labels(payload, ids)
    assert sorted(labels) == sorted(["next", *ALL_FINALS]), labels
    assert labels[0] == "next", labels
    assert payload["pagination"]["total_pages"] == 1


async def test_control_no_futures_leaves_the_page_as_it_was(maker, search):
    ids = await _seed(maker, futures=None)
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    assert _labels(payload, ids) == ALL_FINALS
    assert payload["pagination"]["total_pages"] == 1


async def test_control_an_open_game_market_is_not_a_futures_question(maker, search):
    """Gotcha #33: a settled game's Kalshi market stays `open`; it arms nothing."""
    ids = await _seed(maker, futures="game")
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    assert _labels(payload, ids) == ALL_FINALS
    assert payload["pagination"]["total_pages"] == 1


async def test_control_a_sub_one_percent_outcome_is_not_a_live_question(
    maker, search,
):
    ids = await _seed(maker, probability=0.005)
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    assert _labels(payload, ids) == ALL_FINALS
    assert payload["pagination"]["total_pages"] == 1
