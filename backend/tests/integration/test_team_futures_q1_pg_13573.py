"""#13573 — Real Postgres verification of `_query_team_futures` Q1 rewrite & equivalence.

Verifies on live PostgreSQL:
1. Entertainment FK links (e.g. Madden cover) and NULL-category links are preserved,
   while cross-sport FK and name false positives are filtered cleanly even inside SQL.
2. Tail outcomes created above `reader_floor` (missing from `open_futures_outcomes`) are
   still returned identically under active and stale fallback modes.
3. Multi-spelling collapsed clubs ("Montreal Canadiens" / "Montréal Canadiens") match.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import FuturesMarket, FuturesOutcome, OpenFuturesOutcome, Sport, Team
from app.routes.user import _query_team_futures
from app.services.database import Base
from app.utils import open_futures_outcomes as ofo_mod

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #13573 Q1 real-Postgres tests",
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def q1_pg_session():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_q1_pg_preserves_semantics_and_handles_tail_and_entertainment_fk(q1_pg_session):
    now = datetime.now(timezone.utc)
    async with q1_pg_session() as db:
        s_nba = Sport(id=1, key="basketball_nba", name="NBA", group="Basketball", active=True)
        s_nhl = Sport(id=2, key="icehockey_nhl", name="NHL", group="Ice Hockey", active=True)
        t_lak = Team(id=49, sport_id=1, name="Los Angeles Lakers", slug="los-angeles-lakers", espn_id="13")
        t_mtl1 = Team(id=568, sport_id=2, name="Montreal Canadiens", slug="montreal-canadiens", espn_id="10")
        t_mtl2 = Team(id=3706, sport_id=2, name="Montréal Canadiens", slug="montreal-canadiens-dup", espn_id="10")
        db.add_all([s_nba, s_nhl, t_lak, t_mtl1, t_mtl2])

        # Open markets: NBA (keeps), entertainment FK (keeps), NULL cat (keeps), NHL wrong-sport (rejects), closed (rejects)
        markets = [
            FuturesMarket(id=1, source="kalshi", external_id="k1", sport_id=1, name="NBA Championship", llm_sport_category="basketball", market_tier=1, status="open", updated_at=now),
            FuturesMarket(id=2, source="kalshi", external_id="k2", sport_id=None, name="Madden Athlete Cover", llm_sport_category="entertainment", market_tier=5, status="open", updated_at=now),
            FuturesMarket(id=3, source="polymarket", external_id="p3", sport_id=None, name="Special Uncategorized Winner", llm_sport_category=None, market_tier=5, status="open", updated_at=now),
            FuturesMarket(id=4, source="kalshi", external_id="k4", sport_id=2, name="NHL Cross-Sport Wrong Link", llm_sport_category="hockey", market_tier=1, status="open", updated_at=now),
            FuturesMarket(id=5, source="kalshi", external_id="k5", sport_id=1, name="Closed Historical Board", llm_sport_category="basketball", market_tier=1, status="resolved", updated_at=now - timedelta(days=30)),
            FuturesMarket(id=6, source="kalshi", external_id="k6", sport_id=2, name="Stanley Cup", llm_sport_category="hockey", market_tier=1, status="open", updated_at=now),
        ]
        db.add_all(markets)

        outcomes = [
            FuturesOutcome(id=10, market_id=1, external_id="o10", name="Los Angeles Lakers", team_id=49, current_probability=0.40, current_yes_bid=0.39, current_yes_ask=0.41, volume_24h=100, volume_24h_at=now, last_updated=now),
            FuturesOutcome(id=20, market_id=2, external_id="o20", name="LeBron Cover", team_id=49, current_probability=0.30, current_yes_bid=0.29, current_yes_ask=0.31, volume_24h=100, volume_24h_at=now, last_updated=now),
            FuturesOutcome(id=30, market_id=3, external_id="o30", name="Los Angeles Lakers", team_id=None, current_probability=0.25, current_yes_bid=0.24, current_yes_ask=0.26, volume_24h=100, volume_24h_at=now, last_updated=now),
            FuturesOutcome(id=40, market_id=4, external_id="o40", name="Los Angeles Lakers", team_id=49, current_probability=0.90, current_yes_bid=0.89, current_yes_ask=0.91, volume_24h=100, volume_24h_at=now, last_updated=now),
            FuturesOutcome(id=50, market_id=5, external_id="o50", name="Los Angeles Lakers", team_id=49, current_probability=0.80, current_yes_bid=0.79, current_yes_ask=0.81, volume_24h=100, volume_24h_at=now - timedelta(days=30), last_updated=now - timedelta(days=30)),
            FuturesOutcome(id=60, market_id=6, external_id="o60", name="Montréal Canadiens", team_id=None, current_probability=0.12, current_yes_bid=0.11, current_yes_ask=0.13, volume_24h=100, volume_24h_at=now, last_updated=now),
        ]
        db.add_all(outcomes)
        # Put only outcome 10 & 60 into open_futures_outcomes; outcome 30 sits above reader_floor=25 in tail_scan.
        db.add_all([
            OpenFuturesOutcome(outcome_id=10, market_id=1, name="Los Angeles Lakers"),
            OpenFuturesOutcome(outcome_id=60, market_id=6, name="Montréal Canadiens"),
        ])
        await db.commit()

        executed = []
        orig_exec = db.execute

        async def spy_exec(stmt, *a, **k):
            if hasattr(stmt, "compile"):
                executed.append(str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
            return await orig_exec(stmt, *a, **k)

        db.execute = spy_exec  # type: ignore[method-assign]

        ofo_mod._memo["at"] = None
        ofo_mod._memo["state"] = None
        with patch.object(
            ofo_mod,
            "_fetch_state",
            lambda: {"reader_floor": 25, "pass_at": now.timestamp(), "cycle_complete": True},
        ):
            res_ofo = await _query_team_futures([49], db, limit=30)

        active_sqls = list(executed)
        executed.clear()

        ofo_mod._memo["at"] = None
        ofo_mod._memo["state"] = None
        with patch.object(ofo_mod, "_fetch_state", lambda: None):
            res_fb = await _query_team_futures([49], db, limit=30)

        fb_sqls = list(executed)

        assert {it["market_id"] for it in res_ofo["items"]} == {1, 2, 3}
        assert {it["market_id"] for it in res_fb["items"]} == {1, 2, 3}

        fk_active = [s for s in active_sqls if "futures_outcomes.team_id IN" in s]
        name_active = [s for s in active_sqls if "Los Angeles Lakers" in s]
        assert len(fk_active) == 1 and "WITH fk_hits AS MATERIALIZED" in fk_active[0]
        assert len(name_active) == 1
        assert "WITH ofo_hits AS MATERIALIZED" in name_active[0]
        assert "tail_scan AS MATERIALIZED" in name_active[0]
        tail_scan_block = name_active[0].split("tail_scan AS MATERIALIZED", 1)[1].split(")", 1)[0]
        assert "ILIKE" not in tail_scan_block.upper()

        name_fb = [s for s in fb_sqls if "Los Angeles Lakers" in s]
        assert len(name_fb) == 1 and "open_futures_outcomes" not in name_fb[0]

        # Collapsed multi-spelling club check
        ofo_mod._memo["at"] = None
        ofo_mod._memo["state"] = None
        with patch.object(
            ofo_mod,
            "_fetch_state",
            lambda: {"reader_floor": 25, "pass_at": now.timestamp(), "cycle_complete": True},
        ):
            res_mtl = await _query_team_futures([568, 3706], db, limit=30)
        assert [it["market_id"] for it in res_mtl["items"]] == [6]
