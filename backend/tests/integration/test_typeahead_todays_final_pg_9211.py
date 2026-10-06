"""#9211 — the search dropdown offers a club's game that finished today, beside its next one.

THE DEFECT, production 2026-09-27 21:31Z, `GET /api/events/typeahead?q=chiefs`,
four and a half hours after the Chiefs beat Miami 24–10: the team, *Kansas City
Chiefs at Las Vegas Raiders* (Oct 4), *Exeter Chiefs at Bath* (rugby), then four
futures. The result was not in the list — every arm selects `live`/`scheduled`,
and the or-LAST arm is short-circuited whenever a next fixture exists.

THE TARGET: the next game, then today's final directly behind it (D107: "next
before last"). #10581 falls back to one latest result outside the recent window.
#10186 opened the
window at the earlier of Eastern midnight and now - 18 h, so last night's game
is offered the morning after.
THE STRAWMAN disables the complete final selector: the dropdown reproduces the
production list exactly (no final), so the target case testifies.
THE CONTROL has no final in the supported lookback: suggestions are identical with and
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

    from app.routes.events import _recent_final_window_start

    now, day_start = _clock()
    window_start = _recent_final_window_start(now)
    # Inside [day_start, now] whatever the hour: the midpoint of today so far.
    earlier_today = day_start + (now - day_start) / 2
    # Doubleheader game 1, before `earlier_today` and still inside today. It was
    # `earlier_today - 1 min`, which crosses `day_start` for the first ~2 minutes
    # of the Eastern day (ux, CI at 04:00:01Z 10/1): the arm then rightly drops it.
    earliest_today = day_start + (now - day_start) / 3

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
            ("Milwaukee Brewers", mlb, "MIL"),
            ("San Diego Padres", mlb, "SD"),
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
        # #10186: "yesterday" means BEFORE THE WINDOW, which since #10186 opens at
        # the earlier of Eastern midnight and now - 18 h. Seeded from the route's
        # own window start so it stays outside at any hour; `day_start - 3 h`
        # (9 PM ET) was inside the window until 3 PM ET (gotcha #44).
        _game(nfl, "Denver Broncos", "Kansas City Chiefs", window_start - timedelta(hours=3),
              "completed", home_score=20, away_score=17),
        _game(rugby, "Exeter Chiefs", "Bath", now + timedelta(days=2), "scheduled"),
        # The control: next game this week, last game before the window, nothing in it.
        _game(nfl, "Pittsburgh Steelers", "Cleveland Browns", now + timedelta(days=4), "scheduled"),
        _game(nfl, "Cincinnati Bengals", "Pittsburgh Steelers", window_start - timedelta(hours=2),
              "completed", home_score=30, away_score=27),
        # The doubleheader: game 1 finished earlier today, game 2 is being played.
        _game(mlb, "Tampa Bay Rays", "Boston Red Sox", earliest_today,
              "completed", home_score=3, away_score=2),
        # #9226: scored, so the rule that a live row carries no score testifies.
        _game(mlb, "New York Yankees", "Boston Red Sox", now - timedelta(minutes=30), "live",
              home_score=1, away_score=0),
    ])
    # #10581 controlled route fixture: identity/result are retained; kickoff is
    # deliberately synthetic, outside any recent window, not the actual game time.
    session.add_all(
        [
            _game(
                mlb,
                "Milwaukee Brewers",
                "San Diego Padres",
                now + timedelta(hours=22),
                "scheduled",
            ),
            _game(
                mlb,
                "San Diego Padres",
                "Milwaukee Brewers",
                now - timedelta(days=2),
                "completed",
                id=15323985,
                home_score=4,
                away_score=3,
            ),
        ]
    )
    await session.flush()
    final = await session.get(Event, 15323985)
    assert final.home_team_id == teams["Milwaukee Brewers"].id
    assert final.away_team_id == teams["San Diego Padres"].id
    assert final.home_team_id is not None and final.away_team_id is not None
    await session.commit()
    return {
        "brewers": teams["Milwaukee Brewers"].id,
        "padres": teams["San Diego Padres"].id,
    }


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
        seeded_ids = await _seed(session)

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

                _do.seeded_ids = seeded_ids
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

    async def no_finals(*args):
        return []

    monkeypatch.setattr(
        events_module, "_lead_team_finals_with_latest_fallback", no_finals
    )
    events = _events(await typeahead("chiefs"))
    assert TODAYS_FINAL not in events, events
    assert NEXT in events, events


async def test_a_club_without_a_supported_final_is_unchanged(typeahead, monkeypatch):
    """Raiders have a next fixture but no final; the complete selector is inert."""
    from app.routes import events as events_module

    armed = await typeahead("raiders", debug_timing=1)
    assert "lead_team_todays_final_query" in armed["debug_timing"]

    async def no_finals(*args):
        return []

    monkeypatch.setattr(
        events_module, "_lead_team_finals_with_latest_fallback", no_finals
    )
    unarmed = await typeahead("raiders")
    assert [r["text"] for r in armed["suggestions"]] == [
        r["text"] for r in unarmed["suggestions"]
    ]
    assert NEXT in _events(armed)


STEELERS_LAST_NIGHT = "Cincinnati Bengals at Pittsburgh Steelers"


async def test_latest_final_beyond_the_recent_window_is_offered(typeahead, monkeypatch):
    """#10581 extends the old #10186 recent-only rule without widening it."""
    from app.routes import events as events_module

    async def recent_only(db, team_id, name, now):
        return (
            (
                await db.execute(
                    events_module._lead_team_todays_final_query(team_id, name, now)
                )
            )
            .scalars()
            .all()
        )

    events = _events(await typeahead("steelers"))
    assert STEELERS_LAST_NIGHT in events
    assert events.index(STEELERS_LAST_NIGHT) == events.index(STEELERS_NEXT) + 1
    monkeypatch.setattr(
        events_module, "_lead_team_finals_with_latest_fallback", recent_only
    )
    before = _events(await typeahead("steelers"))
    assert STEELERS_LAST_NIGHT not in before
    assert STEELERS_NEXT in before


