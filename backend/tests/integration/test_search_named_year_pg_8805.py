"""#8805 — `2028 democratic nominee` reaches the 2028 nominee boards, proved at the route.

THE DEFECT, production 2026-09-26 (Flow Sentinel gold set, reproduced by hand)::

    q=2028 democratic nominee     futures []
    q=2028 republican nominee     futures [LA-05 Republican nominee?]
    q=democratic presidential nominee
                                  futures [Democratic Presidential Nominee 2028, …]

`parse_intent` reads ``2028`` as a season and the route searches markets on the
subject, ``democratic nominee``. About ninety open House primaries ("TX-21
Democratic nominee?") carry both words side by side and rank 0.10 on
`ts_rank_cd`. The national board has a word between them and ranks 0.05, so the
primaries filled the 20-row window. In production every one was then refused,
and the page was empty.

This rig seeds 25 such primaries (more than the window holds) and the national
boards, all priced, and drives `GET /api/events/search` over a real database.
Here the primaries are NOT refused, so the pre-fix page is ten primaries with
no national board in it. The test does not depend on the refusal.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres named-year "
            "futures contract (CI job `search-recall` provides one)"
        ),
    ),
]

DEM = "Democratic Presidential Nominee 2028"
DEM_VP = "2028 Democratic VP nominee"
GOP = "Republican Presidential Nominee 2028"
PRIMARIES = [f"TX-{n:02d} Democratic nominee?" for n in range(1, 26)]
GOP_PRIMARIES = [f"TX-{n:02d} Republican nominee?" for n in range(1, 26)]


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
    """The real app over the real database, Redis raising (no cached answers)."""
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
    """The national boards (big volume) and 25 House primaries per party (small).

    Every board is a priced two-leg partition summing to 1.0, so full search
    serves it. Resolution dates are RELATIVE (gotcha #44).
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)
    boards = [
        (f"KXPRES-{i}", name, 2, 10_000_000)
        for i, name in enumerate((DEM, DEM_VP, GOP))
    ]
    boards += [
        (f"KXHOUSE-{i}", name, 3, 1_000 + i)
        for i, name in enumerate(PRIMARIES + GOP_PRIMARIES)
    ]
    for ext, name, tier, volume in boards:
        market = FuturesMarket(
            source="kalshi",
            external_id=ext,
            name=name,
            status="open",
            market_tier=tier,
            volume=volume,
            resolution_date=now + timedelta(days=400),
        )
        session.add(market)
        await session.flush()
        for i, person in enumerate(("Candidate A", "Candidate B")):
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{ext}:{i}",
                    name=person,
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


async def test_control_the_seed_reaches_the_page(maker, client):
    """Taken first: if this fails the fixture is wrong, not the fix."""
    async with maker() as session:
        await _seed(session)
    assert DEM in await _futures(client, "democratic presidential nominee")


async def test_the_named_year_leads_with_the_national_board(maker, client):
    """The gold-set probe: the 2028 national board is the first row."""
    async with maker() as session:
        await _seed(session)
    page = await _futures(client, "2028 democratic nominee")
    assert page, "the page is empty — the #8805 defect as production served it"
    assert page[0] == DEM, (
        f"'2028 democratic nominee' did not lead with {DEM!r}; page was {page}"
    )
    assert DEM_VP in page, f"{DEM_VP!r} names the year too; page was {page}"


async def test_the_republican_twin_leads_with_its_board(maker, client):
    """Production served one Louisiana primary for this query."""
    async with maker() as session:
        await _seed(session)
    page = await _futures(client, "2028 republican nominee")
    assert page and page[0] == GOP, f"page was {page}"


async def test_the_year_orders_rows_and_removes_none(maker, client):
    """A band, not a filter: primaries that do not name the year still serve.

    The page is ten rows. Two name the year and lead; the other eight are
    primaries. A filter would serve two rows.
    """
    async with maker() as session:
        await _seed(session)
    page = await _futures(client, "2028 democratic nominee")
    assert len(page) == 10, f"page was {page}"
    assert set(page[:2]) == {DEM, DEM_VP}, f"page was {page}"
    assert all(name in PRIMARIES for name in page[2:]), f"page was {page}"
