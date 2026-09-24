"""#8427 — `superbowl`, typed as one word, finds the Super Bowl market, proved at the route.

THE DEFECT, Alex's TestFlight 1.0.1 (20) recording, reproduced on production
2026-09-24 with HTTP 200 on both routes::

    q=superbowl              futures []        typeahead []
    q=nfl superbowl winner   futures []        typeahead []
    q=super bowl             futures [86832 …] typeahead [86832 …]

Every venue names it in two words ("NFL Super Bowl Winner"); the joined spelling
is how people type it. The fix is one entry in `_SEARCH_TERM_SYNONYMS`, and the
assertion lives HERE and not on the table for #5821's reason (restated in
`test_search_diacritic_fold_pg_6977.py`): for a multi-term query the route ANDs one
arm PER TERM, so a helper that looks right can still be absent from the reader's
filter. Every case drives `GET /api/events/search` or `/api/events/typeahead` over
a real database and reads the served payload.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres superbowl recall "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

#: Production row 86832, verbatim.
MARKET = "NFL Super Bowl Winner"
#: The unrelated row that must stay out of every Super Bowl answer.
OTHER = "College Football Playoff Winner"


@pytest.fixture
async def maker():
    """Clean schema per test (`drop_all` first: the `search-recall` DB is shared)."""
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
async def client(maker):
    """The real app over the real database, Redis raising.

    Redis is patched to raise because both routes cache whole responses, and these
    cases ask several spellings in a row — a live cache would let one answer serve
    another and a dead synonym would pass.
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
            yield http
    app.dependency_overrides.clear()


async def _seed(session):
    """The Super Bowl market and one unrelated football future, both priced and open.

    The two legs sum to 1.0 on purpose: a board whose legs sum to 0.35 is refused
    by full search as not-a-partition (measured on this rig, spaced control and
    all), which would read as a recall failure that is really a fixture gap.

    Resolution dates are RELATIVE (gotcha #44): the route keeps futures with
    `resolution_date IS NULL OR resolution_date >= now()`.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)
    for ext, name in (("KXSB-27", MARKET), ("KXNCAAF-27", OTHER)):
        market = FuturesMarket(
            source="kalshi",
            external_id=ext,
            name=name,
            status="open",
            market_tier=1,
            resolution_date=now + timedelta(days=120),
        )
        session.add(market)
        await session.flush()
        for i, team in enumerate(("Kansas City Chiefs", "Buffalo Bills")):
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{ext}:{i}",
                    name=team,
                    current_probability=(0.6, 0.4)[i],
                )
            )
    await session.commit()


async def _futures(http, q: str) -> list[str]:
    resp = await http.get("/api/events/search", params={"q": q})
    assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
    body = resp.json()
    assert "futures" in body, f"no `futures` key; got {sorted(body)}"
    return [f["name"] for f in body["futures"]]


async def _suggested(http, q: str) -> list[str]:
    resp = await http.get("/api/events/typeahead", params={"q": q})
    assert resp.status_code == 200, f"typeahead {q!r} -> {resp.status_code}"
    body = resp.json()
    assert "suggestions" in body, f"no `suggestions` key; got {sorted(body)}"
    return [s["text"] for s in body["suggestions"] if s.get("type") == "futures"]


JOINED = ["superbowl", "nfl superbowl winner", "superbowl winner", "Superbowl"]


async def test_control_the_spaced_spelling_already_works(maker, client):
    """Taken first: if this fails the fixture is wrong, not the synonym."""
    async with maker() as session:
        await _seed(session)
    assert await _futures(client, "super bowl") == [MARKET]
    assert await _suggested(client, "super bowl") == [MARKET]


@pytest.mark.parametrize("q", JOINED)
async def test_the_joined_spelling_reaches_the_market_on_full_search(maker, client, q):
    async with maker() as session:
        await _seed(session)
    assert await _futures(client, q) == [MARKET]


@pytest.mark.parametrize("q", JOINED)
async def test_the_joined_spelling_reaches_the_market_in_suggestions(maker, client, q):
    async with maker() as session:
        await _seed(session)
    assert await _suggested(client, q) == [MARKET]


async def test_an_unrelated_word_still_finds_nothing(maker, client):
    """The synonym widens one spelling; it must not make search match anything."""
    async with maker() as session:
        await _seed(session)
    assert await _futures(client, "superbowlx") == []
    assert await _suggested(client, "superbowlx") == []
    assert await _futures(client, "stanley cup") == []
