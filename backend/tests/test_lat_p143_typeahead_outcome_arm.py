"""The typeahead outcome arm carries the page's ORDER BY and LIMIT — LAT-P143/#1866.

WHAT BROKE, AND WHY IT SURVIVED TWELVE DAYS OF BEING LOGGED.

`typeahead futures TIMED OUT` fired **43 times in 24 hours** on production
(2026-08-30), on `yan`, `sta`, `chi`, `stan`, `win`, `winner`, `lakers`, `mas`,
`cel` — the prefixes of `yankees`, `chicago`, `stanford` and `masters winner`.
Every one of those requests took **10.03-10.26 s** (the request deadline, to the
millisecond) and answered with **no futures suggestions at all**.

The cost was ONE arm. `EXPLAIN (ANALYZE, BUFFERS)` on `futures_outcomes`
(3.9 M rows / 3,478 MB) for `q=yan`: the GIN produced 31,081 candidates in 63 ms,
and the **heap fetch of 24,806 rows cost 18,424 blocks and 6,115 ms** — of which
**97 % belong to CLOSED markets** and are discarded by the very next join.

🔴 THE FIX IS THE `ORDER BY` AND THE `LIMIT`, AND THAT IS THE WHOLE POINT OF THIS
FILE. Inside the UNION the planner could not see that only 20 rows are ever
wanted, so it materialised the entire match set. Pulled out as its own statement
carrying the page's own ordering, early termination becomes profitable and the
planner walks `futures_markets` in `(market_tier, volume)` order probing
`futures_outcomes` per candidate instead. Measured, same statement, ORDER BY +
LIMIT the only difference:

    term         blocks OLD -> NEW        time OLD -> NEW
    win           273,637 -> 35,199      13,801 ms ->   477 ms    (29x)
    yan            47,819 -> 30,476       5,771 ms ->   520 ms    (11x)
    cremonese       1,196 ->    834         241 ms ->  16.6 ms  (14.5x)
    zzqx (no hit)      15 ->     18         6.6 ms -> 0.25 ms

⚠️ **DELETING EITHER CLAUSE CHANGES NO RESULT AND RESTORES A 13.8-SECOND QUERY.**
That is the failure mode this file exists for. `LIMIT 20` on a subquery whose
caller already applies `LIMIT 20` reads like redundancy; `ORDER BY` on a
set-membership arm reads like a leftover. A later reader deletes one in good
faith, every test that asserts on ROWS stays green, and the defect is back with
no signal. So the load-bearing assertions here read the compiled SQL and the
route's own source, not the returned rows.

WHY THE TWO LIMITS MUST BE ONE CONSTANT. The caller UNIONs every arm and takes
the top `_TYPEAHEAD_FUTURES_POOL` of the union by the same ordering. Any market
this arm drops has `_TYPEAHEAD_FUTURES_POOL` markets from this same arm ordered
ahead of it, all of which are in the union, so it could not have reached the
union's top `_TYPEAHEAD_FUTURES_POOL` either — the final page is identical. That
proof holds only while the two limits are the SAME number, so they are the same
NAME, and `TestTheSetIdentityProofHolds` fails if they ever stop being.

This file touches no database and asserts no timings: a timing assertion against
a planner whose choice moves with table statistics is a flake, and the production
numbers are banked in the constant's docstring instead.
"""

from __future__ import annotations

import ast
import inspect
import re

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes import events as events_mod
from app.routes.events import (
    _SEARCH_MIN_STAGE_TIMEOUT_MS,
    _TYPEAHEAD_FUTURES_POOL,
    _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS,
    _is_query_timeout,
    _resolve_typeahead_outcome_arm,
    typeahead_search,
)

PATTERN = "%yan%"

#: The arm exactly as the route builds it.
ARM = FuturesMarket.id.in_(
    select(FuturesOutcome.market_id).where(FuturesOutcome.name.ilike(PATTERN))
)
OPEN_NOW = (FuturesMarket.status == "open",)


