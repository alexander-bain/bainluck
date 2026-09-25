"""#8505 — searching your team shows last night's result first among the finals.

THE DEFECT, read on production 2026-09-25 01:4xZ, `/search?q=Red Sox`: three
upcoming games, then Sep 20, Sep 19, Sep 18, Sep 6 ... and last night's 0-1 loss
to Cleveland (15318147) at position 14, behind a game from Aug 28.

The route's ORDER BY was `status_order, tag_boost, search_rank DESC, time`. For a
team query every row ties on `search_rank` (`ts_rank_cd` = 1.0 on all eight rows
read), so the LLM tag tier decided the finished list ahead of recency:
`narrative:rivalry` = 3, `audience:national_interest` = 4,
`stakes:playoff_race` = 5. Page one was exactly tier 3 by date, then 4, then 5.

WHY THE ROUTE AND POSTGRES. `tag_boost` is a JSONB `@>` CASE and the rank is
`ts_rank_cd` — SQLite serves neither — and the ordering is a property of the
whole statement the route composes, not of the helper alone.

The CONTROL is the upcoming half: tags still order games not yet played. It is
what fails if the settled gate is widened to every row, so the fix cannot pass by
deleting the boost.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8505 settled-"
            "recency gate (CI job `search-recall` provides one)"
        ),
    ),
]

TEAM = "Boston Red Sox"
QUERY = "Red Sox"

# (label, opponent, days from now, status, tags). Opponents are all two words so
# every row scores the same `ts_rank_cd` for the query, as on production — the
# tie is the condition the defect needs.
SPECIMEN = [
    # The upcoming control: the rivalry game is further out, and still leads.
    ("next_untagged", "Chicago Cubs", 1, "scheduled", None),
    ("next_rivalry", "Tampa Rays", 3, "scheduled", ["narrative:rivalry"]),
    # The finals, shaped like production's page.
    ("last_night", "Cleveland Guardians", -1, "completed", ["audience:national_interest"]),
    (
        "two_nights",
        "Detroit Tigers",
        -2,
        "completed",
        ["stakes:playoff_race", "audience:local_interest"],
    ),
    ("five_days", "Seattle Mariners", -5, "completed", None),
    ("ten_days", "Baltimore Orioles", -10, "completed", ["narrative:historic_rivalry"]),
    ("month_old_rivalry", "Yankees Pinstripes", -25, "completed", ["narrative:rivalry"]),
]


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


@pytest.fixture
async def seeded(maker):
    """The specimen, at RELATIVE times (gotcha #44): the route windows events on
    `commence_time`, so pinned dates would stop exercising it."""
    from app.models.models import Event, Sport

    now = datetime.now(timezone.utc).replace(microsecond=0)
    ids: dict[int, str] = {}
    async with maker() as session:
        mlb = Sport(key="baseball_mlb", name="MLB")
        session.add(mlb)
        await session.flush()
        for label, opponent, days, status, tags in SPECIMEN:
            kickoff = now + timedelta(days=days)
            settled = status == "completed"
            row = Event(
                sport_id=mlb.id,
                home_team_name=TEAM,
                away_team_name=opponent,
                commence_time=kickoff,
                status=status,
                home_score=0 if settled else None,
                away_score=1 if settled else None,
                completed_at=kickoff + timedelta(hours=3) if settled else None,
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


async def test_last_nights_game_leads_the_finals(search, seeded):
    served = _labels(await search(QUERY), seeded)
    finals = [label for label in served if label not in ("next_untagged", "next_rivalry")]

    assert finals == [
        "last_night",
        "two_nights",
        "five_days",
        "ten_days",
        "month_old_rivalry",
    ], (
        "settled games are not most-recent-first — the LLM tag tier is still "
        f"ordering finished games ahead of recency: {finals}"
    )


async def test_upcoming_games_still_take_the_tag_boost(search, seeded):
    """The control. A gate widened to every row passes the case above and fails
    this one; so does deleting the boost."""
    served = _labels(await search(QUERY), seeded)

    assert served[:2] == ["next_rivalry", "next_untagged"], (
        "the tag boost stopped ordering upcoming games — #8505 is scoped to "
        f"settled rows only: {served}"
    )


async def test_every_seeded_game_is_served(search, seeded):
    """So the ordering cases cannot pass on a page that dropped a row."""
    served = _labels(await search(QUERY), seeded)
    assert sorted(served) == sorted(seeded.values()), served
