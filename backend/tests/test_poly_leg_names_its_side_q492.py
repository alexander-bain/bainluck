"""Q492 — a Polymarket price is labelled with the side it belongs to.

THE DEFECT (measured on production 2026-08-31, `origin/master` 1cf5be34):
1,370 open Polymarket markets carried an outcome whose ``name`` was, character
for character, the market's own ``name``. The user-visible form of that, on the
US Open detail page and in search results for "Swiatek":

    US Open WTA: Iga Swiatek vs Nadia Podoroska        89.5%

89.5% of *what*? The card prints a number that names no side, and nothing on the
page lets the reader recover one. Gamma event 945779 shows why: of its 17
sub-markets exactly one has a real book (bid/ask 0.85/0.94, the moneyline) and
that one arrives with ``groupItemTitle: null`` and its question set to the event
title — so ``_extract_outcome_name``'s "short enough, use it directly" fallback
returned the whole matchup. The correct label was in the same object the whole
time: ``outcomes == ["Iga Swiatek", "Nadia Podoroska"]``, the array parallel to
``outcomePrices == ["0.895", "0.105"]``.

Same class as Q489 — a price must land on the leg whose book it is.

THE CONTROLS MATTER MORE THAN THE SHIP ASSERTION HERE. "Always use
``outcomes[0]``" would pass the ship test and destroy every informative
``groupItemTitle`` in the file ("Set 1 Winner", "33°F or below"), so the rescue
is asserted to be *conditional*, from both directions.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.tasks.polymarket import _extract_outcome_name, _leg_label

EVENT_TITLE = "US Open WTA: Iga Swiatek vs Nadia Podoroska"


class _Market:
    """The three fields ``_leg_label`` reads, shaped like ``PolymarketMarket``."""

    def __init__(self, question="", group_item_title=None, outcomes=None):
        self.question = question
        self.group_item_title = group_item_title
        self.outcomes = list(outcomes or [])


# ---------------------------------------------------------------------------
# The ship: the moneyline leg names a player, not the matchup.
# ---------------------------------------------------------------------------


def test_moneyline_leg_is_labelled_with_the_player_not_the_matchup():
    """Gamma event 945779 market 12, verbatim: no groupItemTitle, question ==
    the event title, outcomes == the two players. The label must be the player
    whose price ``outcome_prices[0]`` is."""
    moneyline = _Market(
        question=EVENT_TITLE,
        group_item_title=None,
        outcomes=["Iga Swiatek", "Nadia Podoroska"],
    )

    label = _leg_label(moneyline, EVENT_TITLE)

    assert label == "Iga Swiatek"
    # The defect stated as its own assertion, so a regression reads plainly.
    assert label != EVENT_TITLE


def test_the_unfixed_helper_still_returns_the_whole_matchup():
    """Red-first anchor: the old naming path is unchanged and still produces the
    defect, so the ship above is demonstrably ``_leg_label``'s doing and not a
    quiet edit to ``_extract_outcome_name``."""
    assert _extract_outcome_name(EVENT_TITLE, EVENT_TITLE) == EVENT_TITLE


def test_whitespace_and_case_variants_of_the_title_are_still_rescued():
    """The collapse is detected on a normalised key, not on ``==`` — Gamma has
    sent the title back with doubled spaces and different casing."""
    noisy = _Market(
        question="  us open WTA:  Iga Swiatek vs   Nadia Podoroska ",
        group_item_title=None,
        outcomes=["Iga Swiatek", "Nadia Podoroska"],
    )

    assert _leg_label(noisy, EVENT_TITLE) == "Iga Swiatek"


# ---------------------------------------------------------------------------
# Non-vacuity control 1 — the rescue is CONDITIONAL. An informative
# groupItemTitle survives untouched. "Always use outcomes[0]" fails here.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "group_item_title, outcomes, expected",
    [
        # Gamma event 945779 market 5, verbatim. outcomes[0] is "Swiatek", but
        # relabelling would silently turn the Set-1 market into a duplicate of
        # the moneyline.
        (
            f"{EVENT_TITLE} Set 1 Winner",
            ["Swiatek", "Podoroska"],
            f"{EVENT_TITLE} Set 1 Winner",
        ),
        # Gamma event 945779 market 0, verbatim.
        (
            f"{EVENT_TITLE} Match O/U 21.5",
            ["Over", "Under"],
            f"{EVENT_TITLE} Match O/U 21.5",
        ),
        # A weather ladder rung — the case the original comment named.
        ("33°F or below", ["Yes", "No"], "33°F or below"),
        # A negRisk candidate leg: groupItemTitle already names the side.
        ("Los Angeles Lakers", ["Yes", "No"], "Los Angeles Lakers"),
    ],
)
def test_an_informative_group_item_title_is_never_overwritten(
    group_item_title, outcomes, expected
):
    market = _Market(
        question="ignored when groupItemTitle is present",
        group_item_title=group_item_title,
        outcomes=outcomes,
    )

    assert _leg_label(market, EVENT_TITLE) == expected


def test_question_parsing_still_wins_when_it_names_a_side():
    """A negRisk "Will X win…" question is not a collapse, so the extractor's
    answer stands and ``outcomes[0]`` ("Yes") is never consulted."""
    leg = _Market(
        question="Will the Los Angeles Lakers win the 2025-26 NBA Championship?",
        group_item_title=None,
        outcomes=["Yes", "No"],
    )

    assert _leg_label(leg, "NBA Championship 2025-26") == "Los Angeles Lakers"


# ---------------------------------------------------------------------------
# Non-vacuity control 2 — a Yes/No token is not a rescue. Relabelling a
# collapsed leg "Yes" trades one uninformative label for a worse one.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tokens", [["Yes", "No"], ["no", "yes"], ["YES", "NO"], [], [""]])
def test_a_collapsed_leg_is_not_relabelled_yes_or_no(tokens):
    collapsed = _Market(
        question=EVENT_TITLE, group_item_title=None, outcomes=tokens
    )

    assert _leg_label(collapsed, EVENT_TITLE) == EVENT_TITLE


def test_a_token_that_is_itself_the_title_is_not_a_rescue():
    """Gamma occasionally echoes the event title into the token array; swapping
    one copy of the title for another is not a fix."""
    echoed = _Market(
        question=EVENT_TITLE, group_item_title=None, outcomes=[EVENT_TITLE, "No"]
    )

    assert _leg_label(echoed, EVENT_TITLE) == EVENT_TITLE


def test_a_market_with_no_outcomes_attribute_does_not_crash():
    """``_leg_label`` runs inside the hourly poll's per-event loop; a shape it
    does not expect must not take the batch down."""

    class _Bare:
        question = EVENT_TITLE
        group_item_title = None

    assert _leg_label(_Bare(), EVENT_TITLE) == EVENT_TITLE


# ---------------------------------------------------------------------------
# The ship must actually be WIRED. A pure function nobody calls fixes nothing —
# and both writers resolve ``outcome_prices[0]``, so both must use it.
# ---------------------------------------------------------------------------


def _outcome_name_assignments() -> list[ast.Assign]:
    """Every ``outcome_name = ...`` statement in the polling module.

    RAISES rather than returning empty when the module cannot be parsed or the
    assignments have moved — a source scan that silently finds nothing is a
    guard that silently stops guarding.
    """
    source = Path(inspect.getsourcefile(_leg_label)).read_text()
    tree = ast.parse(source)
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "outcome_name" for t in node.targets
        )
    ]
    if not found:
        raise AssertionError(
            "no `outcome_name = ...` assignment found in app/tasks/polymarket.py — "
            "the Q492 wiring guard can no longer see what it is guarding; "
            "re-point it rather than deleting it"
        )
    return found


def test_both_price_writers_name_their_leg_through_the_fix():
    """The negRisk writer and the game-level parent-anchor writer both take
    ``outcome_prices[0]``, so both must label it through ``_leg_label``."""
    assignments = _outcome_name_assignments()

    # Two writers today. If a third appears, this fails loudly and on purpose.
    assert len(assignments) == 2, (
        f"expected 2 `outcome_name` writers, found {len(assignments)} — a new "
        "Polymarket price writer must also name its leg through _leg_label"
    )

    for node in assignments:
        call = node.value
        assert isinstance(call, ast.Call), (
            f"line {node.lineno}: outcome_name is not assigned from a call"
        )
        assert isinstance(call.func, ast.Name) and call.func.id == "_leg_label", (
            f"line {node.lineno}: outcome_name is assigned from "
            f"{ast.dump(call.func)[:80]}, not _leg_label — this is the exact "
            "shape that shipped a price labelled with its own market's name"
        )


def test_the_wiring_guard_can_fail():
    """Non-vacuity for the scan above: it must reject the pre-fix shape."""
    pre_fix = ast.parse(
        "outcome_name = market.group_item_title or "
        "_extract_outcome_name(market.question, event.title)"
    )
    assign = pre_fix.body[0]
    call = assign.value

    # The pre-fix RHS is a BoolOp, not a _leg_label Call — the assertion the
    # wiring test makes is the one that would have caught the defect.
    assert not (isinstance(call, ast.Call) and getattr(call.func, "id", None) == "_leg_label")