# --------------------------------------------------------------------------- #
# Fakes. No database: this suite is about the SHAPE of the statement and the
# CONTROL FLOW around it, both of which are decidable without Postgres.
# --------------------------------------------------------------------------- #


class FakeQueryCanceledError(Exception):
    """What asyncpg raises on `statement_timeout`, as `_is_query_timeout` sees it."""

    sqlstate = "57014"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeSession:
    """Records every statement, and can be told to blow up on the arm query.

    `set_local` is captured separately from `arm` because "did it bound the
    statement" and "what statement did it bound" are two different assertions and
    a test that conflates them cannot tell a missing bound from a missing query.
    """

    def __init__(self, rows=(), raise_on_arm: Exception | None = None):
        self.rows = rows
        self.raise_on_arm = raise_on_arm
        self.set_local_ms: list[int] = []
        self.arm_statements: list[object] = []
        self.rolled_back = 0

    async def execute(self, stmt, *args, **kwargs):
        text = str(stmt)
        match = re.search(r"SET LOCAL statement_timeout = (\d+)", text)
        if match:
            self.set_local_ms.append(int(match.group(1)))
            return FakeResult([])
        self.arm_statements.append(stmt)
        if self.raise_on_arm is not None:
            raise self.raise_on_arm
        return FakeResult([(rid,) for rid in self.rows])

    async def rollback(self):
        self.rolled_back += 1


