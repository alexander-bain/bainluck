"""#9865 — `world series` leads with baseball's boards, out of the REAL route against REAL Postgres.

Production, MLB postseason, the header dropdown for `world series`:

    2026-09-30 16:05Z  1  MLB World Series Champion 2026           baseball, vol 42.3M
                       2  Dota 2: Ivory vs Team Kinetix (BO3) -    esports,  vol 22,272
                          EPL World Series Southeast Asia Group Stage
                       3  MLB 2026: World Series Winning League    baseball, vol NULL
                       4  MLB Postseason: World Series MVP         baseball, vol NULL

`tests/test_search_championship_query_sport_9865.py` pins the helper and the
shared reranker. What it cannot see is whether `typeahead_search` reaches them
with a sport and whether a later pass re-sorts the pool — so this file drives
the route.

    1. `world series` offers all three MLB boards above the Dota board     the fix
    2. severing the helper puts the Dota board back in row 2               the strawman
    3. `world series of poker` keeps the old order                         the control
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
            "set SEARCH_TEST_DATABASE_URL to run the #9865 real-Postgres typeahead "
            "control (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

# (name, category, tier, volume, outcomes) — the production rows, read 2026-09-30.
CHAMPION = ("MLB World Series Champion 2026", "baseball", 1, 42291678,
            ("Los Angeles Dodgers", "Milwaukee Brewers"))
DOTA = ("Dota 2: Ivory vs Team Kinetix (BO3) - EPL World Series Southeast Asia Group Stage",
        "esports", 4, 22272, ("Ivory", "Team Kinetix"))
LEAGUE = ("MLB 2026: World Series Winning League", "baseball", 1, None,
          ("American League", "National League"))
MVP = ("MLB Postseason: World Series MVP", "baseball", 3, None,
       ("Shohei Ohtani", "Freddie Freeman"))
POKER = ("World Series of Poker Main Event Winner", "poker", 5, 900000,
         ("Phil Hellmuth", "Daniel Negreanu"))


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
    """Each row an open Polymarket board with priced outcomes; returns name -> id."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    ids = {}
    for i, (name, category, tier, volume, outcomes) in enumerate(rows):
        mid = (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         market_tier, volume)
                    VALUES (:n, 'polymarket', 'prop', TRUE, 'open', :rd, :xid,
                            :cat, :tier, :vol)
                    RETURNING id
                    """
                ),
                {
                    "n": name,
                    "rd": now + timedelta(days=30),
                    "xid": f"PGX-9865-{i}",
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
                {"m": mid, "x": f"PGX-9865-{i}-{j}", "n": o, "p": 0.6 - 0.2 * j, "now": now},
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


class TestWorldSeriesLeadsWithBaseball:
    async def test_the_three_mlb_boards_sit_above_the_dota_board(self, pg_session, _no_redis):
        ids = await _seed(pg_session, CHAMPION, DOTA, LEAGUE, MVP)
        got = await _market_ids(pg_session, "world series")
        assert ids[DOTA[0]] in got, got  # demoted, never dropped
        dota_at = got.index(ids[DOTA[0]])
        for row in (CHAMPION, LEAGUE, MVP):
            assert got.index(ids[row[0]]) < dota_at, (row[0], got)

    async def test_severing_the_helper_puts_the_dota_board_back_in_row_two(
        self, pg_session, _no_redis, monkeypatch
    ):
        # Strawman: the route really orders these rows by volume without the
        # sport, so the order above is the helper's doing, not the fixture's.
        monkeypatch.setattr(
            "app.routes.events._championship_query_sport_category", lambda _e: None
        )
        ids = await _seed(pg_session, CHAMPION, DOTA, LEAGUE, MVP)
        got = await _market_ids(pg_session, "world series")
        assert got[:2] == [ids[CHAMPION[0]], ids[DOTA[0]]], got

    async def test_world_series_of_poker_keeps_poker_first(self, pg_session, _no_redis):
        ids = await _seed(pg_session, CHAMPION, POKER)
        got = await _market_ids(pg_session, "world series of poker")
        assert got and got[0] == ids[POKER[0]], got
