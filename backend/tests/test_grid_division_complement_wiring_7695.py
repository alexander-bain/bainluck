"""#7695 wiring — the complement pass is IN the served grid builder, in the right place.

``test_grid_division_complement_7695.py`` grades the rule. This grades the wiring,
which is the half that decides whether a reader ever sees it.

**Why this file exists: the rule's own 14 tests do not bite.** Every one of them
calls ``propagate_division_complement`` directly. Delete the call site in
``routes/playoffs.py`` and all 14 stay green while the MLB grid goes back to
saying Atlanta won the NL East and pricing Philadelphia at 1.0% to win the NL
East, on one screen. The grader who passed CERT-3219 named this gap and left it
open; this is it.

It matters more here than it usually would, because **the rule's corrective arm
has never fired in production.** Measured daily 2026-09-21: 24 division cohorts
across five grids, 0 violations, and the only three decided cohorts (NL Central /
East / West) were all venue-graded before the fix shipped — so the live payload
cannot distinguish "wired and idle" from "not wired at all". Until the first AL
division clinch lands, this file is the only thing standing between the ship and
a silent unwiring.

RED ARM — measured by deleting the ``propagate_division_complement(...)`` call
from ``get_playoff_grid`` and running this file against that tree. **3 failed,
3 passed:**

    test_the_served_builder_calls_the_complement ..................... FAILED
    test_it_is_handed_the_grid_rows_not_the_espn_standings ........... FAILED
    test_it_runs_AFTER_the_clinch_overlay_and_BEFORE_normalization ... FAILED
    test_CONTROL_the_harness_is_reading_the_served_builder ........... passed
    test_CONTROL_the_builder_is_the_one_the_cached_route_serves ...... passed
    test_CONTROL_the_rule_itself_still_exists_and_is_importable ...... passed

The three controls are green on both trees, which is the point of having them: a
control that goes red under the deletion is not a control, it is a second copy of
the assertion. They testify that the harness read the right function, that the
function is the one the public endpoint reaches, and that a red here means "the
call site moved" rather than "the module stopped importing".

Read as source rather than behaviour on purpose. ``get_playoff_grid`` is ~1,000
lines and takes a live ``AsyncSession``; a behavioural route test would need a
fixture larger than the thing it guards, and would fail for a hundred reasons
that are not this one. The deletion this catches is a deletion of a line.
"""

from __future__ import annotations

import ast
import inspect

# Import the builder explicitly from `playoffs`. `app.routes.futures` defines a
# DIFFERENT function with the same name (futures.py:1475), so a loose import here
# would aim the whole file at the wrong source and pass for the wrong reason.
from app.routes.playoffs import get_playoff_grid, get_playoff_grid_cached


def _calls(func):
    """(lineno, name) for every plain-name call in `func`, ordered by line.

    Ordered by line number rather than by `ast.walk`'s traversal, which is
    breadth-first and only happens to agree for calls at one nesting depth —
    and these calls are not at one depth: `apply_clinch_overlay` sits inside an
    `if espn_rows:` block while the complement runs at the function's top level.
    """
    tree = ast.parse(inspect.getsource(func))
    return sorted(
        (node.lineno, node.func.id)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    )


def _complement_call(func):
    tree = ast.parse(inspect.getsource(func))
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "propagate_division_complement"
    ]
    return found


def test_the_served_builder_calls_the_complement():
    """The line whose deletion is invisible to every other test in the ship."""
    found = _complement_call(get_playoff_grid)
    assert found, (
        "get_playoff_grid no longer calls propagate_division_complement — the "
        "#7695 fix is unwired and the NL East can print two winners again"
    )
    assert len(found) == 1, f"expected exactly one call site, found {len(found)}"


def test_it_is_handed_the_grid_rows_not_the_espn_standings():
    """`teams`, not `espn_rows` — and the confusion is one line away.

    `apply_clinch_overlay(espn_rows, ...)` runs 35 lines above this call and
    takes the ESPN standings rows; `propagate_division_complement(teams, ...)`
    takes the grid rows the reader is served. Handing it `espn_rows` would be a
    silent no-op: those rows carry no `cells`, so no cohort would ever have a
    winner and the function would return 0 forever, exactly like the defect.
    """
    found = _complement_call(get_playoff_grid)
    assert len(found) == 1, (
        f"expected one propagate_division_complement call site, found {len(found)} "
        "— see test_the_served_builder_calls_the_complement for the likely cause"
    )
    (call,) = found
    assert call.args, "propagate_division_complement called with no arguments"
    first = call.args[0]
    assert isinstance(first, ast.Name), (
        f"first argument is {ast.dump(first)!r}, expected the bare name `teams`"
    )
    assert first.id == "teams", (
        f"propagate_division_complement is being handed `{first.id}`, not the "
        "grid rows `teams` — this returns 0 forever and reads as 'no violations'"
    )


def test_it_runs_AFTER_the_clinch_overlay_and_BEFORE_normalization():
    """Both boundaries are load-bearing, and the comment claiming them is not a control.

    AFTER `apply_clinch_overlay`: the complement reads the grid's own `won`
    cells and the overlay is what writes them from ESPN's `Clinched Division`.
    Running first, the pass would look at a cohort whose winner has not been
    marked yet, find no winner, and return 0 — which is precisely the #7695
    reading it was built to remove.

    BEFORE `normalize_column_sums`: the division column is scaled to sum over
    what is live, so the rivals' prices must already be zeroed when the sum is
    taken. Normalizing first would divide the column by a total that still
    counts Philadelphia's 1.0%, and every surviving cell in that cohort would
    be quietly scaled against a club that has already lost.
    """
    watched = {
        "apply_clinch_overlay",
        "propagate_division_complement",
        "normalize_column_sums",
    }
    order = [name for _, name in _calls(get_playoff_grid) if name in watched]
    assert order == [
        "apply_clinch_overlay",
        "propagate_division_complement",
        "normalize_column_sums",
    ], f"call order changed: {order}"


def test_CONTROL_the_harness_is_reading_the_served_builder():
    """Green on both trees: proves a red above is the call site, not the reader.

    If `inspect.getsource` were handed the wrong function — the same-named
    builder in `routes/futures.py`, say — these two would vanish too, and the
    failures above would be reporting the harness rather than the ship.
    """
    names = {name for _, name in _calls(get_playoff_grid)}
    assert "apply_clinch_overlay" in names
    assert "normalize_column_sums" in names


def test_CONTROL_the_builder_is_the_one_the_cached_route_serves():
    """Green on both trees: the guard is aimed at what the reader actually gets.

    `get_playoff_grid` is the RAW builder; every reader path reaches it through
    `get_playoff_grid_cached`, which the public endpoint, `league_context` and
    the warm precompute all call. Pinning a builder nothing serves would be a
    guard that can never fail for the reason it claims.
    """
    assert "get_playoff_grid" in {
        name for _, name in _calls(get_playoff_grid_cached)
    }


def test_CONTROL_the_rule_itself_still_exists_and_is_importable():
    """Green on both trees: separates 'call site deleted' from 'module broken'."""
    from app.utils.playoff_grid import propagate_division_complement

    assert callable(propagate_division_complement)
