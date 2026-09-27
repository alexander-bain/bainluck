"""#9211 — a club's game that finished today sits right behind its next game.

THE DEFECT, read on production 2026-09-27 21:15Z, `/search?q=chiefs`, two hours
after the Chiefs won 24–10 at Miami: 13 upcoming games (Oct 4 through Jan 10)
printed first and the result was card 14. `status_order` put every upcoming
game above every finished one.

D107 keeps the first slot: the next game still leads. Today's final is second,
the rest of the schedule follows, older finals last.

THE STRAWMAN removes the key: the fixture then reproduces the defect (today's
final below every upcoming game), so the case testifies.
THE CONTROL is a day with no final: the order is exactly the strawman's, so
the key moves nothing else.
THE LEADER CASE: a namesake plays TOMORROW, the club in a week. #8738 already
puts the club's game first; the lifted "next" row must be that one, not the
soonest row — a window ordered by time alone would lift the namesake.

WHY THE ROUTE AND POSTGRES: the key is a `row_number()` window inside the
ORDER BY, the day is `timezone('America/New_York', …)::date`, the club test
reads the route's teams statement. SQLite serves none of it.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9211 today's-"
            "final gate (CI job `search-recall` provides one)"
        ),
    ),
]

QUERY = "chiefs"
CLUB = "Kansas City Chiefs"
NAMESAKE = "Exeter Chiefs"
NFL = "americanfootball_nfl"
RUGBY = "rugbyunion_premiership"

# (label, sport, home, away, Eastern day offset, status). Every kickoff is 13:00
# Eastern on its day (gotcha #44: offset first, then fix the time — no branch).
TODAYS_FINAL = ("todays_final", NFL, "Miami Dolphins", CLUB, 0, "completed")
SCHEDULE = [
    ("next", NFL, "Las Vegas Raiders", CLUB, 7, "scheduled"),
    ("week_2", NFL, "Seattle Seahawks", CLUB, 14, "scheduled"),
    ("week_3", NFL, CLUB, "Denver Broncos", 21, "scheduled"),
    ("last_week", NFL, CLUB, "Indianapolis Colts", -7, "completed"),
]
NAMESAKE_TOMORROW = ("namesake_tomorrow", RUGBY, "Bath", NAMESAKE, 1, "scheduled")


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

    yield async_sessionmaker(engine, expire_on_commit=False)

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

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def _seed(maker, rows, *, namesake_team: bool = False) -> dict[int, str]:
    from app.models.models import Event, Sport, Team

    eastern = ZoneInfo("America/New_York")
    today = datetime.now(timezone.utc).astimezone(eastern).date()
    ids: dict[int, str] = {}
    async with maker() as session:
        sports = {key: Sport(key=key, name=key) for key in (NFL, RUGBY)}
        session.add_all(sports.values())
        await session.flush()
        session.add(Team(sport_id=sports[NFL].id, name=CLUB, abbreviation="KC"))
        if namesake_team:
            session.add(
                Team(sport_id=sports[RUGBY].id, name=NAMESAKE, abbreviation="EXE")
            )
        for label, key, home, away, day, status in rows:
            kickoff = datetime.combine(
                today + timedelta(days=day), time(13, 0), tzinfo=eastern
            ).astimezone(timezone.utc)
            settled = status == "completed"
            row = Event(
                sport_id=sports[key].id,
                home_team_name=home,
                away_team_name=away,
                commence_time=kickoff,
                status=status,
                home_score=10 if settled else None,
                away_score=24 if settled else None,
                completed_at=kickoff + timedelta(hours=3) if settled else None,
            )
            session.add(row)
            await session.flush()
            ids[row.id] = label
        await session.commit()
    return ids


def _labels(payload, ids) -> list[str]:
    """Served game cards, as specimen labels. The key is `results`."""
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [ids[int(e["id"])] for e in payload["results"] if int(e["id"]) in ids]


def _card_leads_with_the_club(payload) -> None:
    teams = [t.get("name") for t in payload.get("teams") or []]
    assert teams and teams[0] == CLUB, (
        f"the specimen needs the TEAMS card to lead with {CLUB}: {teams}"
    )


def _strip_key(monkeypatch) -> None:
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_todays_final_order_key", lambda *_: None)


async def test_todays_final_sits_right_behind_the_next_game(maker, search):
    ids = await _seed(maker, [TODAYS_FINAL, *SCHEDULE])
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    assert _labels(payload, ids) == [
        "next", "todays_final", "week_2", "week_3", "last_week",
    ]


async def test_without_the_key_todays_final_is_buried_under_the_schedule(
    maker, search, monkeypatch,
):
    """Strawman: the fixture reproduces #9211 with the key removed."""
    _strip_key(monkeypatch)
    ids = await _seed(maker, [TODAYS_FINAL, *SCHEDULE])
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    assert _labels(payload, ids) == [
        "next", "week_2", "week_3", "todays_final", "last_week",
    ]


async def test_a_day_without_a_final_orders_exactly_as_before(
    maker, search, monkeypatch,
):
    """The control: no final today, so the key must reproduce the old order."""
    ids = await _seed(maker, SCHEDULE)
    with_key = _labels(await search(QUERY), ids)
    _strip_key(monkeypatch)
    without_key = _labels(await search(QUERY), ids)
    assert with_key == without_key == ["next", "week_2", "week_3", "last_week"]


async def test_the_lifted_next_game_is_the_clubs_not_the_soonest_namesake(
    maker, search,
):
    """#8738 orders the upcoming tier by the card's leader, so "next" is the
    club's game in a week, not the namesake's game tomorrow."""
    ids = await _seed(
        maker, [TODAYS_FINAL, *SCHEDULE, NAMESAKE_TOMORROW], namesake_team=True
    )
    payload = await search(QUERY)
    _card_leads_with_the_club(payload)
    labels = _labels(payload, ids)
    assert labels[:2] == ["next", "todays_final"], labels
    assert sorted(labels) == sorted(ids.values()), labels