def _compiled(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _route_source() -> str:
    return inspect.getsource(typeahead_search)


def _resolver_source() -> str:
    return inspect.getsource(_resolve_typeahead_outcome_arm)


# --------------------------------------------------------------------------- #


class TestTheOrderByAndLimitAreOnTheStatement:
    """The plan flip. Nothing else in this file matters if these two fail."""

    @pytest.mark.asyncio
    async def test_the_arm_statement_carries_an_order_by(self):
        db = FakeSession(rows=[1, 2])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        sql = _compiled(db.arm_statements[0])
        assert "ORDER BY" in sql.upper(), (
            "the outcome arm lost its ORDER BY. Results are unchanged and the "
            "query is back to 13,801 ms on `win` — the ordering is what makes "
            "early termination profitable. See this module's docstring."
        )

    @pytest.mark.asyncio
    async def test_the_order_by_is_the_page_ordering_including_the_null_rules(self):
        db = FakeSession(rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        sql = " ".join(_compiled(db.arm_statements[0]).split()).upper()
        order = sql[sql.index("ORDER BY") :]
        assert "MARKET_TIER ASC NULLS LAST" in order, order
        assert "VOLUME DESC NULLS LAST" in order, order
        assert order.index("MARKET_TIER") < order.index("VOLUME"), (
            "tier must outrank volume, exactly as the final page orders. A "
            "different ordering here is a DIFFERENT top-20 and the set-identity "
            "proof in the docstring no longer holds."
        )

    @pytest.mark.asyncio
    async def test_the_arm_statement_carries_a_limit(self):
        db = FakeSession(rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        sql = _compiled(db.arm_statements[0]).upper()
        assert "LIMIT" in sql, (
            "the outcome arm lost its LIMIT. Without it the planner cannot "
            "terminate early and rebuilds the whole match set."
        )

    @pytest.mark.asyncio
    async def test_the_limit_is_the_pool_constant_not_a_literal(self):
        db = FakeSession(rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        sql = _compiled(db.arm_statements[0])
        assert re.search(rf"LIMIT\s+{_TYPEAHEAD_FUTURES_POOL}\b", sql.upper()), sql

    @pytest.mark.asyncio
    async def test_the_arm_predicate_survives_the_rewrite(self):
        """Fast, ordered and WRONG is not a fix. The arm must still be the arm."""
        db = FakeSession(rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        sql = _compiled(db.arm_statements[0]).lower()
        assert "futures_outcomes" in sql, sql
        assert "ilike" in sql or "~~*" in sql, sql
        assert "yan" in sql, sql

    @pytest.mark.asyncio
    async def test_the_open_now_filters_are_pushed_into_the_arm(self):
        db = FakeSession(rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        sql = _compiled(db.arm_statements[0]).lower()
        assert "status" in sql and "open" in sql, (
            "the arm must be filtered to open markets in its OWN statement — the "
            "ordering walk is only cheap because it walks the open set."
        )


class TestTheSetIdentityProofHolds:
    """The two limits are one constant, or the final page is not the same page."""

    def test_the_pool_constant_is_used_by_the_final_query(self):
        src = _route_source()
        assert ".limit(_TYPEAHEAD_FUTURES_POOL)" in src, (
            "the final futures query stopped using the shared pool constant. If "
            "the two limits drift apart the arm can drop a market the union's "
            "top-N would have kept — a silent recall change."
        )

    def test_the_pool_constant_is_used_by_the_arm(self):
        assert ".limit(_TYPEAHEAD_FUTURES_POOL)" in _resolver_source()

    def test_the_final_futures_query_has_no_bare_limit_literal(self):
        """A re-introduced `.limit(20)` would look right and break the proof."""
        src = _route_source()
        futures_block = src[src.index("futures_query = ") :]
        futures_block = futures_block[: futures_block.index("_ta_mark(\"futures_query")]
        assert ".limit(20)" not in futures_block, futures_block

    def test_the_pool_is_a_positive_int(self):
        assert isinstance(_TYPEAHEAD_FUTURES_POOL, int)
        assert _TYPEAHEAD_FUTURES_POOL > 0


class TestTheArmIsHeldBackFromTheUnion:
    """The render, not the helper: the route must actually route through it."""

    def test_the_route_calls_the_resolver(self):
        assert "_resolve_typeahead_outcome_arm(" in _route_source()

    def test_the_route_does_not_append_the_outcome_arm_straight_into_the_union(self):
        """The pre-LAT-P143 shape, which is what a revert looks like."""
        src = _route_source()
        appended = re.search(
            r"ta_futures_where\.append\(\s*FuturesMarket\.id\.in_\(\s*select\(\s*"
            r"FuturesOutcome\.market_id",
            src,
        )
        assert appended is None, (
            "the outcome arm is back in the UNION directly. Inside the UNION the "
            "planner cannot see the LIMIT and the 13.8 s plan returns."
        )

    def test_the_resolved_ids_are_folded_in_as_a_plain_id_list(self):
        assert "FuturesMarket.id.in_(_ta_outcome_ids)" in _route_source()

    def test_the_arm_is_still_gated_on_an_extractable_trigram(self):
        """LAT-P010/LAT-P013's skip must not have been lost in the move."""
        src = _route_source()
        assert "_has_extractable_trigram(_ta_q_compact)" in src
        gate = src.index("_has_extractable_trigram(_ta_q_compact)")
        assert "_ta_outcome_arm = FuturesMarket.id.in_(" in src[gate : gate + 400]


class TestTheBoundIsAnActualBound:
    @pytest.mark.asyncio
    async def test_a_statement_timeout_is_set_before_the_arm_runs(self):
        db = FakeSession(rows=[1])
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        assert db.set_local_ms, "the arm ran with no statement_timeout at all"

    @pytest.mark.asyncio
    async def test_the_bound_is_the_arm_budget_when_the_deadline_is_far_away(self):
        db = FakeSession(rows=[1])
        far = events_mod.time.monotonic() + 3600
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, far)
        assert db.set_local_ms[0] == _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS

    @pytest.mark.asyncio
    async def test_the_bound_never_outlives_the_request_deadline(self, monkeypatch):
        """An arm bound larger than what is left of the request is no bound.

        🔴 THE CLAMP CANNOT BIND AT TODAY'S CONSTANTS, and that is why this test
        moves one. `_SEARCH_MIN_STAGE_TIMEOUT_MS` and
        `_TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS` are both 2,000, so any request with
        enough time left to START the arm has enough left to give it the full
        budget — below that it sheds. The clamp is therefore a guard against the
        two constants drifting apart, not a live branch, and a test that asserted
        it fires at the shipped values would be asserting something false. Raising
        the budget is the only way to exercise the code that protects the deadline
        if someone raises it for real.
        """
        monkeypatch.setattr(
            events_mod, "_TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS", 8000, raising=True
        )
        db = FakeSession(rows=[1])
        near = events_mod.time.monotonic() + 3.0
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, near)
        assert db.set_local_ms[0] < 8000, (
            "the arm took its own budget instead of the time actually remaining — "
            "it would blow the request deadline it is supposed to protect."
        )
        assert 2500 <= db.set_local_ms[0] <= 3000

    def test_the_arm_budget_is_at_least_the_stage_floor(self):
        """Below the floor the arm could never run at all — it would always shed."""
        assert _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS >= _SEARCH_MIN_STAGE_TIMEOUT_MS

    @pytest.mark.asyncio
    async def test_below_the_floor_it_sheds_without_touching_the_database(self):
        """Never start a statement you already intend to cancel."""
        db = FakeSession(rows=[1])
        spent = events_mod.time.monotonic() + (_SEARCH_MIN_STAGE_TIMEOUT_MS - 500) / 1000
        assert await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, spent) is None
        assert db.arm_statements == []
        assert db.set_local_ms == []

    @pytest.mark.asyncio
    async def test_an_expired_deadline_sheds_rather_than_going_negative(self):
        db = FakeSession(rows=[1])
        past = events_mod.time.monotonic() - 5
        assert await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, past) is None
        assert db.arm_statements == []

    def test_the_arm_budget_is_env_tunable(self):
        src = inspect.getsource(events_mod)
        assert 'os.getenv("TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS"' in src

    def test_the_arm_budget_is_well_under_the_request_deadline(self):
        assert (
            _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS < events_mod._TYPEAHEAD_DEADLINE_MS
        ), (
            "an arm budget at or above the request deadline sheds nothing early — "
            "the request would blow the deadline first, which is the defect."
        )


class TestSheddingIsNarrowAndHonest:
    @pytest.mark.asyncio
    async def test_a_timeout_returns_none_rather_than_an_empty_list(self):
        """`[]` means 'matched nothing'. `None` means 'could not answer'."""
        db = FakeSession(raise_on_arm=FakeQueryCanceledError("canceling statement"))
        assert await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None) is None

    @pytest.mark.asyncio
    async def test_a_timeout_recovers_the_session(self):
        """The caller runs more queries; all of them fail on a poisoned session."""
        db = FakeSession(raise_on_arm=FakeQueryCanceledError("canceling statement"))
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)
        assert db.rolled_back == 1

    @pytest.mark.asyncio
    async def test_a_non_timeout_error_is_re_raised(self):
        """A real bug must not be laundered into a quietly narrower dropdown."""
        db = FakeSession(raise_on_arm=ValueError("a genuine bug"))
        with pytest.raises(ValueError):
            await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None)

    @pytest.mark.asyncio
    async def test_the_fake_timeout_is_what_the_route_calls_a_timeout(self):
        """Guards the fake itself: a wrong fake makes every test above vacuous."""
        assert _is_query_timeout(FakeQueryCanceledError("x")) is True
        assert _is_query_timeout(ValueError("x")) is False

    @pytest.mark.asyncio
    async def test_a_successful_arm_returns_plain_ints(self):
        db = FakeSession(rows=[7, 9, 11])
        assert await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None) == [7, 9, 11]

    @pytest.mark.asyncio
    async def test_no_match_returns_an_empty_list_not_none(self):
        db = FakeSession(rows=[])
        assert await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, None) == []


