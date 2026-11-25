"""#13573 — Regression tests for `_query_team_futures` q1 latency & sport scoping."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import user as user_route
from app.utils import open_futures_outcomes as ofo_mod
from tests.test_team_futures_perf_13552 import _build_pg_session, _market, _outcome

pytestmark = pytest.mark.asyncio


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _club(tid: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=tid,
        name=name,
        sport_id=1,
        espn_id=str(tid),
        logo_url_small=None,
        logo_url=None,
        primary_color=None,
        alternate_names=None,
        roster_players=None,
    )


async def test_pg_q1_isolates_ofo_and_tail_scan_and_fk_hits():
    """PG Q1 uses materialized fk_hits, ofo_hits joined to futures_markets, and PK-only tail_scan."""
    now = _now()
    team = _club(49, "Los Angeles Lakers")
    o = _outcome(101, 1001, "Los Angeles Lakers", 0.35, stamp=now, team_id=49)
    m = _market(1001, "NBA Championship", [o], updated_at=now)
    db, sqls, _ = _build_pg_session(
        teams=[team],
        fk_rows=[(o, m, "basketball_nba")],
        markets=[m],
        bind=SimpleNamespace(dialect=postgresql.dialect()),
    )
    ofo_mod._memo["at"] = None
    ofo_mod._memo["state"] = None
    with patch.object(
        ofo_mod,
        "_fetch_state",
        lambda: {"reader_floor": 4000000, "pass_at": now.timestamp(), "cycle_complete": True},
    ):
        res = await user_route._query_team_futures([49], db, limit=30)

    assert [it["market_id"] for it in res["items"]] == [1001]

    fk_sqls = [s for s in sqls if "futures_outcomes.team_id IN" in s]
    assert len(fk_sqls) == 1
    assert "WITH fk_hits AS MATERIALIZED" in fk_sqls[0]
    # Preserves non-sport LLM categories (entertainment / Madden cover, NULL), filters other sports.
    assert "futures_markets.llm_sport_category IS NULL" in fk_sqls[0]
    assert "'hockey'" in fk_sqls[0]
    assert "'entertainment'" not in fk_sqls[0]

    name_sqls = [s for s in sqls if "Los Angeles Lakers" in s]
    assert len(name_sqls) == 1
    qname = name_sqls[0]
    assert "WITH ofo_hits AS MATERIALIZED" in qname
    assert "JOIN futures_markets ON futures_markets.id = open_futures_outcomes.market_id" in qname
    assert "tail_scan AS MATERIALIZED" in qname
    assert "WHERE futures_outcomes.id > 4000000" in qname
    # Critical: tail_scan itself must NOT carry ILIKE (no 8.8M GIN scan); ILIKE filters tail_scan in tail_hits.
    tail_scan_block = qname.split("tail_scan AS MATERIALIZED", 1)[1].split(")", 1)[0]
    assert "ILIKE" not in tail_scan_block.upper()
    assert "futures_markets.llm_sport_category IN ('basketball')" in qname


async def test_pg_q1_fallback_still_pushes_sport_filter():
    """When open_futures_outcomes is stale, q1_name fallback still narrows futures_markets by sport."""
    now = _now()
    team = _club(100, "Boston Celtics")
    o = _outcome(102, 1002, "Boston Celtics", 0.30, stamp=now, team_id=100)
    m = _market(1002, "NBA Championship", [o], updated_at=now)
    db, sqls, _ = _build_pg_session(
        teams=[team],
        fk_rows=[(o, m, "basketball_nba")],
        markets=[m],
        bind=SimpleNamespace(dialect=postgresql.dialect()),
    )
    ofo_mod._memo["at"] = None
    ofo_mod._memo["state"] = None
    with patch.object(ofo_mod, "_fetch_state", lambda: None):
        res = await user_route._query_team_futures([100], db, limit=30)

    assert [it["market_id"] for it in res["items"]] == [1002]
    fb_sqls = [s for s in sqls if "Boston Celtics" in s]
    assert len(fb_sqls) == 1
    assert "open_futures_outcomes" not in fb_sqls[0]
    assert "futures_markets.llm_sport_category IN ('basketball')" in fb_sqls[0]