async def test_named_brewers_final_survives_final_http_composition(typeahead, monkeypatch):
    """Real HTTP+PG, exact screenshot query; no installed-phone cause claim."""
    from app.routes import events as events_module

    reached = []
    selector = events_module._lead_team_finals_with_latest_fallback

    async def record_resolved_team(db, team_id, team_name, now):
        reached.append((team_id, team_name))
        return await selector(db, team_id, team_name, now)

    monkeypatch.setattr(
        events_module, "_lead_team_finals_with_latest_fallback", record_resolved_team
    )
    body = await typeahead("brewers")
    assert reached == [(typeahead.seeded_ids["brewers"], "Milwaukee Brewers")]
    rows = body["suggestions"]
    team_rows = [row for row in rows if row["type"] == "team" and row["text"] == "Milwaukee Brewers"]
    assert len(team_rows) == 1
    assert team_rows[0]["team_id"] == typeahead.seeded_ids["brewers"]
    next_title = "Milwaukee Brewers at San Diego Padres"
    final_title = "San Diego Padres at Milwaukee Brewers"
    events = _events(body)
    assert next_title in events and final_title in events, events
    assert events.index(final_title) == events.index(next_title) + 1
    final = next(row for row in rows if row["text"] == final_title)
    assert final["status"] == "completed"
    assert final["event_id"] == 15323985
    assert (final["away_score"], final["home_score"]) == (3, 4)


async def test_a_live_game_leads_and_the_game_finished_today_follows(typeahead):
    """A doubleheader: game 2 is being played, game 1 finished this afternoon."""
    events = _events(await typeahead("red sox"))
    assert RED_SOX_LIVE in events and RED_SOX_GAME_1 in events, events
    assert events.index(RED_SOX_GAME_1) == events.index(RED_SOX_LIVE) + 1, events