class TestTheRouteHandlesTheThreeAnswersDifferently:
    """`None`, `[]` and a populated list are three outcomes, not two."""

    @staticmethod
    def _shed_branch() -> str:
        src = _route_source()
        start = src.index("if _ta_outcome_ids is None:")
        return src[start : src.index("_ta_arm_selects = [")]

    def test_shedding_marks_the_answer_shed(self):
        """AMENDED BY LAT-P241/#3399, and the amendment is the point.

        This used to assert `_ta_degraded = True`, which made a shed answer
        uncacheable. Measured on production: the shed is a deterministic property
        of the TERM (5/5 or 0/5 across 35 trials, 7 terms), so there was never a
        fuller answer for the cached one to displace — the rule bought nothing
        and cost four head terms 4-8s on every keystroke, permanently. The shed
        now sets its OWN flag; the futures-stage timeout keeps `_ta_degraded`.
        """
        assert "_ta_outcome_arm_shed = True" in self._shed_branch()
        assert "_ta_degraded = True" not in self._shed_branch(), (
            "the bonus outcome-name lane must not set the futures-stage flag — "
            "that is the conflation LAT-P241 removed"
        )

    def test_a_futures_stage_timeout_is_still_never_cached(self):
        """LAT-P007's rule, for the case it was actually written for.

        LAT-P241 narrowed WHAT counts as degraded; it did not weaken this. A
        `futures_query_TIMED_OUT` loses the whole futures stage and still gates
        the write.
        """
        src = _route_source()
        assert "if not _ta_degraded and not debug_evidence and not debug_timing:" in src
        to_branch = src[src.index('_ta_mark("futures_query_TIMED_OUT")'):]
        assert "_ta_degraded = True" in to_branch[:800], (
            "the futures-stage timeout must still mark the answer degraded"
        )

    def test_an_empty_arm_marks_neither_flag(self):
        """Matching no open market is a COMPLETE answer, and must stay cacheable."""
        src = _route_source()
        block = src[src.index("if _ta_outcome_ids is None:") : src.index("_ta_arm_selects = [")]
        else_branch = block[block.index("else:") :]
        assert "_ta_degraded" not in else_branch, else_branch
        assert "_ta_outcome_arm_shed" not in else_branch, else_branch

    def test_shedding_logs_what_the_user_actually_lost(self):
        branch = self._shed_branch()
        assert "logger.error" in branch
        assert "SHED" in branch

    def test_the_shed_log_says_what_SURVIVED_not_only_what_was_lost(self):
        """The pre-LAT-P143 message said 'without its futures suggestions' and
        meant ALL of them. The narrower shed must not inherit that wording."""
        branch = self._shed_branch()
        assert "ticker" in branch and "alias" in branch, branch


