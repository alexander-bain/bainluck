"""The typeahead outcome arm resolves its match set BEFORE it asks about markets.

LAT-P166/#2386. The companion to `test_lat_p143_typeahead_outcome_arm.py`, which
guards the statement this one now runs only as a FALLBACK.

WHAT LAT-P143 LEFT BEHIND, AND WHY IT WAS INVISIBLE.

LAT-P143 gave the arm the page's own `ORDER BY` and `LIMIT`, took `win` from
13,801 ms to 477 ms, and wrote that the 2,000 ms safety net "should essentially
never fire". Measured again on production 2026-08-31 with `EXPLAIN (ANALYZE,
BUFFERS)` on that exact statement, `%win%`:

    cache state   duration     blocks read   shared I/O read time
    cold           7,677 ms         27,338            13,132 ms
    partial        1,249 ms          1,287               402 ms
    warm             313 ms              0                 0 ms

🔴 THE PLAN DID NOT DECAY — all three runs are the same shape. What decays is
RESIDENCY. The statement touches ~35,000 buffers on every execution because the
planner drives from `ix_futures_markets_status`, materialises all **26,204** open
markets, SORTS them, and applies the outcome-name predicate LAST. The arm's cost
is therefore independent of how selective the user's query is. On a 4 GB-RAM
instance holding a 66 GB database those buffers do not stay resident, a cold
execution blows the bound, and the arm sheds — so WHICH users lose their
outcome-name suggestions is decided by cache roulette, not by their query.

It was also the largest live consumer of database time in the system: a
snapshot->wait->snapshot `pg_stat_statements` DELTA over 150 s measured 161 calls
/ 28,338 ms, ~18 % of all exec time in the window.

THE CURE. Resolve the match set first, from the trigram index, then ask
`futures_markets` about a concrete id list:

    step 1  `... WHERE name ILIKE %s LIMIT CAP+1`     12-29 ms,   62-118 blocks
    step 2  `... WHERE id = ANY(:ids) ORDER BY .. 20`    137 ms,  2,451 buffers

⚠️ **THE CAP IS ON RAW OUTCOME ROWS, AND THAT IS WHAT MAKES IT EXACT.** `LIMIT
CAP+1` is what lets step 1 terminate early — `DISTINCT` would not, because a hash
aggregate must consume its whole input before emitting anything (measured: the
`DISTINCT` form of `%win%` cost 7,053 ms for 57,282 ids). Fewer rows returned
than the limit asked for means the limit never bound, so the set IS complete.

🔴 **AND OVER THE CAP IT FALLS BACK — IT DOES NOT SKIP THE ARM.** Below the cap
the id set is complete so the result is SET-IDENTICAL; at or above it, the
statement that runs is the one that runs today. There is no input for which
recall changes, which is why this needed no product ruling. The broad-term case
is NOT fixed here and still needs its index (parked as P116-1).

This file touches no database. It asserts on the SHAPE of the statements and on
the CONTROL FLOW, both decidable without Postgres, and both invisible to any test
that only reads returned rows — deleting the probe changes no result.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes.events import (
    _TYPEAHEAD_FUTURES_POOL,
    _TYPEAHEAD_OUTCOME_PROBE_CAP,
    _resolve_typeahead_outcome_arm,
)

PATTERN = "%yan%"

#: The arm exactly as the route builds it — the fallback path's predicate.
ARM = FuturesMarket.id.in_(
    select(FuturesOutcome.market_id).where(FuturesOutcome.name.ilike(PATTERN))
)
OPEN_NOW = (FuturesMarket.status == "open",)


class FakeQueryCanceledError(Exception):
    """What asyncpg raises on `statement_timeout`, as `_is_query_timeout` sees it."""

    sqlstate = "57014"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeSession:
    """Records the statements in ORDER, which is the whole point.

    The defect this file guards is a statement that stops being issued, or two
    statements issued in the wrong order. Both are invisible to a fake that only
    returns rows, so this one keeps the sequence.
    """

    def __init__(
        self,
        probe_rows=(),
        market_rows=(),
        raise_on: int | None = None,
    ):
        self.probe_rows = probe_rows
        self.market_rows = market_rows
        self.raise_on = raise_on
        self.set_local_ms: list[int] = []
        self.statements: list[object] = []
        self.rolled_back = 0

    async def execute(self, stmt, *args, **kwargs):
        text = str(stmt)
        match = re.search(r"SET LOCAL statement_timeout = (\d+)", text)
        if match:
            self.set_local_ms.append(int(match.group(1)))
            return FakeResult([])
        self.statements.append(stmt)
        if self.raise_on is not None and len(self.statements) == self.raise_on:
            raise FakeQueryCanceledError()
        if len(self.statements) == 1 and "futures_outcomes" in text:
            return FakeResult([(rid,) for rid in self.probe_rows])
        return FakeResult([(rid,) for rid in self.market_rows])

    async def rollback(self):
        self.rolled_back += 1


def _compiled(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _paramized(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


# --------------------------------------------------------------------------- #


class TestTheProbeRunsFirstAndIsTheCheapShape:
    """Nothing else in this file matters if the probe is not issued, or is issued
    in a shape that cannot terminate early."""

    @pytest.mark.asyncio
    async def test_the_probe_is_the_first_statement(self):
        db = FakeSession(probe_rows=[7, 7, 9], market_rows=[9])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        assert len(db.statements) == 2, (
            "expected probe then market lookup, got "
            f"{len(db.statements)} statement(s). If this is 1 the probe was "
            "deleted and every keystroke is back to sorting 26,204 open markets."
        )
        first = _compiled(db.statements[0]).lower()
        assert "from futures_outcomes" in first, first
        assert "futures_markets" not in first, (
            "the FIRST statement must ask futures_outcomes alone. The moment it "
            "joins futures_markets the planner is back in charge and can choose "
            "the 26,204-row sort again."
        )

    @pytest.mark.asyncio
    async def test_the_probe_carries_limit_cap_plus_one(self):
        db = FakeSession(probe_rows=[1], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _compiled(db.statements[0]).upper()
        assert re.search(rf"LIMIT\s+{_TYPEAHEAD_OUTCOME_PROBE_CAP + 1}\b", sql), sql

    @pytest.mark.asyncio
    async def test_the_probe_has_no_distinct_or_aggregate(self):
        """`DISTINCT` reads like tidiness and costs early termination.

        A hash aggregate must consume its whole input before it emits a row, so a
        `DISTINCT` probe cannot stop at CAP+1. Measured: the `DISTINCT` form of
        `%win%` cost 7,053 ms for 57,282 ids, against 12 ms for this one. The
        dedupe belongs in Python, where it is free.
        """
        db = FakeSession(probe_rows=[1], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _compiled(db.statements[0]).upper()
        assert "DISTINCT" not in sql, sql
        assert "GROUP BY" not in sql, sql

    @pytest.mark.asyncio
    async def test_the_probe_uses_the_callers_pattern(self):
        """Fast and asking the wrong question is not a fix."""
        db = FakeSession(probe_rows=[1], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern="%cremonese%"
        )
        sql = _compiled(db.statements[0]).lower()
        assert "cremonese" in sql, sql
        assert "ilike" in sql, sql


class TestTheMarketLookupIsBoundAsOneArray:
    @pytest.mark.asyncio
    async def test_the_ids_are_one_array_bind_not_an_expanding_in_list(self):
        """One `pg_stat_statements` fingerprint however many ids it carries.

        A variable-length `IN` list generates a new entry per distinct width and
        evicts itself out of the table — which is how a statement becomes
        invisible rather than rare, and invisible is worse.
        """
        db = FakeSession(probe_rows=[5, 6, 7], market_rows=[5])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _paramized(db.statements[1])
        assert "= ANY (" in sql, sql
        assert "::INTEGER[]" in sql, sql
        assert re.search(r"IN \(__\[POSTCOMPILE", sql) is None, (
            "the id set became an expanding IN list. Same rows, but the "
            "statement now has one fingerprint per distinct id count."
        )

    @pytest.mark.asyncio
    async def test_the_market_lookup_keeps_the_p143_ordering_and_limit(self):
        """The set-identity proof is inherited, not replaced.

        `test_lat_p143_typeahead_outcome_arm.py` proves the arm's own ORDER BY and
        LIMIT are what make its top-20 the union's top-20. That proof has to hold
        on THIS branch too, or the fast path quietly returns a different page from
        the fallback for the same input.
        """
        db = FakeSession(probe_rows=[1, 2], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = " ".join(_compiled(db.statements[1]).split()).upper()
        order = sql[sql.index("ORDER BY") :]
        assert "MARKET_TIER ASC NULLS LAST" in order, order
        assert "VOLUME DESC NULLS LAST" in order, order
        assert order.index("MARKET_TIER") < order.index("VOLUME"), order
        assert re.search(rf"LIMIT\s+{_TYPEAHEAD_FUTURES_POOL}\b", sql), sql

    @pytest.mark.asyncio
    async def test_the_open_now_filters_survive(self):
        db = FakeSession(probe_rows=[1], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _compiled(db.statements[1]).lower()
        assert "status" in sql, (
            "the fast path dropped the open-market filter — it would surface "
            "settled markets in the dropdown."
        )

    @pytest.mark.asyncio
    async def test_the_ids_are_deduped_and_the_arm_predicate_is_gone(self):
        """Under the cap the subquery must NOT still be there.

        Leaving `arm` in alongside the array would be correct and pointless: the
        26,204-row sort is exactly what we are paying the probe to avoid.
        """
        db = FakeSession(probe_rows=[9, 4, 9, 4, 1], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _compiled(db.statements[1])
        assert "ARRAY[1, 4, 9]" in sql, sql
        assert "futures_outcomes" not in sql.lower(), (
            "the fallback subquery survived into the fast path, so the planner "
            "can still choose the plan this change exists to avoid."
        )


class TestTheCapFallsBackRatherThanNarrowingRecall:
    @pytest.mark.asyncio
    async def test_over_the_cap_runs_the_p143_statement(self):
        db = FakeSession(
            probe_rows=list(range(_TYPEAHEAD_OUTCOME_PROBE_CAP + 1)),
            market_rows=[1],
        )
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _compiled(db.statements[1]).lower()
        assert "futures_outcomes" in sql and "ilike" in sql, (
            "at the cap we do not know the full match set, so the only correct "
            "statement is LAT-P143's. Anything else is a recall change."
        )
        assert "array[" not in sql, sql

    @pytest.mark.asyncio
    async def test_exactly_at_the_cap_is_still_the_fast_path(self):
        """CAP rows returned means the CAP+1 limit never bound: the set is complete.

        The off-by-one here is the difference between a correct completeness test
        and one that silently drops the largest servable match set.
        """
        db = FakeSession(
            probe_rows=list(range(_TYPEAHEAD_OUTCOME_PROBE_CAP)),
            market_rows=[1],
        )
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        sql = _compiled(db.statements[1]).lower()
        assert "array[" in sql, sql
        assert "futures_outcomes" not in sql, sql

    @pytest.mark.asyncio
    async def test_no_pattern_keeps_the_old_single_statement_path(self):
        """The pre-LAT-P166 call signature must still mean the old behaviour."""
        db = FakeSession(market_rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        assert len(db.statements) == 1, db.statements
        assert "futures_outcomes" in _compiled(db.statements[0]).lower()


class TestTheEmptyAndShedStatesStayDistinct:
    @pytest.mark.asyncio
    async def test_no_match_returns_empty_list_without_a_second_query(self):
        db = FakeSession(probe_rows=[], market_rows=[])
        got = await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        assert got == [], got
        assert len(db.statements) == 1, (
            "the arm matched nothing, so there is no id set to look up and the "
            "second statement is pure waste."
        )

    @pytest.mark.asyncio
    async def test_a_probe_timeout_sheds_and_recovers_the_session(self):
        """`[]` and `None` are different answers to the caller and must stay so.

        On a timeout the transaction is aborted, so the caller's later queries all
        fail unless the session is recovered here.
        """
        db = FakeSession(probe_rows=[1], market_rows=[1], raise_on=1)
        got = await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        assert got is None, got
        assert db.rolled_back >= 1, "the poisoned session was not recovered"

    @pytest.mark.asyncio
    async def test_a_market_lookup_timeout_also_sheds(self):
        db = FakeSession(probe_rows=[1, 2], market_rows=[1], raise_on=2)
        got = await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        assert got is None, got
        assert db.rolled_back >= 1

    @pytest.mark.asyncio
    async def test_both_statements_run_under_the_existing_bound(self):
        """The safety net still wraps BOTH statements, not just the second."""
        db = FakeSession(probe_rows=[1], market_rows=[1])
        await _resolve_typeahead_outcome_arm(
            db, ARM, OPEN_NOW, None, pattern=PATTERN
        )
        assert db.set_local_ms, (
            "SET LOCAL statement_timeout is gone — a cold probe could now run "
            "unbounded and blow the request deadline instead of shedding."
        )


class TestTheRouteActuallyPassesThePattern:
    def test_the_call_site_passes_the_pattern(self):
        """A default of `None` means a caller that forgets it silently gets the
        slow path and no test fails — so the call site is asserted directly."""
        import inspect

        from app.routes.events import typeahead_search

        src = inspect.getsource(typeahead_search)
        call = re.search(
            r"_resolve_typeahead_outcome_arm\((.*?)\)", src, re.S
        )
        assert call is not None, "the resolver is no longer called by the route"
        assert "pattern=" in call.group(1), (
            "the route stopped passing `pattern`, so every typeahead request "
            "falls back to the 26,204-row sort while this suite stays green."
        )
