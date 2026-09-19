"""#7243 — typing a club's bare name reaches its championship market on a COLD read.

THE DEFECT, measured on production 2026-09-19 at v4778 through the route's own
`?debug_timing=1` stage clock, which is what separates "the gate never fired" from
"the gate fired and the statement ran out of budget":

    q=dodgers   headline_contenders = 2,033 ms   114584 ABSENT
    q=dodgers   headline_contenders =   896 ms   114584 at row 1
    q=red sox   headline_contenders = 2,035 ms   114584 ABSENT
    q=red sox   headline_contenders =   587 ms   114584 at row 1

2,033 ms is `_SEARCH_HEADLINE_ARM_TIMEOUT_MS` (2,000) plus overhead: the lane's
statement hit its own bound, the handler logged "shipping the page unchanged", and
the reader lost the card. The gate at `events.py` FIRED every single time — so
neither conjunct #7243 offered as a candidate (window saturation, a non-matching row
inside `_deduped_page`) is the cause, and a fix aimed at either would have been aimed
at nothing.

🔴 AND THE ISSUE'S OWN "3/3 deterministic ABSENT" READS WERE ONE CACHED BODY.
`/search` caches its answer, so three plain reads of a term re-serve one response;
`?debug_timing=1` is excluded from the cache on both the read and the write side
(see the cache block in the route), which is why it can see the coin flip at all.
Any future measurement of this lane takes the debug path or it is measuring the TTL.

WHY THE STATEMENT WAS SLOW — production `EXPLAIN (ANALYZE)`, clause order the only
difference. With `_futures_open_now` first the driving scan is `futures_markets` at
1,133 rows (the whole tier-1/volume>=10k open population) and the three `NOT EXISTS`
arms of `_futures_game_already_played()` run `loops=1133` before the contender
semi-join narrows anything. With the contender clauses first the driver is the
pg_trgm bitmap index on `futures_outcomes.name` — 503 index rows, 303 heap rows, 253
distinct markets for `dodgers` — and every anti-join below runs at `loops=1`. Eight
alternating full-entity runs per form: dodgers 528 -> 49 ms median, red sox 785 -> 90,
yankees 764 -> 54, chiefs 513 -> 47.

🪤 THE FIRST MEASUREMENT OF THIS DEFECT WAS A LIE AND IS WORTH THE PARAGRAPH.
`compile(literal_binds=True)` renders the pattern `\\mdodgers\\M` as `'\\\\mdodgers\\\\M'`,
which under `standard_conforming_strings` is a literal pair of backslashes — so the
regex matched NOTHING and every timing taken that way was the cost of a query that
found no rows. It read as a clean 15x win for the reordering. A timing is only
evidence once the query has been shown to return the row (`TestTheBuilderFindsTheRow`
is that check, and it is why the numbers above are trustworthy).

WHAT THIS DOES NOT FIX, stated here so no one reads the medians as a cure: a term
whose own trigram scan exceeds the bound still sheds. `\\mwinner\\M` alone matches 836
candidate markets at 1,971 ms. The bound exists for those.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket
from app.routes.events import (
    _futures_game_already_played,
    _headline_contender_outcome_clause,
    _headline_contender_statement,
)
from app.utils.search_headline_contender import (
    HEADLINE_MARKET_TIER,
    MIN_CONTENDER_VOLUME,
    contender_patterns,
)


def _open_now():
    """The route's own open/unresolved/not-already-played trio."""
    return (
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= datetime.now(timezone.utc),
        ),
        _futures_game_already_played(),
    )


