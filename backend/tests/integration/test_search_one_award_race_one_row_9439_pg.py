"""#9439 — one award race prints once, out of the REAL routes against REAL Postgres.

Production 2026-09-28 ~18:40Z, `mvp` typed into the search box at 390px:

    MVP Winner?            Josh Allen 25%    kalshi 40532 (KXNFLMVP-27)
    NBA MVP Winner         Victor Wembanyama 30%
    NFL: 2026 MVP Winner   Josh Allen 22%    polymarket 7585490

One race, two numbers, on the dropdown and on /search alike. The rule lives in
`_admit_search_future`, which both routes ask (#9404); the unit file
`tests/test_search_one_award_race_one_row_9439.py` pins it on the production
rows. What it cannot see is that each ROUTE hands the rule rows carrying their
outcomes and resolution dates — so this file drives both routes.

    1. `mvp` offers one NFL MVP board, on the dropdown and on /search      the fix
    2. each of the two boards IS offered when it is the only one          not vacuous
    3. NBA MVP beside NFL MVP stays two rows (same `mvp` group)           the control
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from tests.integration.test_typeahead_final_seven_route_control_pg import _FakeRedis

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #9439 real-Postgres award-race "
            "control (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# (name, source, tier, resolution, listed names) — the production rows, 2026-09-28.
NFL_KALSHI = (
    "MVP Winner?", "kalshi", 3, _utc(2027, 3, 14, 15),
    ("Josh Allen", "Brock Purdy", "Lamar Jackson", "Patrick Mahomes", "Joe Burrow"),
)
NFL_POLY = (
    "Pro Football: 2026 MVP Winner", "polymarket", 3, _utc(2027, 3, 1, 4, 59),
    ("Josh Allen", "Lamar Jackson", "Brock Purdy", "Patrick Mahomes", "Joe Burrow"),
)
NBA_KALSHI = (
    "Pro Basketball MVP Winner", "kalshi", 3, _utc(2027, 7, 31, 14),
    ("Victor Wembanyama", "Luka Doncic", "Shai Gilgeous-Alexander", "Nikola Jokic"),
)


@pytest.fixture
def _no_redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    return client


@pytest.fixture
async def pg_session():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed(session, *rows):
    """Each row an open award board with priced outcomes; returns name -> id."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    ids = {}
    for i, (name, source, tier, resolution, names) in enumerate(rows):
        mid = (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         market_tier, volume)
                    VALUES (:n, :src, 'award', TRUE, 'open', :rd, :xid,
                            'football', :tier, :vol)
                    RETURNING id
                    """
                ),
                {
                    "n": name,
                    "src": source,
                    "rd": resolution,
                    "xid": f"PGX-9439-{i}",
                    "tier": tier,
                    "vol": 1_000_000 - 1000 * i,
                },
            )
        ).scalar()
        for j, o in enumerate(names):
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name, "
                    "current_probability, last_updated) "
                    "VALUES (:m, :x, :n, :p, :now)"
                ),
                {"m": mid, "x": f"PGX-9439-{i}-{j}", "n": o, "p": 0.25 - 0.04 * j, "now": now},
            )
        ids[name] = mid
    await session.commit()
    return ids


async def _dropdown_ids(session, q):
    from app.routes.events import typeahead_search

    body = await typeahead_search(
        q=q, debug_evidence=False, debug_timing=False, db=session, request=None
    )
    return [r.get("market_id") for r in body["suggestions"] if r.get("type") == "futures"]


async def _search_ids(session, q):
    """/search through the ASGI app, its session dependency pointed at `session`."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:
            resp = await http.get("/api/events/search", params={"q": q})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
    return [f["id"] for f in resp.json().get("futures") or []]


class TestOneAwardRaceOneRow:
    @pytest.mark.parametrize("surface", [_dropdown_ids, _search_ids])
    async def test_mvp_offers_one_nfl_mvp_board(self, pg_session, _no_redis, surface):
        ids = await _seed(pg_session, NFL_KALSHI, NFL_POLY)
        got = await surface(pg_session, "mvp")
        nfl = {ids[NFL_KALSHI[0]], ids[NFL_POLY[0]]}
        assert len(nfl & set(got)) == 1, got

    @pytest.mark.parametrize("row", [NFL_KALSHI, NFL_POLY], ids=["kalshi", "polymarket"])
    @pytest.mark.parametrize("surface", [_dropdown_ids, _search_ids])
    async def test_each_nfl_board_is_offered_when_it_is_the_only_one(
        self, pg_session, _no_redis, surface, row
    ):
        # Anti-vacuity: the route reaches BOTH rows for `mvp`, so the one missing
        # above is the fold's doing, not recall's.
        ids = await _seed(pg_session, row)
        got = await surface(pg_session, "mvp")
        assert ids[row[0]] in got, got

    @pytest.mark.parametrize("surface", [_dropdown_ids, _search_ids])
    async def test_nba_and_nfl_mvp_stay_two_rows(self, pg_session, _no_redis, surface):
        ids = await _seed(pg_session, NBA_KALSHI, NFL_POLY)
        got = await surface(pg_session, "mvp")
        assert ids[NBA_KALSHI[0]] in got, got
        assert ids[NFL_POLY[0]] in got, got
