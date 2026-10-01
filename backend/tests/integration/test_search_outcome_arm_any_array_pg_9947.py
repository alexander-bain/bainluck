"""#9947 — `ohtani` keeps the boards he is priced on, through the ARRAY-form outcome arm, on real Postgres.

Production 2026-10-01 00:06-00:20Z: `ohtani` served two title-only boards on
every read (`futures_outcome_arm: budget_exceeded`). The arm's `id IN (subquery)`
let the planner walk every open market probing outcomes (4,640-6,345 ms against
a 1,000 ms bound) until an autoanalyze moved the estimate back;
`id = ANY(ARRAY(subquery))` resolves the match set once and reads markets by
primary key (57-146 ms in that window, the same twenty ids in the same order).

The unit guard (`tests/test_search_outcome_arm_any_array_9947.py`) pins the
rendered SHAPE. This file proves what only Postgres can:
  * the rendered `ANY (array((SELECT ...)))` parses and runs inside the route's
    savepointed arm, and the route reports the arm `merged`;
  * the ARRAY form returns exactly the set the IN form returns — closed
    markets out, a market with two matching outcomes once, no match empty.

The plan choice itself is a property of production's row counts and is not
reproducible on a fixture; the EXPLAIN numbers above are the evidence for it.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9947 outcome-arm "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

WS_MVP = "MLB Postseason: World Series MVP"
CS_MVP = "MLB Championship Series MVP Winner"
NAMED = "Shohei Ohtani: Cy Young and MVP Winner"
CY_YOUNG = "AL Cy Young Award Winner"
LAST_YEAR = "2025 World Series MVP"

# (external_id, market name, status, outcome names) — production's spellings.
SEEDS = [
    ("KXMLBWSMVP-26", WS_MVP, "open", ["Shohei Ohtani", "Aaron Judge"]),
    ("KXMLBCSMVP-26", CS_MVP, "open", ["Shohei Ohtani", "Freddie Freeman"]),
    ("KXOHTANI-26", NAMED, "open", ["Yes"]),
    # Two outcomes name him: the market must still come back ONCE.
    ("KXMLBMVPDUP-26", "MLB MVP Finalists", "open", ["Shohei Ohtani (DH)", "Shohei Ohtani (P)"]),
    ("KXALCY-26", CY_YOUNG, "open", ["Tarik Skubal", "Garrett Crochet"]),
    ("KXMLBWSMVP-25", LAST_YEAR, "closed", ["Shohei Ohtani", "Mookie Betts"]),
]


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
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

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for external_id, name, status, outcomes in SEEDS:
            market = FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=name,
                status=status,
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
            session.add(market)
            await session.flush()
            for outcome in outcomes:
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{external_id}:{outcome}",
                        name=outcome,
                        current_probability=0.3,
                    )
                )
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and database; Redis raises."""
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

            async def _search(q: str, **params) -> dict:
                resp = await http.get("/api/events/search", params={"q": q, **params})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def test_ohtani_serves_every_board_he_is_priced_on(search):
    names = [f.get("name") for f in (await search("ohtani"))["futures"]]
    assert {WS_MVP, CS_MVP, NAMED} <= set(names), names
    assert CY_YOUNG not in names, names
    assert LAST_YEAR not in names, f"a closed board reached the page: {names}"


async def test_the_route_reports_the_arm_merged(search):
    """One name match, so the arm runs — and a statement Postgres refused would
    surface here as an error, not as `merged`."""
    payload = await search("ohtani", debug_timing="1")
    assert payload["debug_timing"]["futures_outcome_arm"] == "merged", payload["debug_timing"]


@pytest.mark.parametrize(
    "pattern",
    ["%ohtani%", "%Shohei Ohtani (%", "%judge%", "%nobody-by-this-name%"],
)
async def test_the_array_form_returns_the_in_forms_set(maker, pattern):
    from sqlalchemy import select

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.routes.events import _market_has_outcome

    cond = FuturesOutcome.name.ilike(pattern)
    old = FuturesMarket.id.in_(select(FuturesOutcome.market_id).where(cond))
    async with maker() as session:
        want = (await session.execute(
            select(FuturesMarket.id).where(old, FuturesMarket.status == "open")
            .order_by(FuturesMarket.id)
        )).scalars().all()
        got = (await session.execute(
            select(FuturesMarket.id).where(_market_has_outcome(cond), FuturesMarket.status == "open")
            .order_by(FuturesMarket.id)
        )).scalars().all()
    assert got == want, (pattern, got, want)
    if pattern == "%ohtani%":
        # The two MVP boards + the two-outcome market once (NAMED is a title match).
        assert len(want) == 3, want
