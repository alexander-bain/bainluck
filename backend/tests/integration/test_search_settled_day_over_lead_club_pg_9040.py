"""#9040 — a finished game from the newest day leads, whichever club the card chose.

THE DEFECT, read on production 2026-09-27 03:50Z, `/search?q=texas`, the night
Texas beat Tennessee 20–17: the TEAMS card led with Texas Rangers (MLB), and
#8738's lead key ordered EVERY status tier by it, so all 27 Rangers finals in
the 30-day window sorted above every other club's result. Texas @ Tennessee
was page 3, row 2.

Finished games ordered `status_order, lead_key, search_rank DESC, time DESC`.
Now the finished tier's Eastern DAY sits above the lead key: the newest day
first, the card's leader first within it.

THE STRAWMAN removes the new key: the fixture then reproduces the defect (the
leader's older finals above the namesake's newest one), so the case testifies.
THE CONTROL is the upcoming tier: #8738 still orders it (the leader's game
tomorrow above the namesake's), so the key cannot pass by reaching the
upcoming games or by disarming #8738.

A final where both teams carry the word (`Texas State @ Texas Longhorns`)
out-ranks on `ts_rank_cd`; it now sorts by its day like any other final.

WHY THE ROUTE AND POSTGRES: the lead key reads the teams statement the route
runs first, the day is `timezone('America/New_York', …)::date`, and the rank is
`ts_rank_cd`. SQLite serves none of it.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9040 settled-"
            "day gate (CI job `search-recall` provides one)"
        ),
    ),
]

QUERY = "texas"
LEAD = "Texas Rangers"
NAMESAKE = "Texas Longhorns"
MLB = "baseball_mlb"
NCAAF = "americanfootball_ncaaf"

# (label, sport, home, away, Eastern day offset, status). Every kickoff is 13:00
# Eastern on its day, so a past day is past and a future day is future at any
# hour this runs (gotcha #44: offset first, then fix the time — no branch).
SPECIMEN = [
    ("lead_last_night", MLB, "Minnesota Twins", LEAD, -1, "completed"),
    ("namesake_last_night", NCAAF, "Tennessee Volunteers", NAMESAKE, -1, "completed"),
    ("lead_2", MLB, "Minnesota Twins", LEAD, -2, "completed"),
    ("lead_3", MLB, LEAD, "New York Mets", -3, "completed"),
    ("lead_4", MLB, LEAD, "New York Mets", -4, "completed"),
    ("lead_5", MLB, LEAD, "Toronto Blue Jays", -5, "completed"),
    ("both_named", NCAAF, NAMESAKE, "Texas State Bobcats", -8, "completed"),
    ("lead_next", MLB, "Minnesota Twins", LEAD, 1, "scheduled"),
    ("namesake_next", NCAAF, "Oklahoma Sooners", NAMESAKE, 2, "scheduled"),
]
SETTLED_ORDER = [
    "lead_last_night", "namesake_last_night",
    "lead_2", "lead_3", "lead_4", "lead_5",
    "both_named",
]
UPCOMING_ORDER = ["lead_next", "namesake_next"]


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


async def _seed(maker) -> dict[int, str]:
    from app.models.models import Event, Sport, Team

    eastern = ZoneInfo("America/New_York")
    today = datetime.now(timezone.utc).astimezone(eastern).date()
    ids: dict[int, str] = {}
    async with maker() as session:
        sports = {key: Sport(key=key, name=key) for key in (MLB, NCAAF)}
        session.add_all(sports.values())
        await session.flush()
        session.add_all([
            Team(sport_id=sports[MLB].id, name=LEAD, abbreviation="TEX"),
            Team(sport_id=sports[NCAAF].id, name=NAMESAKE, abbreviation="TEX"),
        ])
        for label, key, home, away, day, status in SPECIMEN:
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
                home_score=3 if settled else None,
                away_score=2 if settled else None,
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


def _card_leads_with_the_lead_club(payload) -> None:
    teams = [t.get("name") for t in payload.get("teams") or []]
    assert teams and teams[0] == LEAD, (
        "the specimen needs the TEAMS card to lead with the MLB club — otherwise "
        f"#8738's key is not armed and this tests nothing: {teams}"
    )


async def test_the_newest_days_finals_lead_the_finished_games(maker, search):
    ids = await _seed(maker)
    payload = await search(QUERY)
    _card_leads_with_the_lead_club(payload)

    settled = [label for label in _labels(payload, ids) if label in SETTLED_ORDER]
    assert settled == SETTLED_ORDER, (
        "finished games are not newest-day first — the card leader's older "
        f"finals still sit above another club's result from last night: {settled}"
    )


async def test_without_the_day_key_the_leaders_old_finals_bury_last_night(
    maker, search, monkeypatch,
):
    """Strawman: the fixture reproduces #9040 with the key removed."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_settled_day_order_key", lambda *_: None)
    ids = await _seed(maker)
    payload = await search(QUERY)
    _card_leads_with_the_lead_club(payload)

    settled = [label for label in _labels(payload, ids) if label in SETTLED_ORDER]
    assert settled.index("namesake_last_night") > settled.index("lead_5"), settled


async def test_the_card_leader_still_leads_the_upcoming_games(maker, search):
    """The control: #8738 is untouched where its specimen lived."""
    ids = await _seed(maker)
    payload = await search(QUERY)
    _card_leads_with_the_lead_club(payload)

    labels = _labels(payload, ids)
    upcoming = [label for label in labels if label in UPCOMING_ORDER]
    assert upcoming == UPCOMING_ORDER, upcoming
    assert labels.index("namesake_next") < labels.index("lead_last_night"), (
        f"an upcoming game fell below a finished one: {labels}"
    )


async def test_every_seeded_game_is_served(maker, search):
    """So the ordering cases cannot pass on a page that dropped a row."""
    ids = await _seed(maker)
    served = _labels(await search(QUERY), ids)
    assert sorted(served) == sorted(ids.values()), served
