"""#9947 — a slow moment must not pin a player's title-only answer for three minutes.

THE SHIP (DISCOVER): typing a player (`ohtani`) shows the open boards they are
priced on — World Series MVP, Championship Series MVP — as `freddie freeman` does.

Those boards reach `/search` through the futures OUTCOME arm (a leg names the
player; the title does not). The arm runs inside its own 1,000 ms bound
(LAT-P271) and, when it blows it, the page carries the title matches alone —
for `ohtani`, the MLB The Show cover prop and "Cy Young and MVP Winner". That
answer is not `degraded`, so it used to be written to the response cache for the
full 180 s ceiling. Production 2026-09-30, release fe46e609 (22:00Z): `ohtani`
served 2 futures at 22:0xZ and 10 (both MVP boards, arm `merged` in 173 ms) at
22:1xZ, on the same code.

It must NOT simply become uncacheable: `f1 winner` / `f1 champion` blow the bound
on every read (1,654 / 2,183 ms futures stage, both `budget_exceeded`), and they
would lose their cache entirely. So the thin answer keeps a short life on the
reader's path, and the warmer — which rebuilds the head every pass — keeps the
full TTL its residency proof needs.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.utils.search_cache import (
    SEARCH_RESPONSE_TTL_SECONDS,
    SEARCH_THIN_RESPONSE_TTL_SECONDS,
    THIN_FUTURES_OUTCOME_ARM_STATES,
    search_response_ttl_seconds,
)

#: Every state `_fetch_futures_window` can report, plus the route's own
#: `not_reached` initial value. Listed here rather than imported so a NEW state
#: added to the window without a decision about its cache life reddens below.
_ALL_ARM_STATES = ("absent", "skipped", "shed", "budget_exceeded", "merged", "not_reached")


@pytest.mark.parametrize("state", ["shed", "budget_exceeded"])
def test_a_readers_thin_answer_gets_the_short_life(state):
    assert (
        search_response_ttl_seconds(state, warmer_rebuild=False)
        == SEARCH_THIN_RESPONSE_TTL_SECONDS
    )


@pytest.mark.parametrize("state", ["absent", "skipped", "merged", "not_reached"])
def test_a_complete_answer_keeps_the_ruled_ceiling(state):
    """Control: the healthy path is untouched — `freddie freeman`'s answer still
    lives the D81 ceiling. `not_reached` never reaches the write (the shed futures
    stage marks `degraded`), and is listed so that stays a decision, not luck."""
    assert (
        search_response_ttl_seconds(state, warmer_rebuild=False)
        == SEARCH_RESPONSE_TTL_SECONDS
    )


@pytest.mark.parametrize("state", _ALL_ARM_STATES)
def test_a_warmer_rebuild_keeps_the_full_ttl_even_when_thin(state):
    """The head is rebuilt every pass, and `residency_invariant()` needs 160 s of
    life. A 30 s head entry would re-open D81's hole for exactly the head terms
    that are always thin (`f1 winner`)."""
    from app.tasks.search_head_warmer import residency_invariant

    ttl = search_response_ttl_seconds(state, warmer_rebuild=True)
    assert ttl == SEARCH_RESPONSE_TTL_SECONDS
    ok, why = residency_invariant(ttl_s=ttl)
    assert ok, why


def test_the_thin_set_is_exactly_the_two_name_matches_alone_states():
    assert THIN_FUTURES_OUTCOME_ARM_STATES == frozenset({"shed", "budget_exceeded"})
    assert THIN_FUTURES_OUTCOME_ARM_STATES <= set(_ALL_ARM_STATES)


def test_the_short_life_is_shorter_than_the_ceiling_and_still_a_cache():
    """Shorter only — never a longer life than D81 — and never 0, which Redis
    `SETEX` refuses and which would make the always-thin query uncacheable."""
    assert 0 < SEARCH_THIN_RESPONSE_TTL_SECONDS < SEARCH_RESPONSE_TTL_SECONDS


def test_every_window_state_is_one_the_ttl_rule_has_decided():
    """A new arm state must be sorted into thin-or-complete, not default silently."""
    from app.routes import events

    src = inspect.getsource(events._fetch_futures_window)
    returned = {
        node.value.elts[1].value
        for node in ast.walk(ast.parse(textwrap.dedent(src)))
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Tuple)
        and len(node.value.elts) == 2
        and isinstance(node.value.elts[1], ast.Constant)
    }
    assert returned, "found no `return rows, \"<state>\"` in _fetch_futures_window"
    assert returned <= set(_ALL_ARM_STATES), (
        f"_fetch_futures_window reports states the cache TTL rule has never "
        f"decided: {sorted(returned - set(_ALL_ARM_STATES))}"
    )


def _route_setex_calls() -> list[ast.Call]:
    from app.routes import events

    tree = ast.parse(textwrap.dedent(inspect.getsource(events.search_events)))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setex"
    ]


def test_the_routes_cache_write_takes_its_life_from_the_arm_state():
    """POSITIONAL. The write's TTL argument must BE the helper call, fed the
    route's real arm state and the warmer flag — a helper that exists but is not
    what the write reads changes nothing (the pre-#9947 write passed the bare
    ceiling here, and this test is RED against it)."""
    calls = _route_setex_calls()
    assert len(calls) == 1, f"expected one cache write in search_events, found {len(calls)}"
    ttl_arg = calls[0].args[1]
    assert (
        isinstance(ttl_arg, ast.Call)
        and isinstance(ttl_arg.func, ast.Name)
        and ttl_arg.func.id == "search_response_ttl_seconds"
    ), f"the cache write's TTL is not search_response_ttl_seconds(...): {ast.dump(ttl_arg)}"

    assert [a.id for a in ttl_arg.args if isinstance(a, ast.Name)] == ["_futures_outcome_arm"], (
        "the TTL must be decided by the futures outcome arm's own state"
    )
    kw = {k.arg: k.value for k in ttl_arg.keywords}
    flag = kw.get("warmer_rebuild")
    assert (
        isinstance(flag, ast.Call)
        and isinstance(flag.func, ast.Attribute)
        and flag.func.attr == "get"
        and isinstance(flag.func.value, ast.Name)
        and flag.func.value.id == "_force_search_cache_rebuild"
    ), "warmer_rebuild must read the warmer's own ContextVar, or the head loses residency"
