"""#5201: the dropdown reaches the RESOLVED team's fixture, not a namesake's.

WHAT WAS BROKEN, measured on production 2026-09-11 before any code moved.
`bruins`, at 390px, in the order the reader gets it:

    Boston Bruins | Make Playoffs 31%                      | Team
    Belmont Bruins                                         | Team
    San Diego State Aztecs at UCLA Bruins | Sat, Sep 12    | Game
    Bruins vs. Sabres Total Games O/U 5.5 | Yes 100%       | Futures
    NHL: BOS Bruins Total Points | 85+ points 74%          | Futures
    ...

Boston is in slot 0 and the only GAME on the page belongs to a different club in
a different sport. Boston's own next fixture — 2026-09-30, one of three inside
the 120-day horizon — was unreachable by any path the endpoint had.

WHY THE OR-NEXT ARM (#5059) COULD NOT REACH IT, which is the whole reason this
is a third arm rather than a widening of that one. It is gated on "no row in the
pool NAMES the query's participant", and a namesake satisfies that gate:

    query_names_participant('bruins', ['San Diego State Aztecs', 'UCLA Bruins'])
        -> True

so the gate never opened. `test_the_premise_of_the_bug_is_pinned` asserts that
predicate directly, because it is the load-bearing fact under this whole file
and a later edit to the plural/namesake rules would move it silently.

And widening is not available either: `_next_match_query` selects on the
participant-NAME filter and takes the eight soonest rows across 120 days. For
`bruins` those eight are UCLA's weekly football fixtures, and Boston's game is
nineteen days behind the last of them. A row that is never fetched cannot be
promoted by any ranking change, and post-filtering that result set returns
nothing at all. The fixture has to be SELECTED BY IDENTITY.

WHAT THIS FILE CAN AND CANNOT PROVE. It compiles the arm and reads the route as
an AST — the clauses and the wiring. It cannot prove the clause changes the
ANSWER; that is
`tests/integration/test_typeahead_next_fixture_pg.py::test_the_resolved_teams_own_fixture_reaches_the_dropdown`,
which drives the real route against real Postgres in CI's `search-recall` job.

THE MUTANTS THIS FILE EXISTS TO KILL, none of which a recall test would catch:

  * the name arm "improved" to a LIKE — which re-admits *UCLA Bruins*, the exact
    row the arm exists to step around (`test_the_name_arm_is_an_equality`);
  * the new gate merged into the or-NEXT one for tidiness, which re-gates every
    query that works today (`test_the_or_next_gate_is_untouched`);
  * the two id arms dropped as "the name covers it" — 1,374 of the 1,378
    id-carrying future fixtures do have a matching name, so a name-only version
    passes almost every hand check and loses the 4 that disagree, plus every row
    whose display name was normalised (`test_it_selects_by_identity`);
  * the rows appended instead of prepended, which the `_EVENT_POOL_SIZE`
    truncation then cuts behind the very namesakes they answer.
"""

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

from app.routes.events import (
    _LEAD_TEAM_FIXTURE_LIMIT,
    _NEXT_MATCH_LOOKAHEAD_DAYS,
    _lead_team_next_match_query,
    typeahead_search,
)
from app.utils.search_match_class import query_names_participant

_NOW = datetime(2026, 9, 11, 17, 0, tzinfo=timezone.utc)

#: The production specimen, by id and by name. Boston Bruins is `teams.id` 574.
_SUBJECT_ID = 574
_SUBJECT_NAME = "Boston Bruins"


def _sql() -> str:
    q = _lead_team_next_match_query(_SUBJECT_ID, _SUBJECT_NAME, _NOW)
    return str(q.compile(compile_kwargs={"literal_binds": True})).lower()


def _where() -> str:
    return _sql().split("where", 1)[1].split("order by")[0]


