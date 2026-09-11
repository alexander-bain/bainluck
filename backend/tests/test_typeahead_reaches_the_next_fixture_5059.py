"""T2-2 (#5059): the dropdown can reach a team's NEXT fixture past the 7-day pool.

WHAT WAS BROKEN, measured on production 2026-09-11 before any code moved.
`/typeahead`'s upcoming pool is bounded at `now + 7 days`. Alex's rule for row 2
is "the live game, else the NEXT, else the last finished", and that bound deleted
the middle term for whole leagues at once:

    league   teams   next fixture <= 7d   next fixture > 7d
    NHL         32                    0                  32
    NBA         27                    0                  27
    NFL         32                   28                   4
    MLB         30                   30                   0
    EPL         18                   18                   0

Every NBA and NHL team — 59 of them — offered a reader no game whatsoever, and
#4411's or-LAST arm filled the slots with finished ones. Across all sports, 366
of the 1,560 teams with a future fixture were in that state. The Patriots
specimen in the issue is the same shape three days wide: they played Thursday
and next play in ten days, which is every Thursday-game NFL club for three days
of every week.

WHY THESE TESTS ARE SHAPED LIKE THE OR-LAST ONES. The arm is a module-level
query compiled here rather than exercised through the route, for the reason
`_last_match_query`'s guards give: the pool assembly runs against a live session,
so an arm left inline is an arm no CI job can read. What a compiled query cannot
prove is that the clause changes the ANSWER; that is the route's job and is
asserted against a real PostgreSQL in the integration suite.

THE MUTANT THIS FILE EXISTS TO KILL is not "someone deletes the arm" — it is
"someone widens the UPCOMING POOL to 120 days instead", which looks equivalent,
passes a naive recall test, and silently changes the candidate set for every
query on the endpoint. `test_the_upcoming_pool_is_still_bounded_at_a_week` is
the assertion that refuses it.
"""

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

from sqlalchemy import true

from app.routes.events import (
    _NEXT_MATCH_LOOKAHEAD_DAYS,
    _next_match_query,
    typeahead_search,
)

_NOW = datetime(2026, 9, 11, 17, 0, tzinfo=timezone.utc)


def _sql() -> str:
    q = _next_match_query(true(), _NOW)
    return str(q.compile(compile_kwargs={"literal_binds": True})).lower()


