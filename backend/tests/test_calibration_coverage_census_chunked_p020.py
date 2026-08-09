"""CAL-P020 — the coverage census, chunk-scoped, so it can ride the staged path.

Queue 300D refused the census under a frozen (staged) scope outright, and the
refusal was right at the time: ``coverage_universe`` scanned EVERY resolved
priced futures outcome, so each of the 128 chunks rescanned all of it and LEFT
JOINed it against only its own slice of the population. Every out-of-chunk
outcome fell to ``market_result_unavailable``, and the summed census came out
~N times the truth with the rungs skewed — wrong in the CONFIDENT direction,
which is the one failure the 300C bridge exists to prevent.

What made that refusal untenable is CAL-P016. It switched the staged path ON
because the monolith cannot finish (ten consecutive ~22.5-minute statement
timeouts), so from 2026-08-09 the staged scope is the ONLY scope that can
publish. "Census XOR publish" had quietly become "never census" — the surface
Alex's 2026-08-02 ruling created had been made permanently unreachable by a
correct fix taken six days later.

So the split the 300D comment described is done here:

  * the universe narrows to the chunk (INNER JOIN onto the roster-scoped
    ``market_info``), additive across chunks because a market never straddles a
    chunk boundary, and
  * ``market_result_unavailable`` — the ONE rung whose members belong to no
    chunk — is counted once per generation against the unscoped ``market_info``.

**A note on what is and is not proven here.** These are statement-shape and
merge-arithmetic proofs, run offline. Full chunked-equals-monolith equivalence
needs a real Postgres executing both scopes over one seeded population; the
harness for that exists (``SEARCH_TEST_DATABASE_URL``, the
``test_search_recall_contract.py`` pattern, CI's ``postgres:15`` service) but no
Postgres runs in the agent sandbox, so writing that test blind would ship an
unrunnable gate. It is named as owed in PROGRAM-CALIBRATION-REPORT.md rather
than implied by coverage here.
"""

from __future__ import annotations

import re

import pytest

try:
    import sqlglot
except ImportError:  # pragma: no cover
    sqlglot = None

from app.tasks.precompute_calibration import (
    _calibration_population_ctes,
    _coverage_bridge_column,
    _coverage_global_rung_sql,
    _coverage_universe_cte,
    _COVERAGE_RUNG_KEYS,
    _main_futures_sql,
)
from app.utils.calibration_staged_futures import merge_futures_rows

CENSUS = "app.tasks.precompute_calibration.COVERAGE_CENSUS_ENABLED"

#: The chunk-scoped universe's join. Named once so a rename cannot make the
#: assertions below silently vacuous.
CHUNK_JOIN = "JOIN market_info mi ON mi.market_id = fo.market_id"
GLOBAL_JOIN = "JOIN futures_markets fm ON fm.id = fo.market_id"

GLOBAL_RUNG = "market_result_unavailable"


def _ladder(sql: str) -> str:
    """The rung CASE expression, extracted so the two scopes can be compared.

    Anchored to ``coverage_bridge`` rather than to the first ``CASE`` in the
    statement: the population chain is full of unrelated CASE expressions, and
    an unanchored match silently compares most of the statement instead of the
    ladder — which would make this assertion pass for the wrong reason.
    """
    start = sql.index("coverage_bridge AS (")
    match = re.search(r"CASE\n(.*?)END AS rung", sql[start:], re.DOTALL)
    assert match, "the rung ladder is not in this statement"
    return match.group(1)


@pytest.fixture
def census_on(monkeypatch):
    monkeypatch.setattr(CENSUS, True)


class TestTheSwitchIsOn:
    """Item 4. The last line of the change, and the point of the queue."""

    def test_census_ships_enabled(self):
        from app.tasks.precompute_calibration import COVERAGE_CENSUS_ENABLED

        assert COVERAGE_CENSUS_ENABLED is True

    def test_the_staged_path_declares_every_census_column_it_emits(self):
        """``merge_futures_rows`` refuses a column it was not told the KIND of.

        The census columns are declared next to the statement that emits them,
        so this pins that the two lists cannot drift apart — a cb_ column
        emitted but undeclared raises ``UndeclaredColumnError`` mid-build, and
        one declared but never emitted publishes ``None`` forever.
        """
        emitted = set(re.findall(r"AS (cb_[a-z_]+)", _main_futures_sql(frozen=True)))
        declared = {_coverage_bridge_column(key) for key in _COVERAGE_RUNG_KEYS} | {
            "cb_coverage_total",
            "cb_with_terminal_cal_price",
        }
        assert emitted == declared


