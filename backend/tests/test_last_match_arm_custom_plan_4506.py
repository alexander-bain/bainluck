"""THE OR-LAST ARM RUNS UNDER A CUSTOM PLAN, AND IT PUTS THE GENERIC ONE BACK. #4506.

Sibling of `test_typeahead_leads_with_the_entity_4411.py`, which owns whether the
arm EXISTS and is REACHED. This file owns what it costs, because #4411 shipped
the arm and #4506 is the regression #4411 caused: from 21:30Z on 2026-09-09 the
arm was 86% of an `nfl` keystroke on production.

MEASURED, production, `GET /api/events/typeahead?debug_timing=1`, 21:45-22:05Z:

    stage `last_match_query`, 14 consecutive `nfl` samples   576-920 ms
    every OTHER stage in the same 14 samples                  7-38 ms
    by term, median / max     sinner 1008/1677 · nba 794/1216 · nfl 740/1669
                              mlb 682/1000 · alcaraz 616/751 · us open 14/17
    pg_stat_statements, the arm's own fingerprint             428 calls,
                                                              mean 142.5 ms,
                                                              max 2159.4 ms
    the SAME SQL with LITERALS, EXPLAIN ANALYZE on production
                              alcaraz 1.1 · nfl 2.6 · sinner 2.9 ms

`alcaraz` and `sinner` are the two headline terms of the ship the arm exists to
serve, so this is not a tail case.

TWO PLANS, NOT A LOAD CURVE. `nfl` and `mlb` each produced a lone 5 ms and 3 ms
reading among 600-1600 ms ones with NOTHING in between, and only this one stage
moved. That bimodality is `plan_cache_mode = auto` (production `pg_settings`:
`boot_val = reset_val = auto`) switching a prepared statement to its generic plan
on the sixth execution of a pooled connection — which also means a measurement
taken minutes after a dyno restart reads fast and proves nothing.

WHAT THIS FILE MUST NOT BE READ AS: a claim that `force_custom_plan` is good
hygiene generally. It is scoped to ONE statement and restored immediately,
because `futures_query` and `headline_contenders` run after this arm in the same
transaction and a replan is a cost they did not ask for. The disarm is tested
below in its own right, including on the exception path.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.routes.events import (
    _LAST_MATCH_PLAN_CACHE_MODE,
    _PLAN_CACHE_MODE_RESTING,
    _forced_custom_plan,
    typeahead_search,
)


# --- a session that records the SQL it is handed --------------------------


class _Recorder:
    """Records `str(clause)` for every execute; answers `SHOW` with a mode."""

    def __init__(self, show: str | None = "force_custom_plan", fail_on: str | None = None):
        self.sql: list[str] = []
        self._show = show
        self._fail_on = fail_on

    async def execute(self, clause):
        rendered = str(clause)
        self.sql.append(rendered)
        if self._fail_on and self._fail_on in rendered:
            raise RuntimeError(f"boom: {rendered}")
        return _ScalarResult(self._show if rendered.startswith("SHOW") else None)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


def _sets(recorder: _Recorder) -> list[str]:
    return [s for s in recorder.sql if s.startswith("SET LOCAL plan_cache_mode")]


# --- the arm is actually run under the manager ----------------------------


class TestTheArmRunsUnderTheManager:
    """AN OMISSION GUARD, and that is the whole point of reading it as an AST.

    Every test in `test_typeahead_leads_with_the_entity_4411.py` stays green if
    the `async with` is deleted and the `db.execute(_last_match_query(...))` left
    where it is — the arm still runs, still returns the right rows, still ranks
    them right, and still costs 618 ms. A ban-shaped assertion ("no bare execute
    of the arm") is blind the other way round, so the property asserted here is
    positional: the call SITS INSIDE the block.
    """

    @staticmethod
    def _tree():
        return ast.parse(textwrap.dedent(inspect.getsource(typeahead_search)))

    @staticmethod
    def _calls_the_arm(node) -> bool:
        return any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_last_match_query"
            for n in ast.walk(node)
        )

    def test_the_arm_is_still_called(self):
        """Cheap sanity: if #4411's own reach guard has gone, say so here first."""
        assert self._calls_the_arm(self._tree()), "the or-last arm is never called"

    def test_every_call_of_the_arm_is_inside_a_forced_custom_plan_block(self):
        tree = self._tree()

        guarded_blocks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncWith)
            and any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "_forced_custom_plan"
                for item in node.items
            )
        ]
        assert guarded_blocks, (
            "no `async with _forced_custom_plan(...)` in the dropdown — the arm "
            "is back on the cached generic plan (#4506)"
        )

        guarded_calls = sum(
            1
            for block in guarded_blocks
            for n in ast.walk(block)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_last_match_query"
        )
        total_calls = sum(
            1
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_last_match_query"
        )
        assert total_calls and guarded_calls == total_calls, (
            f"{total_calls - guarded_calls} of {total_calls} calls to the or-last "
            "arm run outside `_forced_custom_plan` — those pay the generic plan"
        )

    def test_the_read_back_is_wired_to_the_debug_flag(self):
        """`read_back=True` hardcoded would charge a SHOW to every keystroke.

        `read_back=False` hardcoded would delete the only pre/post signal that
        tells "the arming never took" apart from "the diagnosis was wrong" —
        which is the exact ambiguity #4506's fix has to be measured through.
        """
        blocks = [
            item.context_expr
            for node in ast.walk(self._tree())
            if isinstance(node, ast.AsyncWith)
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "_forced_custom_plan"
        ]
        assert blocks
        for call in blocks:
            read_back = [kw for kw in call.keywords if kw.arg == "read_back"]
            assert read_back, "`read_back` is not passed — it defaults to False"
            assert isinstance(read_back[0].value, ast.Name), (
                "`read_back` is a constant, so the echo is either always on or "
                "always off; it must follow the request's own debug flag"
            )


