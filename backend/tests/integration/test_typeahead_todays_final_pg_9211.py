"""#9211 — the search dropdown offers a club's game that finished today, beside its next one.

THE DEFECT, production 2026-09-27 21:31Z, `GET /api/events/typeahead?q=chiefs`,
four and a half hours after the Chiefs beat Miami 24–10: the team, *Kansas City
Chiefs at Las Vegas Raiders* (Oct 4), *Exeter Chiefs at Bath* (rugby), then four
futures. The result was not in the list — every arm selects `live`/`scheduled`,
and the or-LAST arm is short-circuited whenever a next fixture exists.

THE TARGET: the next game, then today's final directly behind it (D107: "next
before last"). Yesterday's final stays out.
THE STRAWMAN sets the new arm's limit to 0: the dropdown then reproduces the
production list exactly (no final), so the target case testifies.
THE CONTROL is a club with no game today: its suggestions are identical with and
without the arm.
THE LIVE CASE is a doubleheader: the game being played leads, the game finished
earlier today follows it.

WHY POSTGRES: the arm is a WHERE clause over the Eastern day and the placement
happens before the pool cut; a session double sees neither.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_todays_final_pg_9211.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9211 typeahead real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

NFL = "americanfootball_nfl"
MLB = "baseball_mlb"
RUGBY = "rugbyunion_premiership"

NEXT = "Kansas City Chiefs at Las Vegas Raiders"
TODAYS_FINAL = "Kansas City Chiefs at Miami Dolphins"
YESTERDAYS_FINAL = "Denver Broncos at Kansas City Chiefs"
NAMESAKE = "Exeter Chiefs at Bath"
STEELERS_NEXT = "Pittsburgh Steelers at Cleveland Browns"
RED_SOX_LIVE = "New York Yankees at Boston Red Sox"
RED_SOX_GAME_1 = "Tampa Bay Rays at Boston Red Sox"


def _clock() -> tuple[datetime, datetime]:
    """(now, midnight of now's Eastern day). No branch on the clock (gotcha #44)."""
    now = datetime.now(timezone.utc)
    tz = ZoneInfo("America/New_York")
    start = datetime.combine(now.astimezone(tz).date(), datetime.min.time(), tzinfo=tz)
    return now, start


async def _seed(session):
    from app.models.models import Event, Sport, Team

    now, day_start = _clock()
    # Inside [day_start, now] whatever the hour: the midpoint of today so far.
    earlier_today = day_start + (now - day_start) / 2

    nfl = Sport(key=NFL, name="NFL")
    mlb = Sport(key=MLB, name="MLB")
    rugby = Sport(key=RUGBY, name="Premiership Rugby")
    session.add_all([nfl, mlb, rugby])
    await session.flush()

    # The nickname as an alternate name, as production carries it (teams 560 /
    # 540: `['Chiefs']`, `['Steelers']`): it is what makes `chiefs` resolve the
    # club rather than merely land on it (`query_resolves_team`).
    teams = {
        name: Team(
            sport_id=sport.id,
            name=name,
            abbreviation=abbr,
            alternate_names=[name.rsplit(" ", 1)[-1]] if name != "Boston Red Sox" else ["Red Sox"],
        )
        for name, sport, abbr in [
            ("Kansas City Chiefs", nfl, "KC"),
            ("Las Vegas Raiders", nfl, "LV"),
            ("Miami Dolphins", nfl, "MIA"),
            ("Denver Broncos", nfl, "DEN"),
            ("Pittsburgh Steelers", nfl, "PIT"),
            ("Cleveland Browns", nfl, "CLE"),
            ("Cincinnati Bengals", nfl, "CIN"),
            ("Boston Red Sox", mlb, "BOS"),
            ("New York Yankees", mlb, "NYY"),
            ("Tampa Bay Rays", mlb, "TB"),
        ]
    }
    session.add_all(teams.values())
    await session.flush()

    def _game(sport, away, home, when, status, **kw):
        return Event(
            sport_id=sport.id,
            away_team_name=away,
            home_team_name=home,
            away_team_id=teams[away].id if away in teams else None,
            home_team_id=teams[home].id if home in teams else None,
            commence_time=when,
            status=status,
            **kw,
        )

    session.add_all([
        _game(nfl, "Kansas City Chiefs", "Las Vegas Raiders", now + timedelta(days=5), "scheduled"),
        _game(nfl, "Kansas City Chiefs", "Miami Dolphins", earlier_today, "completed",
              home_score=10, away_score=24),
        _game(nfl, "Denver Broncos", "Kansas City Chiefs", day_start - timedelta(hours=3),
              "completed", home_score=20, away_score=17),
        _game(rugby, "Exeter Chiefs", "Bath", now + timedelta(days=2), "scheduled"),
        # The control: next game this week, last game yesterday, nothing today.
        _game(nfl, "Pittsburgh Steelers", "Cleveland Browns", now + timedelta(days=4), "scheduled"),
        _game(nfl, "Cincinnati Bengals", "Pittsburgh Steelers", day_start - timedelta(hours=2),
              "completed", home_score=30, away_score=27),
        # The doubleheader: game 1 finished earlier today, game 2 is being played.
        _game(mlb, "Tampa Bay Rays", "Boston Red Sox", earlier_today - timedelta(minutes=1),
              "completed", home_score=3, away_score=2),
        _game(mlb, "New York Yankees", "Boston Red Sox", now - timedelta(minutes=30), "live"),
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


async def test_todays_final_sits_right_behind_the_next_game(typeahead):
    """The production specimen: `chiefs` on the afternoon of a 24–10 win."""
    body = await typeahead("chiefs")
    events = _events(body)
    assert TODAYS_FINAL in events, f"today's final is not offered: {events}"
    assert NEXT in events, events
    assert events.index(TODAYS_FINAL) == events.index(NEXT) + 1, events
    assert YESTERDAYS_FINAL not in events, events
    final = next(r for r in body["suggestions"] if r["text"] == TODAYS_FINAL)
    assert final["status"] == "completed", final


async def test_the_strawman_reproduces_production(typeahead, monkeypatch):
    """With the arm fetching nothing, the dropdown is production's list."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_LEAD_TEAM_TODAYS_FINAL_LIMIT", 0)
    events = _events(await typeahead("chiefs"))
    assert TODAYS_FINAL not in events, events
    assert NEXT in events, events


async def test_a_club_with_no_game_today_is_unchanged(typeahead, monkeypatch):
    """The control: `steelers` played yesterday. Same list with and without the arm."""
    from app.routes import events as events_module

    armed = await typeahead("steelers", debug_timing=1)
    assert "lead_team_todays_final_query" in armed["debug_timing"], (
        "the control must exercise the arm, or it testifies to nothing"
    )
    monkeypatch.setattr(events_module, "_LEAD_TEAM_TODAYS_FINAL_LIMIT", 0)
    unarmed = await typeahead("steelers")
    assert [r["text"] for r in armed["suggestions"]] == [
        r["text"] for r in unarmed["suggestions"]
    ]
    assert STEELERS_NEXT in _events(armed), _events(armed)


async def test_a_live_game_leads_and_the_game_finished_today_follows(typeahead):
    """A doubleheader: game 2 is being played, game 1 finished this afternoon."""
    events = _events(await typeahead("red sox"))
    assert RED_SOX_LIVE in events and RED_SOX_GAME_1 in events, events
    assert events.index(RED_SOX_GAME_1) == events.index(RED_SOX_LIVE) + 1, events