class TestOneLadderTwoScopes:
    """The universe narrows; the rung ladder must not.

    Two ladders that agree today is how the census and the curve drift apart on
    the first rung anybody adds to only one of them — the C14 lesson, and the
    reason ``_COVERAGE_RUNG_PREDICATES`` already refuses rung drift against the
    contract. The scope must not become a second place that can disagree.
    """

    def test_the_rung_ladder_is_identical_in_both_scopes(self, census_on):
        assert _ladder(_main_futures_sql(frozen=True)) == _ladder(_main_futures_sql())

    def test_the_universe_is_the_only_thing_that_differs(self, census_on):
        frozen = _main_futures_sql(frozen=True)
        chunked_universe = _coverage_universe_cte(chunk_scoped=True)
        global_universe = _coverage_universe_cte(chunk_scoped=False)
        # Swap the frozen statement's universe for the global one and the two
        # statements' census halves become the same text. Anything else that
        # differed would survive this substitution and fail the assertion.
        assert chunked_universe in frozen
        rebuilt = frozen.replace(chunked_universe, global_universe)
        assert _ladder(rebuilt) == _ladder(_main_futures_sql())

    def test_every_contract_rung_is_still_counted_in_the_chunk_scope(self, census_on):
        frozen = _main_futures_sql(frozen=True)
        for key in _COVERAGE_RUNG_KEYS:
            assert _coverage_bridge_column(key) in frozen


class TestTheUniverseIsChunkScoped:
    """Item 1."""

    def test_frozen_universe_joins_the_roster_scoped_market_info(self):
        universe = _coverage_universe_cte(chunk_scoped=True)
        assert CHUNK_JOIN in universe
        # It must NOT reach futures_markets directly: that is what made it
        # global, and an inner join onto market_info already carries
        # status='resolved' plus the DataGolf-residual filter.
        assert GLOBAL_JOIN not in universe

    def test_global_universe_still_reaches_futures_markets_directly(self):
        universe = _coverage_universe_cte(chunk_scoped=False)
        assert GLOBAL_JOIN in universe
        assert CHUNK_JOIN not in universe
        # The DataGolf withholding stays a VISIBLE rung rather than an invisible
        # pre-filter — that is why the global scope does not join market_info.
        assert "fm.status = 'resolved'" in universe

    def test_the_two_scopes_select_the_same_columns(self):
        """Only the FROM changes. A column added to one scope only would make
        the chunk rows and the monolith rows different shapes."""
        cols = lambda sql: sorted(re.findall(r"AS (\w+)", sql))  # noqa: E731
        assert cols(_coverage_universe_cte(chunk_scoped=True)) == cols(
            _coverage_universe_cte(chunk_scoped=False)
        )

    def test_the_monolith_is_untouched_by_the_chunk_scoping(self, census_on):
        """``TestMonolithIsUnmoved``'s property, for the census half.

        Compared on the whole universe CTE, not on its join line: the join text
        alone also occurs in the population chain's per-market aggregates, so a
        bare substring check here would be vacuous.
        """
        monolith = _main_futures_sql()
        assert _coverage_universe_cte(chunk_scoped=False) in monolith
        assert _coverage_universe_cte(chunk_scoped=True) not in monolith