# --- what the manager emits -----------------------------------------------


class TestItArmsTheCustomPlan:
    @pytest.mark.asyncio
    async def test_it_forces_a_custom_plan_before_the_arm_runs(self):
        db = _Recorder()
        async with _forced_custom_plan(db) as state:
            db.sql.append("-- the arm --")
        assert db.sql[0] == f"SET LOCAL plan_cache_mode = '{_LAST_MATCH_PLAN_CACHE_MODE}'"
        assert "force_custom_plan" in db.sql[0], (
            "the GUC value is not `force_custom_plan`; `auto` and "
            "`force_generic_plan` are the two settings this fix exists to avoid"
        )
        assert state["armed"] is True

    @pytest.mark.asyncio
    async def test_the_arm_runs_between_the_arming_and_the_disarming(self):
        """Order is the property. Arming after the statement changes nothing."""
        db = _Recorder()
        async with _forced_custom_plan(db):
            db.sql.append("-- the arm --")
        assert [s for s in db.sql if s.startswith("SET LOCAL") or s.startswith("--")] == [
            f"SET LOCAL plan_cache_mode = '{_LAST_MATCH_PLAN_CACHE_MODE}'",
            "-- the arm --",
            f"SET LOCAL plan_cache_mode = '{_PLAN_CACHE_MODE_RESTING}'",
        ]


