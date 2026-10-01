"""#9947 — the /search futures OUTCOME arm reads `id = ANY(ARRAY(subquery))`, not `id IN (subquery)`.

THE DEFECT, read on production 2026-10-01 00:06-00:20Z (Deploy ffe2727c):
`ohtani` served two title-only boards on every read, `futures_outcome_arm:
budget_exceeded`, so the World Series MVP and Championship Series MVP markets
he is priced on never reached the page. #9947's first half (a 30 s TTL for such
answers) stopped one slow moment pinning that for 3 minutes; it could not help
an arm that never finished.

The arm's statement, EXPLAIN ANALYZE on production: the planner pulled the
`IN (SELECT market_id FROM futures_outcomes WHERE name ILIKE '%ohtani%')`
subquery up into the window's join and walked every open market (50,547 loops)
probing each one's outcomes, 4,640-6,345 ms against a 1,000 ms bound. The same
statement with `= ANY(ARRAY(...))` evaluates the match set once through the
trigram index and reads markets by primary key: 57-146 ms, the same twenty ids
in the same order. The IN form's plan is not stable: after `futures_outcomes`
was autoanalyzed at 00:26:21Z the same statement ran in 68-142 ms. The ARRAY
form takes that choice away from the planner.

These guards need no server (the real-Postgres half is
`tests/integration/test_search_outcome_arm_any_array_pg_9947.py`):
  * every /search outcome-arm builder renders the ARRAY form;
  * the set of call sites still using the IN form is PINNED, so a new arm
    cannot quietly bring the slow shape back;
  * the strawman: the old IN form fails the predicate the builders pass.
"""

from __future__ import annotations

import ast
import inspect
import re

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes import events as events_route

ANY_ARRAY = "= ANY (array((SELECT futures_outcomes.market_id"
IN_FORM = re.compile(r"IN \(SELECT futures_outcomes\.market_id", re.I)


def _sql(expr) -> str:
    return str(
        select(FuturesMarket.id)
        .where(expr)
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _is_array_form(sql: str) -> bool:
    return ANY_ARRAY in sql and not IN_FORM.search(sql)


class TestTheBuildersRenderTheArrayForm:
    def test_the_helper(self):
        sql = _sql(events_route._market_has_outcome(FuturesOutcome.name.ilike("%ohtani%")))
        assert _is_array_form(sql), sql

    def test_a_club_resolved_term(self):
        sql = _sql(events_route._resolved_club_outcome_match("yank", None, ["Yankees"]))
        assert _is_array_form(sql), sql

    def test_a_round_word(self):
        sql = _sql(events_route._resolved_club_outcome_match("alds", None, []))
        assert _is_array_form(sql), sql

    def test_every_term_long(self):
        sql = _sql(events_route._multi_term_outcome_match([("zelenskyy", None), ("putin", None)]))
        assert sql.count(ANY_ARRAY) == 2 and not IN_FORM.search(sql), sql

    def test_a_short_term_anchored_on_a_long_one(self):
        # `us recession`: one long term, so the anchored subquery is the whole arm
        # (#1619 — the long term's own subquery is implied by the anchor).
        sql = _sql(events_route._multi_term_outcome_match([("us", None), ("recession", None)]))
        assert sql.count(ANY_ARRAY) == 1 and not IN_FORM.search(sql), sql

    def test_a_short_term_anchored_on_two_long_ones(self):
        # `us fed rates`: one arm per long term plus the anchored subquery.
        sql = _sql(events_route._multi_term_outcome_match(
            [("us", None), ("fed", None), ("rates", None)]
        ))
        assert sql.count(ANY_ARRAY) == 3 and not IN_FORM.search(sql), sql

    def test_the_single_term_arm_inside_the_route(self):
        """`_outcome_id_match` is nested in `search_events`; read its body."""
        body = inspect.getsource(events_route.search_events)
        start = body.index("def _outcome_id_match")
        arm = body[start:body.index("\n\n", start)]
        assert "_market_has_outcome(" in arm, arm
        assert ".in_(" not in arm, arm


class TestTheInFormCallSitesArePinned:
    """Every `FuturesMarket.id.in_(select(FuturesOutcome.market_id)...)` left in
    the module, by enclosing function. Neither is a /search outcome arm:
    `_headline_contender_outcome_clause` is the contender hoist's own statement,
    and `/typeahead` already resolves its match set first (LAT-P166). A new name
    here is a new arm in the slow shape — route it through `_market_has_outcome`.
    """

    EXPECTED = {"_headline_contender_outcome_clause", "typeahead_search"}

    @staticmethod
    def _is_in_form_call(node: ast.AST) -> bool:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            return False
        if node.func.attr != "in_" or ast.unparse(node.func.value) != "FuturesMarket.id":
            return False
        return any("select(FuturesOutcome.market_id)" in ast.unparse(a) for a in node.args)

    def test_the_set(self):
        tree = ast.parse(inspect.getsource(events_route))
        funcs = [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        found = set()
        for node in ast.walk(tree):
            if self._is_in_form_call(node):
                found.add(min(
                    (f for f in funcs if f.lineno <= node.lineno <= f.end_lineno),
                    key=lambda f: f.end_lineno - f.lineno,
                ).name)
        assert found == self.EXPECTED, found


class TestTheStrawman:
    def test_the_old_in_form_fails_the_predicate(self):
        old = FuturesMarket.id.in_(
            select(FuturesOutcome.market_id).where(FuturesOutcome.name.ilike("%ohtani%"))
        )
        assert not _is_array_form(_sql(old))

    def test_the_pin_sees_an_in_form_call(self):
        call = ast.parse(
            "FuturesMarket.id.in_(select(FuturesOutcome.market_id).where(x))"
        ).body[0].value
        assert TestTheInFormCallSitesArePinned._is_in_form_call(call)