class TestTheGlobalRung:
    """Item 2 — the one rung that belongs to no chunk, counted exactly once."""

    def test_it_is_an_anti_join_against_the_unscoped_market_info(self):
        sql = _coverage_global_rung_sql()
        assert "LEFT JOIN market_info mi ON mi.market_id = cu.market_id" in sql
        assert "WHERE mi.market_id IS NULL" in sql

    def test_it_reuses_the_canonical_population_verbatim(self):
        """A hand-written second copy of the eligibility predicate is the C14
        drift, and here it would put the census and the curve on different
        definitions of an eligible market."""
        assert _calibration_population_ctes() in _coverage_global_rung_sql()

    def test_it_uses_the_global_universe_not_the_chunked_one(self):
        sql = _coverage_global_rung_sql()
        assert _coverage_universe_cte(chunk_scoped=False) in sql
        assert _coverage_universe_cte(chunk_scoped=True) not in sql

    def test_it_reports_exactly_the_three_columns_the_chunks_cannot(self):
        sql = _coverage_global_rung_sql()
        selected = set(re.findall(r"AS (cb_\w+)", sql))
        assert selected == {
            _coverage_bridge_column(GLOBAL_RUNG),
            "cb_coverage_total",
            "cb_with_terminal_cal_price",
        }

    def test_the_rung_it_carries_cannot_also_fire_inside_a_chunk(self, census_on):
        """The load-bearing non-double-count argument, pinned.

        ``market_result_unavailable``'s predicate is ``mi.market_id IS NULL``.
        Under the chunk scope every row in the universe got there BY joining
        that same ``market_info``, so the predicate is unsatisfiable and each
        chunk reports 0 — which is why adding the global count to the sum is
        exact rather than double-counting.
        """
        from app.tasks.precompute_calibration import _COVERAGE_RUNG_PREDICATES

        predicate = dict(_COVERAGE_RUNG_PREDICATES)[GLOBAL_RUNG]
        assert predicate == "mi.market_id IS NULL"
        assert CHUNK_JOIN in _coverage_universe_cte(chunk_scoped=True)


class TestTheGuardStillRefusesTheWrongThing:
    """Item 3. The refusal narrowed; it did not go away.

    Deleting it outright would leave nothing standing between a future edit that
    un-scopes the universe and a census inflated ~128x in production.
    """

    def test_an_unscoped_universe_under_a_frozen_scope_is_still_refused(
        self, monkeypatch, census_on
    ):
        # Mutation: put the OLD global universe back under the frozen scope.
        monkeypatch.setattr(
            "app.tasks.precompute_calibration._coverage_universe_cte",
            lambda *, chunk_scoped: _coverage_universe_cte(chunk_scoped=False),
        )
        with pytest.raises(ValueError, match="not chunk-scoped"):
            _main_futures_sql(frozen=True)

    def test_the_refusal_still_names_the_work(self, monkeypatch, census_on):
        monkeypatch.setattr(
            "app.tasks.precompute_calibration._coverage_universe_cte",
            lambda *, chunk_scoped: _coverage_universe_cte(chunk_scoped=False),
        )
        with pytest.raises(ValueError) as excinfo:
            _main_futures_sql(frozen=True)
        assert "coverage_universe" in str(excinfo.value)

    def test_the_real_chunk_scoped_universe_builds_without_refusal(self, census_on):
        assert "coverage_universe" in _main_futures_sql(frozen=True)


class TestDisabledIsStillAByteIdenticalNoOp:
    """The off state must keep costing the build exactly nothing."""

    def test_off_emits_no_census_in_either_scope(self, monkeypatch):
        monkeypatch.setattr(CENSUS, False)
        assert "coverage_universe" not in _main_futures_sql()
        assert "coverage_universe" not in _main_futures_sql(frozen=True)

    def test_off_never_refuses(self, monkeypatch):
        monkeypatch.setattr(CENSUS, False)
        _main_futures_sql(frozen=True)  # must not raise


def _chunk(cb: dict[str, int], *, bucket: int = 0):
    """One chunk result: a bucket row carrying its chunk's 1-row census."""
    row = {
        "bucket_idx": bucket,
        "source": "kalshi",
        "category": "politics",
        "price_moved": False,
        "is_nonexclusive_bundle": False,
        "n": 10,
        "sum_prob": 5.0,
        "winners": 4,
        "sum_sq_err": 1.0,
    }
    row.update(cb)
    return [row]


