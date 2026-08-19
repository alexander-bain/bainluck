"""``until`` — the reviewed population's COMPLETED half must be addressable alone
(#1798, queue 374 item 4).

WHY THIS PARAMETER EXISTS, which is not "for convenience"

The reviewed 180-side binding population splits cleanly by month: **151 sides in
2026-04, 29 in 2026-08** (re-derived 2026-08-19: 151 and 21 — the April count is
unchanged across two derivations two days apart, the August one is churning).

Those halves are not equivalent risk. April's games are long completed: static
damage, no ingestion writing to them. August's sit in the live band where the
#1989 absorber is still active, so repairing them races a writer — and Fable's
queue-374 ruling (c) sequences that half AFTER the absorber closes.

Before this parameter there was no way to SAY that:

* ``since`` cannot express an upper bound, and
* ``since`` was not reachable over HTTP at all — ``admin_repairs`` passes through
  only the names it declares, and ``since`` was not one of them.

So the only expressible population was "module default forward". That is not
merely awkward, because ``apply`` is bound to a whole plan by content address: an
operator who has approval for 151 rows and can only mint an address over 172 must
either write 21 rows nobody sanctioned or do nothing. A half that cannot be
scoped cannot be applied alone.
"""
from datetime import date

import ast
import inspect

import pytest

from app.tasks.repair_event_team_binding import repair, _CANDIDATES_SQL
from tests.test_repair_event_team_binding import _FakeSession, _row, TEAMS


class TestTheBoundReachesTheQuery:
    """It has to be IN the SQL, not applied to the SQL's results."""

    def test_the_scan_carries_an_exclusive_upper_bound_predicate(self):
        sql = str(_CANDIDATES_SQL)
        assert "commence_time < :until" in sql, (
            "the upper bound must be a predicate inside the scan. The scan is "
            "ORDER BY commence_time DESC LIMIT :lim — newest-first — so filtering "
            "the month out in Python AFTER the scan lets the NEWER half consume "
            "the limit and starves the older half. That is gotcha #41's shape "
            "(the combat-wps lesson): ordering is never the whole answer, ask "
            "what the ordering starts on."
        )
        assert "commence_time <= :until" not in sql, (
            "the bound is EXCLUSIVE — `until=2026-05-01` must mean 'April', not "
            "'April plus whatever happens to start at midnight on May 1st'"
        )

    @pytest.mark.asyncio
    async def test_until_is_bound_as_a_date_not_a_string(self):
        """The same class that 500-ed this rail on its first production call.

        ``_FakeSession`` never binds to a driver, and asyncpg binds by TYPE
        rather than rendering values into SQL text — so a str sails through every
        test here and dies in production. A double cannot check a driver's type
        contract, but it CAN check the type of what we hand it, and the existing
        ``TestSinceIsBoundAsADate`` exists for exactly this reason on ``since``.
        A new date-shaped parameter needs the same guard or it re-opens the hole.
        """
        session = _FakeSession([_row()], TEAMS)
        await repair(session, until="2026-05-01")
        until = session.candidate_scans[0]["until"]
        assert isinstance(until, date), (
            f"until was bound as {type(until).__name__}={until!r}; asyncpg "
            "rejects a str for a timestamp column and the rail 500s"
        )
        assert not isinstance(until, str)

    @pytest.mark.asyncio
    async def test_every_scan_binds_until_including_the_after_census(self):
        """Both scans, not just the first.

        The after-census runs AFTER the commit, so a binding error there 500s a
        run whose writes have already landed — the worse of the two failures.
        """
        session = _FakeSession([_row()], TEAMS)
        await repair(session, until="2026-05-01")
        assert session.candidate_scans, "no scan was recorded"
        for i, params in enumerate(session.candidate_scans):
            assert "until" in params, f"scan {i} did not bind until"
            assert isinstance(params["until"], date)