class TestTheNextMatchArmsOwnClauses:
    """The or-NEXT recall query, compiled. Every clause is load-bearing."""

    def test_it_asks_for_games_that_have_not_been_played(self):
        """The whole point: a FIXTURE, not a result.

        If this ever selects `completed`/`closed` it has become a second copy of
        the or-LAST arm, and the "else the next" term is gone again.
        """
        sql = _sql()
        assert "'scheduled'" in sql and "'live'" in sql, sql
        assert "'completed'" not in sql, "this is the or-NEXT arm, not or-LAST"
        assert "'closed'" not in sql, "this is the or-NEXT arm, not or-LAST"

    def test_it_reaches_past_the_seven_day_pool(self):
        """Otherwise the arm is the upcoming pool again and repairs nothing.

        Asserted as a real date in the compiled SQL rather than by reading the
        constant, because the constant being 120 proves nothing about whether
        the query uses it.
        """
        ceiling = (_NOW + timedelta(days=_NEXT_MATCH_LOOKAHEAD_DAYS)).isoformat(sep=" ")
        assert ceiling in _sql(), f"expected a {ceiling} ceiling in:\n{_sql()}"

    def test_it_is_still_ceilinged(self):
        """gotcha #41 wants BOTH ends.

        Unbounded, a dissolved club answers with a fixture from a season nobody
        is asking about — the forward-facing twin of the retired-player case the
        or-LAST arm's floor exists for.
        """
        assert "commence_time <=" in _sql()

    def test_it_is_floored_at_the_upcoming_pools_own_floor(self):
        """A strict superset of the upcoming pool IN TIME, deliberately.

        The floor is `now - 1h`, not `now`, so a game that kicked off forty
        minutes ago cannot fall between this arm (which would want `> now`) and
        the pool it backs up. A floor of `now` would open exactly that hole for
        live games, which are the rows this endpoint least wants to lose.

        🔴 ASSERTED TO THE HOUR, and that is the whole test. The first version
        of this compared `(_NOW - timedelta(hours=1)).date().isoformat()` — but
        16:00 and 17:00 on the same day truncate to the SAME DATE, so the guard
        threw away the one hour it exists to protect. Mutating the floor to
        `now` left it green. Gotcha #44's shape, one field over: offset first,
        then truncate — and if you truncate past the unit you are asserting,
        you have written a test about the calendar.
        """
        sql = _sql()
        assert "commence_time >=" in sql
        floor = (_NOW - timedelta(hours=1)).isoformat(sep=" ")
        assert floor in sql, (
            f"expected the floor at {floor} (one hour before the anchor), got:\n{sql}"
        )

    def test_the_soonest_fixture_comes_first(self):
        """"Next" means the soonest.

        The or-LAST arm sorts DESC because "last" means the one just played.
        Copying that here — the obvious edit when adapting one arm from the
        other — would answer `celtics` with Boston's LAST game of the season.
        """
        sql = _sql()
        assert "order by" in sql
        order_by = sql.split("order by", 1)[1]
        assert "commence_time asc" in order_by, order_by
        assert "commence_time desc" not in order_by, order_by

    def test_it_carries_the_proven_duplicate_clause(self):
        """CERT-439. This arm needs it more than its siblings, not less.

        It is the only search arm reaching 120 days out, so it selects on
        fixtures still accumulating provider rows. The `celtics` specimen
        measured while building this returned a twinned pair inside its own
        window (Celtic v Ferencvaros listed twice, three hours apart).

        BOTH arms of the OR are asserted, not just the tag. `not_a_proven_duplicate`
        is a function rather than a pasted expression precisely because
        `NULL NOT LIKE x` is NULL and not TRUE: a bare `NOT LIKE` would drop every
        untagged row — which is nearly all of them — and empty this arm entirely.
        A guard that checked only for the tag string would pass that mutant.
        """
        where = _sql().split("where", 1)[1].split("order by")[0]
        assert "event_tags is null" in where, where
        assert "not like '%provenance:duplicate-of:%'" in where, where


class TestTheArmIsActuallyWiredIn:
    """A query nobody calls is a query that repairs nothing."""

    @staticmethod
    def _tree():
        return ast.parse(textwrap.dedent(inspect.getsource(typeahead_search)))

    @staticmethod
    def _calls(node, name: str) -> bool:
        return any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == name
            for n in ast.walk(node)
        )

    def test_the_route_calls_it(self):
        assert self._calls(self._tree(), "_next_match_query"), (
            "the or-next arm is never called — it is dead code"
        )

    def test_it_is_gated_and_not_run_on_every_keystroke(self):
        """It must sit behind the same "nothing names the participant" gate.

        Ungated it is a fourth query on the hottest path in the API, run for
        every keystroke including the ones the upcoming pool already answered.
        """
        conditional = [
            branch
            for branch in ast.walk(self._tree())
            if isinstance(branch, ast.If) and self._calls(branch, "_next_match_query")
        ]
        assert conditional, "the or-next arm is called unconditionally"

    def test_it_runs_under_the_forced_custom_plan_guard(self):
        """#4506's pathology is about the SHAPE of the query, not its name.

        The or-NEXT arm is the same shape as or-LAST — a parameterised text
        predicate with an abort-early `ORDER BY commence_time LIMIT n` — so it
        is exposed to the same cached generic plan that measured 618ms median
        on production. Leaving it outside the guard reintroduces that cost on
        the repaired path.
        """
        guarded = [
            node
            for node in ast.walk(self._tree())
            if isinstance(node, ast.AsyncWith)
            and self._calls(node, "_next_match_query")
        ]
        assert guarded, (
            "the or-next arm runs outside `_forced_custom_plan` — see #4506"
        )

    def test_next_is_preferred_over_last(self):
        """"Live, else NEXT, else last" — the order is the rule.

        Asserted on the assembled pool rather than on call order: what a reader
        sees is the sequence in `_ta_rows`, and a change that ran the queries in
        the right order but concatenated them in the wrong one would put a
        finished game above tonight's fixture while every call-order assertion
        still passed.
        """
        source = inspect.getsource(typeahead_search)
        assert "[*_ta_next, *_ta_last, *_ta_rows]" in source, (
            "the or-next rows must be prepended AHEAD of the or-last rows"
        )

    def test_the_upcoming_pool_is_still_bounded_at_a_week(self):
        """🔴 THE REFUSAL. The cheap-looking fix is the one this forbids.

        Widening the upcoming pool to 120 days would satisfy every recall test
        in this file's sibling suites and would change the candidate set for
        EVERY query on the endpoint — `lakers` fetching games spread over six
        weeks, the fetch limit cutting relevant rows to make room for distant
        ones. The gated arm changes candidates only for queries that currently
        return nothing naming the participant. If this assertion fails, the
        repair has been undone and replaced with the thing it was chosen over.

        🔴 IT COUNTS, AND THE COUNT IS THE ASSERTION. `typeahead_search` holds
        TWO seven-day bounds — the primary event pool and the fuzzy pool it
        falls back to when a team matched but no event did. An `in` check passes
        while either one survives, so widening the primary pool alone — the
        exact mutant this test exists to refuse — went undetected until it was
        run against a mutation. Both arms stay at seven days; the or-NEXT arm is
        what reaches further.
        """
        source = inspect.getsource(typeahead_search)
        assert source.count("Event.commence_time <= now + timedelta(days=7)") == 2, (
            "a 7-day upcoming-pool bound moved — the or-next arm exists so those "
            "bounds can STAY. Widening a pool changes the candidate set for every "
            "query on the endpoint; see #5059"
        )