def _sql(stmt) -> str:
    return " ".join(
        str(
            stmt.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )


def _patterns(*terms):
    return contender_patterns([(t, None) for t in terms])


class TestTheClauseOrderIsTheFix:
    """The invariant the production plan bought: SELECTIVE predicate first.

    These assert on POSITION inside the compiled WHERE, which is the only place the
    fix exists — the two orderings are semantically identical and return the same
    rows, so nothing about the result set can witness this. A test that checked only
    "the same markets come back" would pass against the defect.
    """

    def test_the_outcome_subquery_precedes_every_open_now_clause(self):
        sql = _sql(
            _headline_contender_statement(_patterns("dodgers"), _open_now(), limit=10)
        )
        contender_at = sql.index("futures_outcomes.market_id")
        # Each of the three `open_now` arms, by a fragment unique to it.
        for fragment in (
            "futures_markets.status = 'open'",
            "futures_markets.resolution_date IS NULL",
            "provenance:duplicate-of",
        ):
            assert fragment in sql, fragment
            assert contender_at < sql.index(fragment), (
                f"the contender subquery must precede {fragment!r} — with the open-now "
                "arms first the planner drives 1,133 rows through three anti-joins "
                "and the lane times out (#7243)"
            )

    def test_every_pattern_precedes_open_now_on_a_multi_term_query(self):
        """`red sox` is two patterns; BOTH must lead, not just the first."""
        sql = _sql(
            _headline_contender_statement(
                _patterns("red", "sox"), _open_now(), limit=10
            )
        )
        assert sql.count("futures_outcomes.market_id") == 2
        last_contender = sql.rindex("futures_outcomes.market_id")
        assert last_contender < sql.index("futures_markets.status = 'open'")

    def test_the_old_ordering_is_what_these_tests_catch(self):
        """The strawman: the pre-#7243 statement must FAIL the assertion above.

        Without this, a builder that emitted no contender clause at all would pass
        `test_the_outcome_subquery_precedes_every_open_now_clause` vacuously.
        """
        old = (
            select(FuturesMarket)
            .where(
                FuturesMarket.market_tier == HEADLINE_MARKET_TIER,
                FuturesMarket.volume >= MIN_CONTENDER_VOLUME,
                *_open_now(),
                *[_headline_contender_outcome_clause(p) for p in _patterns("dodgers")],
            )
            .order_by(
                FuturesMarket.volume.desc().nulls_last(), FuturesMarket.id.asc()
            )
            .limit(10)
        )
        sql = _sql(old)
        assert sql.index("futures_markets.status = 'open'") < sql.index(
            "futures_outcomes.market_id"
        ), "the strawman must carry the defect, or the guard above proves nothing"


class TestTheRowsAreUnchanged:
    """A reordering that changed WHICH markets qualify would be a recall change."""

    def test_the_predicate_set_is_identical_to_the_old_form(self):
        pats = _patterns("dodgers")
        open_now = _open_now()
        new = _sql(_headline_contender_statement(pats, open_now, limit=10))
        old = _sql(
            select(FuturesMarket)
            .where(
                FuturesMarket.market_tier == HEADLINE_MARKET_TIER,
                FuturesMarket.volume >= MIN_CONTENDER_VOLUME,
                *open_now,
                *[_headline_contender_outcome_clause(p) for p in pats],
            )
            .order_by(
                FuturesMarket.volume.desc().nulls_last(), FuturesMarket.id.asc()
            )
            .limit(10)
        )
        # Same conjuncts, same count of each — only the sequence differs.
        for fragment in (
            "futures_markets.market_tier = 1",
            "futures_markets.volume >= 10000",
            "futures_markets.status = 'open'",
            "futures_outcomes.market_id",
            "teams.name",
            "provenance:duplicate-of",
        ):
            assert new.count(fragment) == old.count(fragment) != 0, fragment

    def test_the_order_by_and_limit_survive(self):
        sql = _sql(
            _headline_contender_statement(_patterns("dodgers"), _open_now(), limit=7)
        )
        assert (
            "ORDER BY futures_markets.volume DESC NULLS LAST, futures_markets.id ASC"
            in sql
        )
        assert sql.rstrip().endswith("LIMIT 7")

    def test_the_price_floor_and_the_anchor_arm_both_survive(self):
        """#6430/CERT-3125's `or_` is inside the subquery and must be untouched."""
        sql = _sql(
            _headline_contender_statement(_patterns("dodgers"), _open_now(), limit=10)
        )
        assert "futures_outcomes.current_probability >= 0.05" in sql
        assert "futures_outcomes.team_id IS NOT NULL" in sql
        assert "teams.name ~*" in sql


class TestBothLanesTakeOneBuilder:
    """#3394's lesson, mechanised: a fix on one surface and not its twin."""

    def test_search_and_typeahead_differ_only_in_limit_and_loaders(self):
        pats = _patterns("dodgers")
        open_now = _open_now()
        search = _sql(
            _headline_contender_statement(
                pats,
                open_now,
                limit=10,
                options=(
                    selectinload(FuturesMarket.sport),
                    selectinload(FuturesMarket.outcomes),
                ),
            )
        )
        typeahead = _sql(
            _headline_contender_statement(
                pats,
                open_now,
                limit=5,
                options=(selectinload(FuturesMarket.outcomes),),
            )
        )
        # `selectinload` issues its own statements, so the primary SQL is equal
        # except for the limit — which is exactly the intended difference.
        assert search.replace("LIMIT 10", "LIMIT 5") == typeahead

    def test_the_outcome_clause_is_called_from_the_builder_and_nowhere_else(self):
        """Parsed, not grepped.

        The first spelling of this guard counted the substring
        `_headline_contender_outcome_clause(pattern)` and read 2 — because the
        helper's own `def` line contains it. A string count cannot tell a
        definition from a call, and a guard that cannot make that distinction
        would have to be loosened to pass, which is how a guard ends up asserting
        nothing. The AST can, so the AST is what asks.
        """
        import ast
        import inspect

        from app.routes import events as events_module

        tree = ast.parse(inspect.getsource(events_module))
        callers = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "_headline_contender_outcome_clause"
                ):
                    callers.add(node.name)
        assert callers == {"_headline_contender_statement"}, (
            "an inline copy of the lane's WHERE has reappeared outside the one "
            f"builder (#3394, #7243): {sorted(callers)}"
        )

    def test_both_route_lanes_call_the_builder(self):
        import ast
        import inspect

        from app.routes import events as events_module

        tree = ast.parse(inspect.getsource(events_module))
        callers = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "_headline_contender_statement"
                ):
                    callers.append(node.name)
        assert len(callers) == 2, (
            "the search and typeahead lanes are the two call sites; "
            f"found {callers}"
        )