class TestTheMergeArithmeticIsExact:
    """Item 5's arithmetic half: sum over chunks + one global == the truth.

    ``merge_futures_rows`` sums census columns across chunks, so the whole
    correctness of the split reduces to "each chunk counts its own outcomes
    once, and the global rung is contributed once". Both directions are pinned
    below, including the ~Nx inflation the pre-fix scoping produced.
    """

    COLUMNS = ("cb_plotted_on_curve", f"cb_{GLOBAL_RUNG}", "cb_coverage_total")

    def test_per_chunk_counts_sum_and_the_global_rung_is_added_once(self):
        chunks = [
            _chunk({"cb_plotted_on_curve": 100, f"cb_{GLOBAL_RUNG}": 0, "cb_coverage_total": 120}),
            _chunk({"cb_plotted_on_curve": 50, f"cb_{GLOBAL_RUNG}": 0, "cb_coverage_total": 70}),
            _chunk({"cb_plotted_on_curve": 25, f"cb_{GLOBAL_RUNG}": 0, "cb_coverage_total": 30}),
        ]
        global_pass = {f"cb_{GLOBAL_RUNG}": 7, "cb_coverage_total": 7}

        merged = merge_futures_rows(
            chunks, census_columns=self.COLUMNS, extra_censuses=[global_pass]
        )

        assert len(merged) == 1
        assert merged[0].cb_plotted_on_curve == 175
        # Counted once, from the global pass alone — every chunk reported 0.
        assert getattr(merged[0], f"cb_{GLOBAL_RUNG}") == 7
        assert merged[0].cb_coverage_total == 120 + 70 + 30 + 7

    def test_the_pre_fix_scoping_inflates_by_the_chunk_count(self):
        """The defect this queue removes, pinned as arithmetic.

        Before the fix every chunk scanned the WHOLE universe, so every chunk
        reported the same global totals and the merge summed them N times. If
        anyone re-globalises the universe, the numbers move exactly like this.
        """
        whole_universe = {
            "cb_plotted_on_curve": 175,
            f"cb_{GLOBAL_RUNG}": 7,
            "cb_coverage_total": 227,
        }
        n_chunks = 4
        merged = merge_futures_rows(
            [_chunk(dict(whole_universe)) for _ in range(n_chunks)],
            census_columns=self.COLUMNS,
        )
        assert merged[0].cb_coverage_total == 227 * n_chunks
        assert getattr(merged[0], f"cb_{GLOBAL_RUNG}") == 7 * n_chunks

    def test_a_chunk_that_omits_a_census_column_does_not_vote_zero(self):
        """Unknown is not zero — the merge's own rule, relied on here because
        the global pass reports only three of the census columns."""
        merged = merge_futures_rows(
            [_chunk({"cb_plotted_on_curve": 40})],
            census_columns=self.COLUMNS,
            extra_censuses=[{f"cb_{GLOBAL_RUNG}": 7}],
        )
        assert merged[0].cb_plotted_on_curve == 40
        assert getattr(merged[0], f"cb_{GLOBAL_RUNG}") == 7
        # Nobody reported it at all: None, never 0.
        assert merged[0].cb_coverage_total is None


class TestTheGlobalPassIsWiredIntoTheStagedFinalize:
    """The statement being correct is worth nothing if nothing runs it.

    Source-level rather than behavioural: driving ``_run_staged_futures`` needs a
    runner, a cursor and a live session, and a mock deep enough to fake all
    three would mostly be asserting against itself. What matters is cheap to
    pin exactly — the pass runs once, gated, after completeness, and its row
    reaches the merge.
    """

    @staticmethod
    def _source() -> str:
        import inspect

        from app.tasks.precompute_calibration import _run_staged_futures

        return inspect.getsource(_run_staged_futures)

    def test_the_global_pass_is_executed_and_gated_on_the_switch(self):
        source = self._source()
        assert "if COVERAGE_CENSUS_ENABLED:" in source
        assert "_coverage_global_rung_sql()" in source

    def test_its_row_reaches_the_merge_as_an_extra_census(self):
        assert "extra_censuses=census_only + global_census" in self._source()

    def test_it_runs_after_the_completeness_check_not_per_unit(self):
        """An incomplete beat must never pay for it, and it must never run once
        per chunk — that would be the double count the split exists to avoid."""
        source = self._source()
        assert source.index("if not is_complete(") < source.index(
            "_coverage_global_rung_sql()"
        )
        # Inside the per-unit loop is `read:futures_unit`; the global pass must
        # come after that loop's body, not within it.
        assert source.index("read:futures_unit") < source.index(
            "read:coverage_global_rung"
        )


@pytest.mark.skipif(sqlglot is None, reason="sqlglot not installed")
class TestEveryScopeParses:
    """The only automated check on the heaviest statements in the product."""

    @pytest.mark.parametrize("frozen", [False, True])
    def test_the_census_statement_parses(self, frozen, census_on):
        sqlglot.parse_one(_main_futures_sql(frozen=frozen), read="postgres")

    def test_the_global_rung_statement_parses(self, census_on):
        sqlglot.parse_one(_coverage_global_rung_sql(), read="postgres")