class TestTheUnboundedCallIsUnCHANGED:
    """A new parameter must not silently re-scope every existing caller."""

    @pytest.mark.asyncio
    async def test_omitting_until_still_binds_a_sentinel_so_the_sql_is_one_query(self):
        session = _FakeSession([_row()], TEAMS)
        await repair(session)
        until = session.candidate_scans[0]["until"]
        assert isinstance(until, date)
        assert until.year == 9999, (
            "an omitted bound is a far-future sentinel, so the predicate is "
            "always true and there is exactly ONE query text. A conditional "
            "predicate would give the bounded and unbounded calls two different "
            "scans that can drift apart."
        )

    @pytest.mark.asyncio
    async def test_an_unbounded_run_records_no_until_in_scope_or_plan_context(self):
        """The artifact must not claim a window it was never given.

        A sentinel written into the persisted plan would make every historical
        unbounded plan read as if it had been window-scoped — which is a false
        statement about what the reviewer saw.
        """
        session = _FakeSession([_row()], TEAMS)
        out = await repair(session)
        assert "until" not in out["scope"], (
            f"unbounded run leaked a window into scope: {out['scope']}"
        )

    @pytest.mark.asyncio
    async def test_a_bounded_run_DOES_record_its_window(self):
        session = _FakeSession([_row()], TEAMS)
        out = await repair(session, until="2026-05-01")
        assert out["scope"].get("until") == "2026-05-01", (
            "a window an operator asked for must be echoed back, so the reviewer "
            "can see the population the address was minted over"
        )


class TestItFailsClosedOnAnEmptyWindow:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("until", ["2026-03-01", "2026-01-01"])
    async def test_until_at_or_before_since_is_REFUSED_not_silently_empty(self, until):
        """An empty plan and 'nothing to repair' read identically. Refuse instead.

        This is gotcha #53's shape in miniature: the emptier reading is not a
        fact about the world, and an operator handed an empty plan cannot tell
        'the window was backwards' from 'the population is clean'.
        """
        session = _FakeSession([_row()], TEAMS)
        out = await repair(session, until=until)
        assert out.get("refused") is True
        assert "EMPTY_WINDOW" in out.get("reason_codes", [])
        assert not session.candidate_scans, (
            "the refusal must happen BEFORE the scan — a refused call should "
            "cost nothing and must never mint a plan"
        )
        assert "plan_hash" not in out


class TestTheDispatcherActuallyPassesItThrough:
    """The defect was half in the rail and half in the route.

    ``repair()`` already accepted ``since`` and had done for its whole life — and
    it was dead, because the dispatcher builds its kwargs from a literal tuple of
    names and ``since`` was not in it. A parameter the HTTP surface cannot reach
    is not a parameter. Walk the AST, not the text (Fable ruling (a)).
    """

    def _passthrough_names(self):
        import app.routes.admin_repairs as mod

        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "run_repair":
                continue
            names = set()
            for sub in ast.walk(node):
                # the ("name", value) pairs the kwargs dict is built from
                if isinstance(sub, ast.Tuple) and len(sub.elts) == 2:
                    first = sub.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        names.add(first.value)
            return names
        raise AssertionError("run_repair not found in app.routes.admin_repairs")

    @pytest.mark.parametrize("name", ["since", "until"])
    def test_the_date_bounds_are_in_the_passthrough_tuple(self, name):
        names = self._passthrough_names()
        assert name in names, (
            f"{name!r} is not passed through by run_repair, so no HTTP caller can "
            f"reach it. `repair()` declaring it is not enough — that is exactly "
            f"how `since` sat dead: accepted by the function, unreachable by the "
            f"only thing that calls it."
        )

    @pytest.mark.parametrize("name", ["since", "until"])
    def test_the_route_declares_the_query_param(self, name):
        import app.routes.admin_repairs as mod

        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run_repair":
                declared = {a.arg for a in node.args.args + node.args.kwonlyargs}
                assert name in declared, (
                    f"{name!r} is in the passthrough tuple but is not a declared "
                    f"Query parameter — it would pass through as None forever"
                )
                return
        raise AssertionError("run_repair not found")

    def test_repair_declares_until_so_the_passthrough_filter_admits_it(self):
        """The dispatcher filters on ``k in accepted``, by design.

        That filter is what makes adding a param safe for other repairs — and it
        is also what silently drops a param the target repair forgot to declare.
        """
        accepted = inspect.signature(repair).parameters
        assert "until" in accepted
        assert "since" in accepted