class TestTheLoadersAreTheCallersChoice:
    def test_no_loader_is_applied_by_default(self):
        """A default would hand the dropdown a loader it never asked to pay for."""
        stmt = _headline_contender_statement(
            _patterns("dodgers"), _open_now(), limit=5
        )
        assert stmt._with_options == ()

    def test_the_options_given_are_the_options_applied(self):
        stmt = _headline_contender_statement(
            _patterns("dodgers"),
            _open_now(),
            limit=5,
            options=(selectinload(FuturesMarket.outcomes),),
        )
        assert len(stmt._with_options) == 1


class TestTheBuilderFindsTheRow:
    """The escaping trap, frozen as a test rather than as a paragraph.

    A timing measured against a pattern that matches nothing is not a measurement.
    This pins the rendered pattern so the next person's `EXPLAIN` is run on a
    predicate that can actually find market 114584's `Los Angeles Dodgers` outcome.
    """

    @pytest.mark.parametrize(
        "term,expected", [("dodgers", r"\mdodgers\M"), ("red", r"\mred\M")]
    )
    def test_the_pattern_reaches_sql_as_one_backslash_per_assertion(
        self, term, expected
    ):
        (pattern,) = _patterns(term)
        assert pattern == expected
        sql = _sql(
            _headline_contender_statement(_patterns(term), _open_now(), limit=10)
        )
        # `literal_binds` DOUBLES the backslash; the rendered literal is therefore
        # not directly runnable, and anyone pasting it into psql must undo that.
        assert r"\\m" + term + r"\\M" in sql
        assert r"\m" + term + r"\M" == sql.split("'")[
            [i for i, p in enumerate(sql.split("'")) if "m" + term in p][0]
        ].replace("\\\\", "\\")