def test_the_premise_of_the_bug_is_pinned():
    """🔴 The one fact the whole ship rests on: a namesake NAMES the query.

    If this ever goes False the or-NEXT gate would have opened on its own and
    this arm is answering a question nobody is asking any more — read the
    plural-boundary work on #4615 before deleting anything, and do not "fix"
    that by widening `query_names_participant`: CERT-2392's measured rule is
    that the plural is the entity boundary (`sinner` -> Sinners -> False).
    """
    assert query_names_participant("bruins", ["San Diego State Aztecs", "UCLA Bruins"]) is True
    assert query_names_participant("bruins", ["Boston Bruins", "Buffalo Sabres"]) is True


class TestTheLeadTeamArmsOwnClauses:
    """The compiled query. Every clause is load-bearing."""

    def test_it_selects_by_identity(self):
        """🔴 THE SHIP, in one assertion: the team, not the text.

        Both id arms, because a fixture carries its team on either side and a
        home-only version answers half the season. Asserted on the compiled SQL
        rather than by reading the function, so a refactor that keeps the source
        shape and loses the clause is caught.
        """
        where = _where()
        assert f"home_team_id = {_SUBJECT_ID}" in where, where
        assert f"away_team_id = {_SUBJECT_ID}" in where, where

    def test_the_name_arm_is_an_equality(self):
        """🔴 NOT a LIKE, and this is the mutant that matters most.

        The entire defect is that "UCLA Bruins" CONTAINS the query. A substring
        or prefix test here re-admits precisely the row the arm exists to step
        around, and it would look like a generous improvement in review: it
        makes the arm "find more fixtures".

        The name arm earns its place on measurement, not symmetry: of the 344
        future fixtures inside the horizon with no `home_team_id` (production,
        2026-09-11), 81 name a real team row exactly and are reachable by
        nothing else.
        """
        where = _where()
        assert f"home_team_name = '{_SUBJECT_NAME.lower()}'" in where, where
        assert f"away_team_name = '{_SUBJECT_NAME.lower()}'" in where, where
        assert "home_team_name like" not in where, where
        assert "home_team_name ilike" not in where, where
        assert "away_team_name like" not in where, where
        assert "away_team_name ilike" not in where, where

    def test_it_asks_for_a_fixture_not_a_result(self):
        """A FIXTURE. If this selects completed rows it is the or-LAST arm again."""
        sql = _sql()
        assert "'scheduled'" in sql and "'live'" in sql, sql
        assert "'completed'" not in sql, "this arm answers 'the next game'"
        assert "'closed'" not in sql, "this arm answers 'the next game'"

    def test_it_reaches_past_the_seven_day_pool(self):
        """Otherwise it is the upcoming pool again and repairs nothing.

        Boston's next game was NINETEEN days out on the day this was built —
        inside the horizon, outside the pool. Asserted as a real date in the
        compiled SQL, because the constant being 120 proves nothing about
        whether the query uses it.
        """
        ceiling = (_NOW + timedelta(days=_NEXT_MATCH_LOOKAHEAD_DAYS)).isoformat(sep=" ")
        assert ceiling in _sql(), f"expected a {ceiling} ceiling in:\n{_sql()}"

    def test_it_is_floored_at_the_upcoming_pools_own_floor(self):
        """`now - 1h`, and asserted TO THE HOUR.

        Same trap #5059's file paid for: 16:00 and 17:00 truncate to the same
        DATE, so a date-level assertion throws away the exact hour it exists to
        protect and a mutation of the floor to `now` stays green (gotcha #44 —
        offset first, then truncate, and never past the unit you are asserting).
        The hour is what keeps a game that kicked off forty minutes ago from
        falling between this arm and the pool it backs up.
        """
        sql = _sql()
        floor = (_NOW - timedelta(hours=1)).isoformat(sep=" ")
        assert "commence_time >=" in sql
        assert floor in sql, f"expected the floor at {floor}, got:\n{sql}"

    def test_the_soonest_fixture_comes_first(self):
        """"Next" means the soonest — and with LIMIT 1 the sort IS the answer.

        Copying the or-LAST arm's DESC here (the obvious edit when adapting one
        arm from another) would answer `bruins` with Boston's LAST game of the
        season and nothing would look broken.
        """
        order_by = _sql().split("order by", 1)[1]
        assert "commence_time asc" in order_by, order_by
        assert "commence_time desc" not in order_by, order_by

    def test_the_live_game_outranks_the_next_one(self):
        """Q438: the served status can never disagree with the sort.

        The same `live_first_order` term the upcoming pool and the or-NEXT arm
        use, so "the live game, else the next" holds inside this arm too rather
        than only across arms.
        """
        order_by = _sql().split("order by", 1)[1]
        assert "commence_time" in order_by
        assert order_by.index("case") < order_by.index("commence_time asc"), order_by

    def test_it_takes_exactly_one_row(self):
        """One, and the constant is not the assertion — the compiled LIMIT is.

        This arm fires only when the pool is already full of somebody else's
        fixtures, so every extra row it prepends spends one of the reader's four
        event slots on a team whose card they can already see.
        """
        assert _LEAD_TEAM_FIXTURE_LIMIT == 1
        assert "limit 1" in _sql(), _sql()

    def test_it_carries_the_proven_duplicate_clause(self):
        """CERT-439, and it matters MORE here than in its siblings.

        This arm reaches furthest out, over fixtures still accumulating provider
        rows, and it takes ONE row — so a twin that sorts first is not a
        duplicate beside the answer, it IS the answer.

        BOTH arms of the OR are asserted. `NULL NOT LIKE x` is NULL, not TRUE, so
        a bare `NOT LIKE` would drop every untagged row — nearly all of them —
        and empty this arm entirely while every other test here stayed green.
        """
        where = _where()
        assert "event_tags is null" in where, where
        assert "not like '%provenance:duplicate-of:%'" in where, where

    def test_it_eager_loads_everything_the_pool_build_reads(self):
        """gotcha #6: a lazy load on an async row RAISES, it does not emit a query.

        Rows from this arm go through the same pool build as every other row —
        `_ta_names_participant` reaches `ev.sport.key`, and the payload reads
        `event.home_team.logo_url_small`. A `MissingGreenlet` here is a 500 on a
        per-keystroke path, for the queries this ship exists to repair.
        """
        source = inspect.getsource(_lead_team_next_match_query)
        for rel in ("Event.sport", "Event.home_team", "Event.away_team"):
            assert f"selectinload({rel})" in source, rel


