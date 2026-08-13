"""The settledness authority — #1812, #1803's real blast radius, ruling 036.

UX-P069. What these tests are FOR, stated up front because the previous round of
this fix was guarded by a test that transcribed the expression it checked and
therefore bound nothing:

* the monotonicity guarantee is a PROPERTY, not a case analysis;
* an event in play is BIT-IDENTICAL to the pre-#1803 inference, per adapter;
* every adapter CALLS the authority (source-bound) rather than re-typing it;
* the term each adapter supplies is genuinely ASSIGNED and not price-derived —
  the guard that stops the fix from quietly chaining two inferences;
* election's non-atomicity is pinned, because it is the one adapter for which the
  parent must NOT settle the children.

No test here branches on the clock (gotcha #44); nothing here takes `now` at all.
"""

from __future__ import annotations

import inspect

import pytest

from app.utils.settledness import (
    CONVERGED_HIGH,
    CONVERGED_LOW,
    market_assigned_settled,
    price_converged,
    settled_under_assigned_state,
)


# --- the combinator ---------------------------------------------------------


def test_monotone_the_assigned_term_can_only_RAISE_settledness():
    """The whole guarantee, over every input rather than the cases we thought of.

    If this holds, "over-suppression" is unrepresentable: there is no pair of
    inputs for which consulting assigned state makes a child LESS settled.
    """
    for inferred in (True, False):
        for assigned in (True, False):
            combined = settled_under_assigned_state(
                inferred=inferred, assigned_settled=assigned
            )
            assert combined >= inferred, (
                f"NON-MONOTONE: inferred={inferred} assigned={assigned} -> {combined}. "
                "The assigned term must never remove settledness."
            )


def test_in_play_is_BIT_IDENTICAL_to_the_old_inference():
    """An event still in play must decide exactly as it always did.

    This is the promise that let the fix ship without re-validating live pages:
    with `assigned_settled` False the authority IS the legacy expression.
    """
    for lead_prob in (None, 0.0, 0.03, 0.031, 0.5, 0.9, 0.969, 0.97, 1.0):
        legacy = lead_prob is not None and (lead_prob >= 0.97 or lead_prob <= 0.03)
        assert (
            settled_under_assigned_state(
                inferred=price_converged(lead_prob), assigned_settled=False
            )
            is legacy
        ), f"in-play behaviour changed at lead_prob={lead_prob}"


def test_a_settled_event_settles_the_coin_flip_that_never_converged():
    """#1803's actual specimen, as a unit: `event:ufc:26aug08` rendered a fought
    bout at 0.54/0.44. The price test says live; the card says settled."""
    assert price_converged(0.54) is False
    assert settled_under_assigned_state(inferred=price_converged(0.54), assigned_settled=True)


# --- the inference ----------------------------------------------------------


@pytest.mark.parametrize(
    "lead_prob,expected",
    [
        (None, False),
        (0.5, False),
        (0.9, False),
        (CONVERGED_HIGH - 0.001, False),
        (CONVERGED_HIGH, True),
        (1.0, True),
        (CONVERGED_LOW, True),
        (CONVERGED_LOW + 0.001, False),
        (0.0, True),
    ],
)
def test_price_converged_band_is_inclusive_at_both_edges(lead_prob, expected):
    assert price_converged(lead_prob) is expected


# --- the per-child assigned term --------------------------------------------


class _Outcome:
    def __init__(self, is_winner=False):
        self.is_winner = is_winner


class _Market:
    def __init__(self, status=None, outcomes=None):
        self.status = status
        self.outcomes = outcomes or []


@pytest.mark.parametrize("status", ["resolved", "closed", "settled", "final", "SETTLED"])
def test_a_source_closed_market_is_assigned_settled(status):
    assert market_assigned_settled(_Market(status=status)) is True


