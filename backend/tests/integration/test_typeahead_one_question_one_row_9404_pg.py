"""#9404 — the dropdown shows one question once, out of the REAL route against REAL Postgres.

Production 2026-09-28 16:05Z, `world series` typed into the search box at 390px:

    MLB World Series Champion   Los Angeles Dodgers 30%     polymarket 114584, tier 1
    Dota 2: … EPL World Series…  Match Winner 17%
    MLB World Series Winner     Los Angeles Dodgers 28%     odds_api 1, tier 5

One question, two numbers. `/api/events/search?q=world series` showed only
114584: `_admit_search_future` drops a second venue's copy of a question already
on the page (#8378), and the dropdown loop still deduped on the tiered key alone.

`tests/test_search_cross_source_tier_dedup_8378.py` pins the helper on these
exact rows. What it cannot see is whether `typeahead_search` asks it — so this
file drives the route.

    1. `world series` offers the Polymarket board and not the odds_api copy   the fix
    2. the odds_api board IS offered when it is the only one                 not vacuous
    3. two same-venue fiscal years under one title stay two rows             the control
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.test_typeahead_final_seven_route_control_pg import _FakeRedis

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #9404 real-Postgres typeahead "
            "control (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

# (name, source, tier, volume) — the production rows, read 2026-09-28.
WS_POLY = ("MLB World Series Champion 2026", "polymarket", 1, 41590129)
WS_ODDS = ("MLB World Series Winner", "odds_api", 5, None)
URBN_FY26 = ("Urban Outfitters Total Stores in Q1", "kalshi", 5, None)
URBN_FY27 = ("Urban Outfitters total stores in Q1", "kalshi", 2, None)
TEAMS = ("Los Angeles Dodgers", "Milwaukee Brewers", "Tampa Bay Rays")


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
    """Each row an open futures board with priced outcomes; returns name -> id."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    ids = {}
    for i, (name, source, tier, volume) in enumerate(rows):
        category = "economics" if name.startswith("Urban") else "baseball"
        outcomes = ("Yes", "No") if name.startswith("Urban") else TEAMS
        mid = (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         market_tier, volume)
                    VALUES (:n, :src, 'prop', TRUE, 'open', :rd, :xid,
                            :cat, :tier, :vol)
                    RETURNING id
                    """
                ),
                {
                    "n": name,
                    "src": source,
                    "rd": now + timedelta(days=30),
                    "xid": f"PGX-9404-{i}",
                    "cat": category,
                    "tier": tier,
                    "vol": volume,
                },
            )
        ).scalar()
        for j, o in enumerate(outcomes):
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name, "
                    "current_probability, last_updated) "
                    "VALUES (:m, :x, :n, :p, :now)"
                ),
                {"m": mid, "x": f"PGX-9404-{i}-{j}", "n": o, "p": 0.3 - 0.1 * j, "now": now},
            )
        ids[name] = mid
    await session.commit()
    return ids


async def _market_ids(session, q):
    from app.routes.events import typeahead_search

    body = await typeahead_search(
        q=q, debug_evidence=False, debug_timing=False, db=session, request=None
    )
    return [r.get("market_id") for r in body["suggestions"] if r.get("type") == "futures"]


class TestTheDropdownShowsOneQuestionOnce:
    async def test_world_series_offers_the_leader_and_not_the_second_venues_copy(
        self, pg_session, _no_redis
    ):
        ids = await _seed(pg_session, WS_POLY, WS_ODDS)
        got = await _market_ids(pg_session, "world series")
        assert ids[WS_POLY[0]] in got, got
        assert ids[WS_ODDS[0]] not in got, got

    async def test_the_odds_api_board_is_offered_when_it_is_the_only_one(
        self, pg_session, _no_redis
    ):
        # Anti-vacuity: the route really reaches the odds_api row for this query,
        # so its absence above is the fold's doing, not recall's.
        ids = await _seed(pg_session, WS_ODDS)
        got = await _market_ids(pg_session, "world series")
        assert ids[WS_ODDS[0]] in got, got

    async def test_two_same_venue_fiscal_years_stay_two_rows(self, pg_session, _no_redis):
        # #8378's control, at the route: one venue, one title, two tiers — two
        # different markets, and the fold is cross-venue only.
        ids = await _seed(pg_session, URBN_FY26, URBN_FY27)
        got = await _market_ids(pg_session, "urban outfitters")
        assert ids[URBN_FY26[0]] in got, got
        assert ids[URBN_FY27[0]] in got, got