class TestItPutsItBack:
    """`SET LOCAL` lasts the whole transaction, and two stages come after."""

    @pytest.mark.asyncio
    async def test_it_restores_the_resting_mode(self):
        db = _Recorder()
        async with _forced_custom_plan(db):
            pass
        assert _sets(db)[-1] == (
            f"SET LOCAL plan_cache_mode = '{_PLAN_CACHE_MODE_RESTING}'"
        )
        assert _PLAN_CACHE_MODE_RESTING == "auto", (
            "`auto` is Postgres' own resting value (boot_val = reset_val = auto, "
            "read from production pg_settings); restoring anything else would "
            "leave the connection in a state nobody chose"
        )

    @pytest.mark.asyncio
    async def test_it_restores_even_when_the_arm_raises(self):
        """A statement_timeout inside the block must not leak the GUC onward.

        Written as try/except rather than `pytest.raises` so the propagation is
        an assertion of its own: an `@asynccontextmanager` whose generator
        catches at the `yield` and does not re-raise SWALLOWS the error, and a
        swallowed `statement_timeout` here would serve a dropdown that silently
        lost its events arm. The restore and the re-raise are two properties and
        this pins both.
        """
        db = _Recorder()
        propagated = False
        try:
            async with _forced_custom_plan(db):
                raise RuntimeError("query cancelled")
        except RuntimeError:
            propagated = True
        assert propagated, (
            "the manager swallowed the error — a cancelled arm would look like "
            "a player with no matches rather than like a failure"
        )
        assert _sets(db)[-1] == (
            f"SET LOCAL plan_cache_mode = '{_PLAN_CACHE_MODE_RESTING}'"
        )

    @pytest.mark.asyncio
    async def test_it_does_not_disarm_what_it_never_armed(self):
        """Arming failed, so the transaction may be unusable — do not pile on."""
        db = _Recorder(fail_on="force_custom_plan")
        async with _forced_custom_plan(db) as state:
            pass
        assert state["armed"] is False
        assert not [s for s in _sets(db) if "auto" in s]


class TestTheGuardNeverBreaksTheDropdown:
    @pytest.mark.asyncio
    async def test_a_failed_arming_is_swallowed(self):
        """The dropdown is the ship; a latency guard may never be the thing that
        breaks it. Local sqlite sessions have no `plan_cache_mode` at all."""
        db = _Recorder(fail_on="force_custom_plan")
        async with _forced_custom_plan(db) as state:
            db.sql.append("-- the arm --")
        assert "-- the arm --" in db.sql
        assert state == {"armed": False, "mode": None}


class TestTheProofTravels:
    """Without this the post-deploy measurement cannot name its own failure.

    `SET LOCAL` outside a transaction is a silent no-op. An inert fix and a wrong
    diagnosis produce the SAME reading — "latency unchanged" — and the only thing
    that separates them is what Postgres says it is holding at the moment the arm
    runs.
    """

    @pytest.mark.asyncio
    async def test_it_reads_the_mode_back_when_asked(self):
        db = _Recorder(show="force_custom_plan")
        async with _forced_custom_plan(db, read_back=True) as state:
            pass
        assert "SHOW plan_cache_mode" in db.sql
        assert state["mode"] == "force_custom_plan"

    @pytest.mark.asyncio
    async def test_it_reports_a_no_op_arming_rather_than_hiding_it(self):
        """If the SET LOCAL did not take, the echo says `auto` and the probe
        knows the fix is inert instead of blaming the diagnosis."""
        db = _Recorder(show="auto")
        async with _forced_custom_plan(db, read_back=True) as state:
            pass
        assert state["mode"] == "auto"

    @pytest.mark.asyncio
    async def test_it_costs_no_round_trip_when_not_asked(self):
        db = _Recorder()
        async with _forced_custom_plan(db):
            pass
        assert not [s for s in db.sql if s.startswith("SHOW")]

    def test_the_echo_is_its_own_key_and_not_inside_the_timing_map(self):
        """CERT-2032's follow-up, applied: `total_ms` is a SUM over
        `debug_timing`, and a GUC name summed with milliseconds is a reader
        waiting to happen. `debug_shed` is here for the same reason."""
        src = textwrap.dedent(inspect.getsource(typeahead_search))
        assert 'result["debug_plan"]' in src, (
            "the armed/mode state is never served — the post-deploy proof has no "
            "rail (#4506)"
        )
        timing_assignment = next(
            line for line in src.splitlines() if 'result["debug_timing"]' in line
        )
        assert "plan" not in timing_assignment, (
            "the plan state is being written into the summed timing map"
        )
