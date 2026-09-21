"""#1740 — the dropdown stops claiming nothing matched when it ran out of time looking.

THE DEFECT, stated by the issue's own title: *"typeahead computes `_ta_degraded`
then drops it from the response."* Both shed flags were computed in
`typeahead_search` and then reachable from exactly one place —

    result["debug_shed"] = {"outcome_arm_shed": ..., "degraded": ...}

— which is inside the `if debug_timing:` branch. A normal keystroke never sets
`debug_timing`, and the route refuses to CACHE a debug answer anyway, so no
reader and no client has ever been able to see either flag. The wire could not
distinguish "this prefix matches nothing" from "we abandoned the futures stage",
and both clients printed the first sentence for both.

That is the same claim about the world `/search` stopped making in #2239, one
surface earlier. `/search` states the contract at its payload site:

    A stage we could not complete must be distinguishable from a stage that
    honestly found nothing.

`/search` has kept it since LAT-P002/#1494 (`**({"degraded": degraded} if
degraded else {})`). `/typeahead` never had it. Sites 1 and 2 of #1740 (the web
and iOS halves of `/search`) are done; sites 3 and 4 are the two `/typeahead`
clients, and they were PRODUCER-BLOCKED on this file emitting the field.

## What these tests pin, in three halves that fail for different reasons

* `TestTheGuardIsArmed` — the AST locators below actually find their targets. Without
  it every structural assertion in this file passes vacuously the day the route is
  restructured or a name changes, which is the standing failure mode of source-reading
  guards. If this class fails, nothing else here means anything.
* `TestTheStageNamesAreDecided` — the pure mapping. Directly callable, so the stage
  names, their order and the empty case are pinned by behaviour rather than by source.
* `TestTheRouteActuallyEmitsIt` — the defect itself, structurally: the key is assigned
  OUTSIDE the `debug_timing` branch and BEFORE the cache write. Both are RED on the
  pre-fix source, and for different reasons — pre-fix there was no `result["degraded"]`
  assignment at all, so the first assertion fails on absence; and a fix that emitted it
  after the Redis write would leave every warm keystroke undeclared for the full TTL,
  which only the ordering assertion catches.

The ordering half is not hypothetical bookkeeping: the cached body is
`_json.dumps(result)` taken at the write, so a key added after it is a key the
next 65 seconds of readers of that prefix do not get.
"""

import ast
import inspect
import pathlib

import pytest

from app.routes.events import _typeahead_shed_stages

ROUTE = pathlib.Path(
    inspect.getsourcefile(__import__("app.routes.events", fromlist=["x"]))
)
TREE = ast.parse(ROUTE.read_text())


# ---------------------------------------------------------------------------
# AST locators. Same idiom as test_lat_p241_outcome_arm_shed_is_cacheable_3399.
# ---------------------------------------------------------------------------


def _typeahead_fn() -> ast.AsyncFunctionDef:
    for node in ast.walk(TREE):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "typeahead_search":
            return node
    raise AssertionError("typeahead_search not found in routes/events.py")


def _degraded_assignments() -> list[ast.Assign]:
    """Every `result["degraded"] = ...` in the route, in source order."""
    found = []
    for n in ast.walk(_typeahead_fn()):
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if (
                isinstance(t, ast.Subscript)
                and isinstance(t.value, ast.Name)
                and t.value.id == "result"
                and isinstance(t.slice, ast.Constant)
                and t.slice.value == "degraded"
            ):
                found.append(n)
    return sorted(found, key=lambda n: n.lineno)


def _debug_timing_branch() -> ast.If:
    """The `if debug_timing:` branch that used to be the only way out."""
    for n in ast.walk(_typeahead_fn()):
        if (
            isinstance(n, ast.If)
            and isinstance(n.test, ast.Name)
            and n.test.id == "debug_timing"
        ):
            return n
    raise AssertionError("the `if debug_timing:` branch was not found")


def _cache_write_gate() -> ast.If:
    """The `if not _ta_degraded and ...:` branch holding the `setex` write."""
    for n in ast.walk(_typeahead_fn()):
        if not isinstance(n, ast.If):
            continue
        for c in ast.walk(ast.Module(body=n.body, type_ignores=[])):
            if (
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "setex"
            ):
                return n
    raise AssertionError("the typeahead cache write was not found")


def _names_read(node: ast.AST) -> set[str]:
    return {
        n.id
        for n in ast.walk(node)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }


# ---------------------------------------------------------------------------