def test_an_open_market_with_a_graded_outcome_is_assigned_settled():
    """Gotcha #33 is the whole reason this arm exists: Kalshi leaves settled
    markets `status='open'`, so the GRADE, not the status, is usually the signal."""
    m = _Market(status="open", outcomes=[_Outcome(False), _Outcome(True)])
    assert market_assigned_settled(m) is True


def test_an_open_ungraded_market_is_NOT_assigned_settled():
    m = _Market(status="open", outcomes=[_Outcome(False), _Outcome(False)])
    assert market_assigned_settled(m) is False


def test_a_partially_loaded_row_degrades_to_unknown_rather_than_throwing():
    """A lookup must never throw the page. Absence of an attribute is 'unknown',
    which under a monotone `or` costs nothing."""

    class _Bare:
        pass

    assert market_assigned_settled(_Bare()) is False


def test_explicit_outcomes_win_over_the_relationship():
    """Callers pass an already field/placeholder-filtered list; it must be used."""
    m = _Market(status="open", outcomes=[_Outcome(True)])
    assert market_assigned_settled(m, outcomes=[]) is False


# --- source binding: every adapter CALLS the authority ----------------------

_ADAPTER_MODULES = [
    "app.utils.event_combat",
    "app.utils.event_cycling",
    "app.utils.event_tennis",
    "app.utils.event_awards",
    "app.utils.event_election",
]


@pytest.mark.parametrize("modname", _ADAPTER_MODULES)
def test_the_adapter_CALLS_the_authority_rather_than_transcribing_it(modname):
    """UX-P068's recorded limitation, closed.

    Cycling's guard transcribed the expression under test, so the only thing
    binding the source was an `inspect.getsource` assert — and a transcription
    test proves the logic is right while saying nothing about whether the code
    uses it. Five adapters, one authority, asserted at the source.
    """
    import importlib

    src = inspect.getsource(importlib.import_module(modname))
    assert "settled_under_assigned_state(" in src, (
        f"{modname} no longer calls the settledness authority — if the policy was "
        "re-inlined, the next change to it will only reach one of six adapters."
    )


# The term each adapter must actually PASS. Asserting the call exists is not
# enough — a plant that replaced tennis's whole term with `assigned_settled=False`
# left every other guard in this file green, which is the #1803 defect itself
# reinstated with the authority still dutifully called. (UX-P069 found this by
# planting it; the suite audits the fixture, not just the guard.)
_REQUIRED_ASSIGNED_TERM = {
    "app.utils.event_combat": ["assigned_settled=card_settled"],
    "app.utils.event_cycling": ['assigned_settled=event_status == "settled"'],
    "app.utils.event_tennis": ['event_status == "settled"', "market_assigned_settled(m, outs)"],
    "app.utils.event_awards": ["ceremony_graded", "market_assigned_settled(m, outs)"],
    "app.utils.event_election": ["market_assigned_settled(m, outs)"],
}


@pytest.mark.parametrize("modname", sorted(_REQUIRED_ASSIGNED_TERM))
def test_the_adapter_passes_a_REAL_assigned_term_not_a_constant(modname):
    """The positive half of the guard: the term is present, and it is not `False`.

    Dropping the term is the cheapest possible regression — the call site keeps
    calling the authority, every structural assertion still holds, and the adapter
    silently reverts to the pure price inference.
    """
    import importlib

    src = inspect.getsource(importlib.import_module(modname))
    call = src[src.index("settled_under_assigned_state(") :][:500]
    assert "assigned_settled=False" not in call, (
        f"{modname} passes a constant False as its assigned term — that is the "
        "pre-#1803 behaviour with the fix's shape bolted on top."
    )
    for term in _REQUIRED_ASSIGNED_TERM[modname]:
        assert term in call, f"{modname} no longer passes its assigned term `{term}`"


@pytest.mark.parametrize("modname", _ADAPTER_MODULES)
def test_no_adapter_re_inlines_the_convergence_band(modname):
    """The literal that was copied into six files. It must not come back."""
    import importlib

    src = inspect.getsource(importlib.import_module(modname))
    assert "lead_prob >= 0.97" not in src, (
        f"{modname} re-inlined the convergence band. Use `price_converged`."
    )