class TestTheArmIsActuallyWiredIn:
    """A query nobody calls repairs nothing. Read as an AST, not as text."""

    @staticmethod
    def _source() -> str:
        return textwrap.dedent(inspect.getsource(typeahead_search))

    @classmethod
    def _tree(cls) -> ast.AST:
        return ast.parse(cls._source())

    def test_the_arm_is_called(self):
        called = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_lead_team_next_match_query"
            for n in ast.walk(self._tree())
        )
        assert called, "the lead-team arm is never called — #5201 is inert"

    def test_the_or_next_gate_is_untouched(self):
        """🔴 THE REFUSAL. This ship adds an arm; it re-gates nothing.

        CERT-2392's rule — a pool full of somebody else is as empty as an empty
        pool — is the or-NEXT arm's trigger and it must survive verbatim. The
        tempting tidy-up is to fold the two gates into one "does the pool hold
        the right fixture" test; that changes what EVERY query on the endpoint
        fetches, which is the cheaper fix #5059 was deliberately chosen over.
        """
        assert (
            "if not any(_ta_names_participant(ev) for ev in _ta_rows):"
            in self._source()
        ), "the or-NEXT gate has been rewritten — see CERT-2392 before proceeding"

    def test_the_lead_team_is_the_pools_leading_row(self):
        """Not a second notion of "what the reader meant".

        The pool is ordered by prominence then exactness precisely so the row
        the scorer would pick is in slot 0; deriving a different answer here is
        how the team card and the game beneath it come to disagree — the bug.
        """
        assert "_ta_lead_team = team_pool[0] if team_pool else None" in self._source()

    def test_the_gate_and_the_query_cannot_disagree(self):
        """The same four columns on both sides, asserted as sets.

        A gate LOOSER than its query fires forever (a wasted round trip on every
        keystroke); a gate TIGHTER than its query never fires at all and the
        ship is silently inert. Either way both halves keep working, which is
        why this is checked structurally rather than left to review.
        """
        gate = next(
            (
                n
                for n in ast.walk(self._tree())
                if isinstance(n, ast.FunctionDef) and n.name == "_ta_is_lead_team_fixture"
            ),
            None,
        )
        assert gate is not None, "the gate helper is gone"

        gate_columns = {
            node.attr
            for node in ast.walk(gate)
            if isinstance(node, ast.Attribute)
            and node.attr.startswith(("home_team", "away_team"))
        }
        query_columns = {
            node.attr
            for node in ast.walk(ast.parse(textwrap.dedent(
                inspect.getsource(_lead_team_next_match_query)
            )))
            if isinstance(node, ast.Attribute)
            and node.attr.startswith(("home_team", "away_team"))
        }
        # The query also eager-loads the two relationships; the gate reads plain
        # columns. Compare on the columns both are entitled to have.
        columns = {"home_team_id", "away_team_id", "home_team_name", "away_team_name"}
        assert gate_columns & columns == columns, gate_columns
        assert query_columns & columns == columns, query_columns

    def test_the_rows_are_prepended(self):
        """`_ta_events[:_EVENT_POOL_SIZE]` truncates BEFORE anything is scored.

        Appended, this row sits behind the four namesake fixtures it was fetched
        to answer and is cut on its way to the scorer — the ship would fail in a
        way that reads as a ranking bug and is not one.
        """
        assert "_ta_rows = [*_ta_lead_rows, *_ta_rows]" in self._source()

    def test_the_new_arm_runs_after_the_or_next_arm(self):
        """Composition, and it is what keeps the arm from double-fetching.

        If the or-NEXT arm already prepended the team's own fixture, the gate
        below sees it and this arm costs nothing. Ordered the other way the two
        would both fire for every repaired query.
        """
        source = self._source()
        assert source.index("_ta_rows = [*_ta_next, *_ta_last, *_ta_rows]") < source.index(
            "_ta_lead_team = team_pool[0] if team_pool else None"
        )

    def test_the_fetched_row_is_promoted(self):
        """Fetched but not promoted is the same as never fetched, one step later.

        `_names_participant` is what #4986 promotes on. A row selected BY THE
        TEAM'S OWN ID is the participant's by construction — a strictly tighter
        test than any name match — so it must carry the flag, or a query whose
        nickname the token test declines ("celtic" naming "Boston Celtics")
        fetches the game and then drops it at the pool cap.
        """
        assert "event.id in _ta_lead_team_row_ids" in self._source()

    def test_the_arm_is_marked_for_the_timing_probe(self):
        """A stage nobody stamps is a cost nobody can attribute (#4506's lesson).

        Marked only INSIDE the branch, so `lead_team_next_match_query: 0` is
        never written for a keystroke where the arm was not armed — "cost
        nothing" and "never ran" are different facts.
        """
        marked_inside = [
            n
            for n in ast.walk(self._tree())
            if isinstance(n, ast.If)
            and any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name)
                and c.func.id == "_ta_mark"
                and c.args
                and getattr(c.args[0], "value", None) == "lead_team_next_match_query"
                for c in ast.walk(ast.Module(body=n.body, type_ignores=[]))
            )
        ]
        assert marked_inside, "the lead-team arm is not stamped inside its own branch"
        assert self._source().count('_ta_mark("lead_team_next_match_query")') == 1