class TestTheBehaviouralGateExistsAndIsWiredIntoCi:
    """Everything above is a source assertion. This is what says so out loud.

    Each test in this file compiles the arm or reads the route's AST. Not one of
    them drives the endpoint, so all of them would stay green if the arm selected
    the right rows and the route dropped them on the floor — the exact shape that
    let `/search` keep returning a twin through a green CERT-439 unit suite.

    The behavioural half is `tests/integration/test_typeahead_next_fixture_pg.py`,
    and it is invisible to `backend-tests`' shards in the sense that matters: its
    cases are all `needs_postgres` and skip there. It grades something only inside
    the `search-recall` job, and that job names each of its integration files
    EXPLICITLY. A file added without its step is a gate that exists and never
    runs — which is indistinguishable, from the outside, from a gate that passes.
    """

    @staticmethod
    def _repo():
        from pathlib import Path

        return Path(__file__).resolve().parents[2]

    def test_the_behavioural_gate_exists(self):
        gate = self._repo() / "backend/tests/integration/test_typeahead_next_fixture_pg.py"
        assert gate.exists(), (
            "the real-Postgres or-NEXT gate is missing — this file's assertions "
            "cannot tell a working arm from a discarded one on their own"
        )

    def test_a_ci_step_names_it(self):
        workflow = (self._repo() / ".github/workflows/ci.yml").read_text()
        assert "tests/integration/test_typeahead_next_fixture_pg.py" in workflow, (
            "the or-NEXT behavioural gate is not named by any CI step, so it has "
            "never once executed"
        )

    def test_that_step_fails_on_a_silent_skip(self):
        """`pytest` exits 0 when every test skips.

        Without its own skip detection the step goes green the moment the service
        container fails to come up, and the gate reports success for a run in
        which nothing was measured.
        """
        import yaml

        workflow = yaml.safe_load(
            (self._repo() / ".github/workflows/ci.yml").read_text()
        )
        steps = workflow["jobs"]["search-recall"]["steps"]
        mine = [
            s for s in steps
            if "tests/integration/test_typeahead_next_fixture_pg.py" in (s.get("run") or "")
        ]
        assert len(mine) == 1, f"expected exactly one step for the gate, got {len(mine)}"
        assert "skipped" in mine[0]["run"], (
            "the or-NEXT gate step does not detect a silent skip"
        )


class TestTheHorizonIsMeasuredNotChosen:
    def test_it_clears_the_widest_real_offseason_gap(self):
        """Production 2026-09-11: NBA opening night was 39 days out.

        120 is three times that. The lower bound on this constant is not taste —
        anything under ~40 puts every NBA team back in the broken state the ship
        was filed for.
        """
        assert _NEXT_MATCH_LOOKAHEAD_DAYS >= 60

    def test_it_is_wider_than_the_pool_it_backs_up(self):
        assert _NEXT_MATCH_LOOKAHEAD_DAYS > 7
