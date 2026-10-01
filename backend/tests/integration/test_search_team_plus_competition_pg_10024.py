"""#10024 — `dodgers world series` answers with the World Series board, not
"No results", proved through the route on real Postgres.

Production 2026-10-01, mid-postseason: `dodgers world series`, `yankees world
series`, `chiefs super bowl` each returned every list empty, while `phillies`
alone and `world series` alone found `MLB World Series Champion 2026`. The
reader named the board AND the team, and the query split across the two
fields: `world series` is in the market name, `dodgers` is one of its options.
Every recall arm wanted the whole query in one field.

Why Postgres: the split arms are trigram ILIKEs, a whole-word `~*` regex and a
correlated EXISTS, read by the tier-ordered window only when the other tier<=1
arms come back short. SQLite runs none of that as production does.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres team-plus-"
            "competition contract (CI provides one)"
        ),
    ),
]

WORLD_SERIES = "MLB World Series Champion 2026"
SUPER_BOWL = "NFL Super Bowl Winner"
WORLD_CUP = "World Cup Winner"
POKER = "World Series of Poker Main Event"

# (name, category, outcomes). Production's names for the first two (db-query,
# 2026-10-01 07:1xZ: markets 114584 and 86832).
BOARDS = [
    (WORLD_SERIES, "baseball", [
        "Los Angeles Dodgers", "New York Yankees", "Boston Red Sox",
        "Philadelphia Phillies",
    ]),
    (SUPER_BOWL, "football", ["Kansas City Chiefs", "Philadelphia Eagles"]),
    (WORLD_CUP, "soccer", ["Spain", "Brazil"]),
    # `red` and `sox` are both here, in two different options: one option must
    # carry the whole outcome run, so `red sox world series` may not reach this.
    (POKER, "poker", ["Red Johnson", "Sox Brennan"]),
]

# Enough `Red Sox` boards to fill the 20-row window from the name arm alone.
RED_SOX_PROPS = [f"Boston Red Sox prop {i}" for i in range(25)]


@pytest.fixture
async def maker():
    """Clean schema per test — the database is shared with the whole job."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.now(timezone.utc)
    rows = BOARDS + [(n, "baseball", ["Yes", "No"]) for n in RED_SOX_PROPS]
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for i, (name, category, outcomes) in enumerate(rows):
            market = FuturesMarket(
                source="kalshi", external_id=f"split-10024-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=30),
                llm_sport_category=category, volume=10_000.0,
            )
            session.add(market)
            await session.flush()
            for j, outcome in enumerate(outcomes):
                session.add(FuturesOutcome(
                    market_id=market.id, name=outcome,
                    current_probability=round(0.9 / len(outcomes), 4) + 0.01 * j,
                    external_id=f"{market.external_id}:{j}",
                ))
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and database.

    Redis raises, so every ask is a cache miss — the strawman asks the same
    query the ship case asks, and a live cache would answer it from the fixed run.
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
                resp = await http.get(
                    "/api/events/search", params={"q": q, "debug_timing": 1}
                )
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


def _futures(payload: dict) -> list[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return [f["name"] for f in payload["futures"] or []]


def _split_state(payload: dict) -> str:
    return payload["debug_timing"]["futures_split_arm"]


@pytest.mark.parametrize(
    "typed, board",
    [
        ("dodgers world series", WORLD_SERIES),
        ("world series dodgers", WORLD_SERIES),
        ("Yankees World Series", WORLD_SERIES),
        ("red sox world series", WORLD_SERIES),
        ("chiefs super bowl", SUPER_BOWL),
    ],
)
async def test_a_team_plus_its_competition_reaches_the_board(search, typed, board):
    payload = await search(typed)
    names = _futures(payload)
    assert names and names[0] == board, names
    assert WORLD_CUP not in names, names
    assert _split_state(payload) == "merged", payload["debug_timing"]


async def test_the_outcome_run_must_be_one_option(search):
    """`red` and `sox` in two different poker options is not a Red Sox board."""
    names = _futures(await search("red sox world series"))
    assert POKER not in names, names


async def test_a_full_window_never_reads_the_split_arms(search):
    """`red sox` fills its window from the name arm, so the split arms are not
    paid for: production measured them at 1.5-2.7 s on this query for no row."""
    payload = await search("red sox")
    assert len(_futures(payload)) >= 1
    assert _split_state(payload) == "skipped", payload["debug_timing"]


async def test_without_the_split_arms_the_page_is_empty_again(search, monkeypatch):
    """The strawman: no split arms, and production's empty page comes back."""
    from app.routes import events as ev

    monkeypatch.setattr(ev, "_split_futures_arms", lambda expanded: [])
    payload = await search("dodgers world series")
    assert WORLD_SERIES not in _futures(payload), _futures(payload)
    assert _split_state(payload) == "absent", payload["debug_timing"]