# --- the anti-chaining guard ------------------------------------------------


def test_awards_does_not_pass_a_price_derived_term_as_assigned_state():
    """Monotonicity protects the direction, NOT the input.

    `event_awards.event_status` is itself set from `marquee_top >=
    _WON_PRICE_THRESHOLD`, so passing it as `assigned_settled` would chain two
    inferences — and would newly mark every category settled the moment one
    runaway favourite crossed 0.97. The term must be the graded one.
    """
    from app.utils import event_awards

    src = inspect.getsource(event_awards)
    call = src[src.index("settled = settled_under_assigned_state(") :][:400]
    assert "ceremony_graded" in call, "awards must pass the graded term"
    assert "event_status" not in call, (
        "awards passed `event_status` as assigned state — it is price-derived "
        "(the `marquee_top >= _WON_PRICE_THRESHOLD` arm)."
    )
    assert "_WON_PRICE_THRESHOLD" not in call


def test_the_awards_graded_term_is_captured_BEFORE_the_price_crown_writes_won():
    """Ordering, asserted — the crown block writes `won = True` onto a
    price-settled leader, so reading `any(c["won"])` after it would silently
    re-admit the inference the term exists to exclude."""
    from app.utils import event_awards

    src = inspect.getsource(event_awards)
    capture = src.index("ceremony_graded = any(")
    crown = src.index('if event_status == "settled" and not any(c["won"] for c in competitors):')
    assert capture < crown, (
        "`ceremony_graded` is now read AFTER the price-crown block, so it includes "
        "price-settled leaders. Move it back above the crown."
    )


def test_election_does_not_pass_a_price_derived_term_as_assigned_state():
    from app.utils import event_election

    src = inspect.getsource(event_election)
    call = src[src.index("settled = settled_under_assigned_state(") :][:400]
    assert "market_assigned_settled(m" in call
    assert "event_status" not in call
    assert "_WON_PRICE_THRESHOLD" not in call


# --- election is NOT atomic in time -----------------------------------------


def test_a_graded_parent_does_not_settle_an_ungraded_election_child():
    """The asymmetry that makes election the narrowest of the six.

    A fight card, a tournament, a grand tour, a slam and a ceremony conclude as
    ONE thing. Races do not — they are decided independently and runoffs run weeks
    past election night. So a called marquee race must leave an undecided House
    race rendering as live.
    """
    undecided_child = _Market(status="open", outcomes=[_Outcome(False), _Outcome(False)])
    assert (
        settled_under_assigned_state(
            inferred=price_converged(0.61),
            assigned_settled=market_assigned_settled(undecided_child),
        )
        is False
    ), "a contested down-ballot race was settled by something other than itself"


def test_election_source_passes_only_the_child_s_own_state():
    """Belt and braces on the above: the call must not reference the parent."""
    from app.utils import event_election

    src = inspect.getsource(event_election)
    call = src[src.index("settled = settled_under_assigned_state(") :][:400]
    for parent_term in ("competitors", "ceremony_graded", "marquee"):
        assert parent_term not in call, (
            f"election passed the parent term `{parent_term}`; races are not atomic "
            "in time and the parent cannot settle them."
        )


# --- tennis: the assigned term is trustworthy BECAUSE of the L2-88 demotion --


def test_tennis_relies_on_a_status_that_was_already_demoted_where_it_lies():
    """`event_status` is safe to trust here only because the L2-88 block above
    demotes a placeholder-resolution_date false-settle back to "live" BEFORE the
    children are built. If that block ever moves below the child loop, the
    monotone term starts settling live matches."""
    from app.utils import event_tennis

    src = inspect.getsource(event_tennis)
    demotion = src.index('            event_status = "live"')
    child_call = src.index("settled = settled_under_assigned_state(")
    assert demotion < child_call, (
        "the L2-88 demotion now runs AFTER the children are built, so a tennis "
        "final still being played would be marked settled."
    )
