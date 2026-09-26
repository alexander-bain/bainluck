"""#8942 — searching your club shows its next game first.

THE DEFECT, read on production 2026-09-26 21:50Z, `/search?q=arsenal`: the games
list opened with Fleetwood v Arsenal (EFL Cup, Oct 27) above Arsenal v Leeds
(EPL, Oct 10) — the next game — then Lille (Oct 13), Forest (Oct 18).
`?q=liverpool` read the same way (EFL Cup Oct 28 above Man City Oct 11).

Upcoming games ordered `status_order, tag_boost, search_rank DESC, time`. Every
row of a club query ties on `search_rank`, and the cup tie carries
`importance:playoff` (tier 1) while league games carry no qualifying tag (tier
9), so the LLM tag tier decided the club's schedule before the date did.

THE CONTROL is the same specimen with no TEAMS card (no `teams` row matches the
query). There the tag tier still leads, so (a) the specimen reproduces the defect
whenever the club gate is off, and (b) the fix cannot pass by deleting the tier.

WHY THE ROUTE AND POSTGRES: the tier is a JSONB `@>` CASE, the rank is
`ts_rank_cd`, and the club gate reads the teams statement the route runs first.
SQLite serves none of it.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8942 club-"
            "schedule gate (CI job `search-recall` provides one)"
        ),
    ),
]

CLUB = "Arsenal"
QUERY = "arsenal"

# (label, sport key, home, away, days from now, status, tags). Opponents are all
# two words so every row scores the same `ts_rank_cd`, as on production — the
# tie is the condition the defect needs.
SPECIMEN = [
    ("next_league", "soccer_epl", CLUB, "Leeds United", 14, "scheduled",
     ["importance:regular_season", "league:epl", "tier:1"]),
    ("later_league", "soccer_epl", "Nottingham Forest", CLUB, 22, "scheduled",
     ["importance:regular_season", "league:epl", "tier:1"]),
    ("cup_tie", "soccer_england_efl_cup", "Fleetwood Town", CLUB, 31, "scheduled",
     ["class:other", "importance:playoff", "tier:4"]),
    ("last_result", "soccer_epl", "Brighton Hove", CLUB, -7, "completed",
     ["importance:regular_season"]),
]
UPCOMING = ("next_league", "later_league", "cup_tie")


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


async def _seed(maker, *, with_club: bool) -> dict[int, str]:
    """The specimen at RELATIVE times (gotcha #44): the route windows events on
    `commence_time`, so pinned dates would stop exercising it."""
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc).replace(microsecond=0)
    ids: dict[int, str] = {}
    async with maker() as session:
        sports: dict[str, Sport] = {}
        for key in sorted({s[1] for s in SPECIMEN}):
            sports[key] = Sport(key=key, name=key)
            session.add(sports[key])
        await session.flush()
        if with_club:
            session.add(Team(sport_id=sports["soccer_epl"].id, name=CLUB, abbreviation="ARS"))
        for label, key, home, away, days, status, tags in SPECIMEN:
            kickoff = now + timedelta(days=days)
            settled = status == "completed"
            row = Event(
                sport_id=sports[key].id,
                home_team_name=home,
                away_team_name=away,
                commence_time=kickoff,
                status=status,
                home_score=3 if settled else None,
                away_score=0 if settled else None,
                completed_at=kickoff + timedelta(hours=2) if settled else None,
                event_tags=tags,
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


async def test_a_club_query_reads_its_schedule_in_date_order(maker, search):
    ids = await _seed(maker, with_club=True)
    payload = await search(QUERY)

    assert [t["name"] for t in payload.get("teams") or []] == [CLUB], (
        "the specimen needs a TEAMS card naming the club — without it this case "
        f"tests the control's arm: {payload.get('teams')}"
    )
    upcoming = [label for label in _labels(payload, ids) if label in UPCOMING]
    assert upcoming == ["next_league", "later_league", "cup_tie"], (
        "a club's upcoming games are not in date order — the tag tier "
        f"(`importance:playoff` on the cup tie) still leads: {upcoming}"
    )


async def test_without_a_club_card_the_tag_tier_still_leads(maker, search):
    """The control. Deleting the tier, or widening the gate to every query,
    passes the case above and fails this one."""
    ids = await _seed(maker, with_club=False)
    payload = await search(QUERY)

    assert not payload.get("teams"), payload.get("teams")
    upcoming = [label for label in _labels(payload, ids) if label in UPCOMING]
    assert upcoming == ["cup_tie", "next_league", "later_league"], (
        "the tag tier stopped ordering upcoming games for a query that names no "
        f"club — #8942 is scoped to club queries only: {upcoming}"
    )


async def test_every_seeded_game_is_served(maker, search):
    """So the ordering cases cannot pass on a page that dropped a row."""
    ids = await _seed(maker, with_club=True)
    served = _labels(await search(QUERY), ids)
    assert sorted(served) == sorted(ids.values()), served
