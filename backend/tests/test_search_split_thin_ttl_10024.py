"""#10024: one slow moment must not cache "No results" for 'phillies world series' for three minutes.

THE SHIP (DISCOVER): searching a team plus its competition (`phillies world
series`) shows that competition's board with the team's price.

The board reaches `/search` only through the futures SPLIT arm: the title says
`world series` and one leg says `phillies`. If the arm misses its bound, the answer
is empty. Before this change that empty answer was cached for the full 180 s,
because the short life (#9947) read only the OUTCOME arm. Production 2026-10-01
14:01-14:05Z: `phillies world series` was a cache HIT with 0 futures for about
3.5 minutes, while every uncached (`debug_timing`) read returned "MLB World Series
Champion 2026" with the split arm `merged`.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.utils.search_cache import (
    SEARCH_RESPONSE_TTL_SECONDS,
    SEARCH_THIN_RESPONSE_TTL_SECONDS,
    search_response_ttl_seconds,
)

_COMPLETE = ("absent", "skipped", "merged", "not_reached")
_THIN = ("shed", "budget_exceeded")


@pytest.mark.parametrize("split", _THIN)
@pytest.mark.parametrize("outcome", _COMPLETE)
def test_a_thin_split_arm_gets_the_short_life_whatever_the_outcome_arm(split, outcome):
    assert (
        search_response_ttl_seconds(outcome, warmer_rebuild=False, futures_split_arm=split)
        == SEARCH_THIN_RESPONSE_TTL_SECONDS
    )


@pytest.mark.parametrize("split", _COMPLETE)
@pytest.mark.parametrize("outcome", _COMPLETE)
def test_both_arms_complete_keeps_the_ceiling(split, outcome):
    """Control: `freddie freeman`/`dodgers world series` on a good moment still
    live the D81 ceiling."""
    assert (
        search_response_ttl_seconds(outcome, warmer_rebuild=False, futures_split_arm=split)
        == SEARCH_RESPONSE_TTL_SECONDS
    )


@pytest.mark.parametrize("split", _THIN + _COMPLETE)
def test_the_warmer_keeps_the_full_ttl_even_with_a_thin_split_arm(split):
    from app.tasks.search_head_warmer import residency_invariant

    ttl = search_response_ttl_seconds("budget_exceeded", warmer_rebuild=True, futures_split_arm=split)
    assert ttl == SEARCH_RESPONSE_TTL_SECONDS
    ok, why = residency_invariant(ttl_s=ttl)
    assert ok, why


def test_the_default_leaves_every_other_caller_where_it_was():
    for outcome in _COMPLETE:
        assert search_response_ttl_seconds(outcome, warmer_rebuild=False) == SEARCH_RESPONSE_TTL_SECONDS
    for outcome in _THIN:
        assert search_response_ttl_seconds(outcome, warmer_rebuild=False) == SEARCH_THIN_RESPONSE_TTL_SECONDS


def test_the_routes_cache_write_reads_the_split_arms_own_state():
    """POSITIONAL. The write must hand the helper the split arm's REPORTED state —
    the same dict `debug_timing` prints as `futures_split_arm`. Without the
    keyword the helper falls back to `absent` and this ship changes nothing."""
    from app.routes import events

    tree = ast.parse(textwrap.dedent(inspect.getsource(events.search_events)))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "search_response_ttl_seconds"
    ]
    assert len(calls) == 1, f"expected one TTL decision in search_events, found {len(calls)}"
    kw = {k.arg: k.value for k in calls[0].keywords}
    split = kw.get("futures_split_arm")
    assert (
        isinstance(split, ast.Subscript)
        and isinstance(split.value, ast.Name)
        and split.value.id == "_futures_split_report"
        and isinstance(split.slice, ast.Constant)
        and split.slice.value == "state"
    ), f"futures_split_arm is not _futures_split_report['state']: {split and ast.dump(split)}"


def test_the_split_report_carries_only_states_the_rule_has_decided():
    """A new split-arm state must be sorted into thin or complete, not default."""
    from app.routes import events

    src = textwrap.dedent(inspect.getsource(events))
    assigned = {
        node.value.value
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_split_state" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    }
    assert assigned, "found no `_split_state = \"<state>\"` assignment"
    assert assigned <= set(_THIN + _COMPLETE), sorted(assigned - set(_THIN + _COMPLETE))