class TestStageAttributionIsNotDoubleMarked:
    """`_ta_mark` resets its clock, so two marks in a row attribute ~0 ms."""

    @staticmethod
    def _arm_block() -> str:
        src = _route_source()
        return src[
            src.index("if _ta_outcome_arm is not None:") : src.index("_ta_arm_selects = [")
        ]

    def test_success_and_shed_are_distinct_labels(self):
        block = self._arm_block()
        assert '_ta_mark("futures_outcome_arm")' in block
        assert '_ta_mark("futures_outcome_arm_SHED")' in block

    def test_exactly_one_mark_fires_on_each_path(self):
        block = self._arm_block()
        tree = ast.parse(textwrap_dedent(block))
        marks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_ta_mark"
        ]
        assert len(marks) == 2, (
            f"expected exactly two _ta_mark calls (one per branch), found {len(marks)}. "
            "Two marks on ONE path attribute the arm's whole cost to the label "
            "that says it succeeded."
        )

    def test_events_assemble_is_marked_before_the_arm_runs(self):
        """Otherwise the arm's whole duration is buried inside events_assemble."""
        src = _route_source()
        assert src.index('_ta_mark("events_assemble")') < src.index(
            "_resolve_typeahead_outcome_arm("
        )

    def test_events_assemble_is_marked_exactly_once(self):
        assert _route_source().count('_ta_mark("events_assemble")') == 1


def textwrap_dedent(block: str) -> str:
    import textwrap

    return textwrap.dedent(block)