class TestTheGuardIsArmed:
    """Strawman guards. Every assertion below reads source; these prove the
    reads land on something."""

    def test_the_route_function_is_found(self):
        assert _typeahead_fn().name == "typeahead_search"

    def test_the_debug_timing_branch_is_found(self):
        assert isinstance(_debug_timing_branch(), ast.If)

    def test_the_cache_write_is_found(self):
        assert isinstance(_cache_write_gate(), ast.If)

    def test_a_degraded_assignment_exists_at_all(self):
        # RED on the pre-fix source: `degraded` appeared only as a dict KEY
        # inside `debug_shed`, never as an assignment into `result`.
        assert _degraded_assignments(), (
            "`result[\"degraded\"]` is never assigned in typeahead_search — the "
            "route still computes its shed flags and drops them (#1740)"
        )


class TestTheStageNamesAreDecided:
    """The pure mapping, called directly. Behaviour, not source."""

    def test_a_complete_answer_declares_nothing(self):
        assert _typeahead_shed_stages(False, False) == []

    def test_a_lost_futures_stage_is_named_futures(self):
        assert _typeahead_shed_stages(True, False) == ["futures"]

    def test_a_shed_outcome_arm_is_named_outcome_names(self):
        assert _typeahead_shed_stages(False, True) == ["outcome_names"]

    def test_both_are_declared_severity_first(self):
        # Order is part of the contract: a reader diffing two payloads compares
        # lists. `futures` loses the whole stage, `outcome_names` a bonus lane.
        assert _typeahead_shed_stages(True, True) == ["futures", "outcome_names"]

    @pytest.mark.parametrize(
        "futures_shed,outcome_arm_shed",
        [(False, False), (True, False), (False, True), (True, True)],
    )
    def test_the_result_is_always_a_list_of_str(self, futures_shed, outcome_arm_shed):
        # The clients type this `readonly string[] | null` / `[String]?`. A bool
        # or an int leaking in here is a decode failure on the phone, not a
        # cosmetic difference.
        out = _typeahead_shed_stages(futures_shed, outcome_arm_shed)
        assert isinstance(out, list)
        assert all(isinstance(s, str) for s in out)


class TestTheRouteActuallyEmitsIt:
    """The defect. Both assertions are RED on the pre-fix source."""

    def test_it_is_emitted_outside_the_debug_timing_branch(self):
        # THE DEFECT ITSELF. `debug_shed` lives inside `if debug_timing:`, which
        # a normal keystroke never sets — so an assignment reachable only from
        # there is the bug, not the fix.
        inside = {
            id(n)
            for n in ast.walk(
                ast.Module(body=_debug_timing_branch().body, type_ignores=[])
            )
        }
        reachable = [n for n in _degraded_assignments() if id(n) not in inside]
        assert reachable, (
            "`result[\"degraded\"]` is assigned only inside `if debug_timing:` — "
            "a normal keystroke still gets an undeclared answer (#1740)"
        )

    def test_it_is_emitted_before_the_cache_write(self):
        # The cached body is `_json.dumps(result)` taken AT the write. A key
        # added after it is a key every warm reader of that prefix misses for
        # the full TTL — the answer would declare itself on a cold keystroke and
        # go quiet on a warm one, which is worse than never declaring it.
        first = _degraded_assignments()[0].lineno
        assert first < _cache_write_gate().lineno, (
            "`result[\"degraded\"]` is assigned after the Redis write, so warm "
            "entries are served without it"
        )

    def test_both_shed_flags_feed_it(self):
        # A fix that declared only the futures loss would leave the outcome-arm
        # shed exactly as undeclared as it was.
        call = None
        for n in ast.walk(_typeahead_fn()):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "_typeahead_shed_stages"
            ):
                call = n
                break
        assert call is not None, "_typeahead_shed_stages is never called by the route"
        read = _names_read(call)
        assert "_ta_degraded" in read, "the futures-stage flag does not reach `degraded`"
        assert "_ta_outcome_arm_shed" in read, (
            "the outcome-arm shed flag does not reach `degraded`"
        )

    def test_the_key_is_additive(self):
        # Absent means complete, matching `/search`. An unconditional
        # `result["degraded"] = []` would break every client that treats
        # presence as meaningful and would change the cached body for every
        # healthy keystroke.
        guarded = 0
        for n in ast.walk(_typeahead_fn()):
            if not isinstance(n, ast.If):
                continue
            body = ast.Module(body=n.body, type_ignores=[])
            for c in ast.walk(body):
                if c in _degraded_assignments():
                    guarded += 1
        assert guarded == len(_degraded_assignments()), (
            "`result[\"degraded\"]` is assigned unconditionally — the key must be "
            "absent when the answer is complete"
        )
