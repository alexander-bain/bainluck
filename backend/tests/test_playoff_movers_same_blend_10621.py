"""#10621 — a grid's 24h move compares the SAME blend then vs now.

Every playoff/golf grid used to compute ``trend_24h = merged - old_p`` where
``merged`` blends ALL sources now and ``old_p`` is ONE source's consensus 24h ago
(whichever leg came first — ``odds_api`` on the NBA championship column). When
sportsbooks sat still, the printed "move" was the gap between sportsbooks and
Kalshi/Polymarket: the 76ers read "▲2.7 pts 24h" on 2026-10-06 while the page's
own trend chart held their headline at 11.05% all day.

The guard the issue names: three sources that disagree and do not move must
produce no move.
"""

import ast
import pathlib

import pytest

from app.routes.playoffs import _blended_trend_24h, _merge_probabilities


# The specimen's shape: sportsbooks 8.35%, Polymarket 11.05%, Kalshi 13%.
_SPORTSBOOKS, _POLYMARKET, _KALSHI = 0.0835, 0.1105, 0.13


def test_three_disagreeing_sources_that_did_not_move_print_no_move():
    legs = [(_SPORTSBOOKS, _SPORTSBOOKS), (_POLYMARKET, _POLYMARKET), (_KALSHI, _KALSHI)]

    assert _blended_trend_24h(legs) == 0.0

    # What the old arithmetic printed on the same fixture: the blend now minus
    # the FIRST leg then — the cross-source gap, read as movement.
    merged = _merge_probabilities([p for p, _ in legs])
    assert round(merged - legs[0][1], 4) == pytest.approx(0.027), (
        "fixture must reproduce the served +2.7 pts under the old formula"
    )


def test_a_real_move_in_one_source_moves_the_blend():
    # Polymarket (the median leg) rose 2 pts; the blend is the median, so +2 pts.
    legs = [(_SPORTSBOOKS, _SPORTSBOOKS), (_POLYMARKET, _POLYMARKET - 0.02), (_KALSHI, _KALSHI)]

    assert _blended_trend_24h(legs) == pytest.approx(0.02)


def test_a_source_with_no_reading_then_is_left_out_of_both_ends():
    # Kalshi is new today. Comparing a 3-source blend now with a 2-source blend
    # then is the same which-source defect; both ends use the two that exist.
    legs = [(_SPORTSBOOKS, _SPORTSBOOKS), (_POLYMARKET, _POLYMARKET), (_KALSHI, None)]

    assert _blended_trend_24h(legs) == 0.0


def test_no_reading_then_on_any_source_is_no_trend():
    assert _blended_trend_24h([(0.2, None), (0.3, None)]) is None
    assert _blended_trend_24h([]) is None


def test_volume_weights_are_held_fixed_across_both_ends():
    legs = [(0.10, 0.10), (0.30, 0.30)]
    assert _blended_trend_24h(legs, [10, 100_000]) == 0.0
    # And they are applied: a move on the heavy leg dominates.
    heavy = _blended_trend_24h([(0.10, 0.10), (0.32, 0.30)], [10, 100_000])
    light = _blended_trend_24h([(0.12, 0.10), (0.30, 0.30)], [10, 100_000])
    assert heavy > light > 0


# ---------------------------------------------------------------------------
# Every grid site routes through the helper
# ---------------------------------------------------------------------------

_PLAYOFFS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "playoffs.py"

#: The four builders that publish ``trend_24h`` (golf tour, upcoming golf event,
#: league grid, team progression). Pinned as a SET so a fifth builder that
#: computes its own delta, or one of these four dropping the helper, both fail.
_TREND_BUILDERS = {
    "_build_golf_grid_team_rows",
    "_build_upcoming_golf_event_grid",
    "get_playoff_grid",
    "_get_team_progression_for_event_uncached",
}


def _functions_calling_helper(tree: ast.AST) -> set[str]:
    found = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name == "_blended_trend_24h":
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_blended_trend_24h"):
                found.add(fn.name)
    # Nested defs (team progression's inner _build_team_row) report the
    # outermost top-level function too, since ast.walk descends into them.
    return found


def test_every_trend_builder_uses_the_same_blend_helper():
    tree = ast.parse(_PLAYOFFS.read_text())
    callers = _functions_calling_helper(tree)
    top_level = {n.name for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert callers & top_level == _TREND_BUILDERS


def test_no_site_subtracts_a_single_source_reading_from_the_blend():
    """``merged - old_p`` is the defect's exact shape; it must not come back."""
    tree = ast.parse(_PLAYOFFS.read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
        and isinstance(node.left, ast.Name) and node.left.id == "merged"
        and not isinstance(node.right, ast.Constant)  # the min-tick check
    ]
    assert offenders == [], f"merged - <x> at playoffs.py lines {offenders}"
