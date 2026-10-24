"""#10769 — the futures pools' `status = 'open'` reaches Postgres as a constant.

The open-only partial indexes behind search suggestions
(`ix_futures_name_trgm_open`, `ix_futures_name_fts_open`) are declared
`WHERE status = 'open'`. The reader runs the futures arms through asyncpg as
prepared statements. Spelled `FuturesMarket.status == "open"`, the predicate
reaches Postgres as `futures_markets.status = $1::VARCHAR`; after five executions
Postgres may keep a generic plan, and a generic plan cannot prove `$1` implies the
partial's `WHERE` — so neither open-only partial is usable and the arm falls back
to the whole-table trigram index, scanning the settled tail #10769 removes.

The latency gate cannot see this: it compiles the arm with `literal_binds=True`,
which prints `status = 'open'` either way. So every assertion here compiles with
the ASYNCPG dialect and NO literal binds — the form the reader actually sends.

What this file proves: the SQL text each route sends. What it does NOT prove:
that Postgres picks the partial (that is a plan choice, decided per query by the
unchanged gate), or that production currently runs these statements generic.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import asyncpg as pg_asyncpg

from app.models.models import FuturesMarket
from app.routes import events as ev

_DIALECT = pg_asyncpg.dialect()
_INLINE = "futures_markets.status = 'open'"
_BOUND = re.compile(r"futures_markets\.status\s*=\s*\$\d+")


def _asyncpg_sql(stmt) -> str:
    """The text asyncpg prepares: binds stay `$n`, constants stay inline."""
    return " ".join(str(stmt.compile(dialect=_DIALECT)).split())


def _result():
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    r.scalars.return_value.first.return_value = None
    r.scalar.return_value = 0
    r.scalar_one_or_none.return_value = None
    r.fetchall.return_value = []
    r.all.return_value = []
    r.first.return_value = None
    r.mappings.return_value.all.return_value = []
    return r


def _recording_db(seen: list):
    db = AsyncMock()

    async def execute(stmt, *a, **k):
        if hasattr(stmt, "compile") and not isinstance(stmt, str):
            try:
                sql = _asyncpg_sql(stmt)
            except Exception:  # a TextClause with unbound params, etc.
                sql = str(stmt)
            if "futures_markets.status" in sql:
                seen.append(sql)
        return _result()

    db.execute = AsyncMock(side_effect=execute)
    return db


def _patches():
    rc = MagicMock()
    rc.get.return_value = None  # cache MISS, so the route builds the pool
    return (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._record_trending", new=MagicMock()),
        patch("app.routes.events._apply_search_statement_timeout", new=AsyncMock()),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
    )


async def _search_statements(q: str) -> list[str]:
    seen: list[str] = []
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5]:
        await ev.search_events(
            request=MagicMock(),
            response=MagicMock(),
            q=q,
            db=_recording_db(seen),
            sport=None,
            tags=None,
            page=1,
            per_page=25,
            days_back=30,
            include_upcoming=True,
            debug_timing=False,
            current_user=None,
        )
    return seen


async def _typeahead_statements(q: str) -> list[str]:
    seen: list[str] = []
    request = MagicMock()
    request.headers = {}
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5]:
        await ev.typeahead_search(
            q=q,
            debug_evidence=False,
            debug_timing=False,
            db=_recording_db(seen),
            request=request,
        )
    return seen


def _name_arm_pool_reads(statements: list[str]) -> list[str]:
    """The candidate-pool reads: a futures name arm under the open filter."""
    return [
        s for s in statements
        if "futures_markets.name" in s and "futures_markets.resolution_date" in s
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface, run",
    [("/search", _search_statements), ("/typeahead", _typeahead_statements)],
)
async def test_the_route_sends_the_open_filter_as_a_constant(surface, run):
    """🔴 THE SHIP. Driven through the real route, compiled as asyncpg sends it."""
    pool_reads = _name_arm_pool_reads(await run("world cup"))
    # Non-vacuity: the route really did build its futures pool here.
    assert pool_reads, f"{surface} sent no futures candidate read"
    for sql in pool_reads:
        assert _INLINE in sql, f"{surface} pool read has no inline open filter:\n{sql}"
        assert not _BOUND.search(sql), (
            f"{surface} still binds the status as a parameter — a generic plan "
            f"cannot use the open-only partial indexes:\n{sql}"
        )


def test_the_constant_is_the_partials_predicate_and_nothing_else():
    """Same truth value as the bind it replaces: `= 'open'`, no cast, no other literal."""
    sql = _asyncpg_sql(
        select(FuturesMarket.id).where(FuturesMarket.status == ev._FUTURES_OPEN_STATUS_SQL)
    )
    assert sql.endswith("WHERE futures_markets.status = 'open'"), sql
    assert "$" not in sql, sql


def test_the_negative_control_binds_the_status():
    """The pre-fix spelling. If this ever stops rendering `$n`, the tests above
    no longer discriminate and need a new control."""
    sql = _asyncpg_sql(select(FuturesMarket.id).where(FuturesMarket.status == "open"))
    assert _BOUND.search(sql), sql
    assert _INLINE not in sql, sql


def test_the_gate_compile_is_byte_identical_before_and_after():
    """The latency gate compiles with `literal_binds=True`; its arm text, and its
    `no_partial` rewrite target, must not move under this change."""
    from sqlalchemy.dialects import postgresql

    def literal(clause):
        return str(
            select(FuturesMarket.id).where(clause).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )

    before = literal(FuturesMarket.status == "open")
    after = literal(FuturesMarket.status == ev._FUTURES_OPEN_STATUS_SQL)
    assert before == after
    assert "futures_markets.status = 'open'" in after
