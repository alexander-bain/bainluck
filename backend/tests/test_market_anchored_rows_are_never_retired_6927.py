"""#6927: the market refusal was nested inside the `external_id`-present branch.

`suspended_row_is_unreachable` refuses a row that still carries a market —
`polymarket` and `kalshi_resolution_sweep` both admit `status='suspended'`
explicitly, so such a row has a live door however it was minted, and retiring it
closes a door that is still open. That refusal is #6347's and it works.

It was only ever ASKED of rows whose `external_id` was present. Both the
verdict's test and the screen's `~market_anchored_exists` sat inside the same
`external_id`-present branch, so a row with no `external_id` walked past a rule
that was written for it and was never put to it. Two copies of one rule are not
a belt and braces when they hang from the same hook.

Measured on production 2026-09-18 from the arm's own record of what it retired,
`backup_unreachable_suspended_5532` — replicated independently of the lane that
filed it:

    retired since 2026-09-13 16:15:15Z         13,595
      ... carrying markets                      7,360
      ... carrying an OPEN market                 921
    retired in the trailing 24h                   332
      ... carrying markets                        296   (89%)
    last retirement before the stop       11:00:48Z

Every one came through the unguarded arm; 0 through the guarded one. The door
was closed at 11:27:08Z (`scripts/unreachable_suspended_door.py --close`) and 0
rows were retired after that instant, which is how the stop was verified.

🔴 THE FIX CAN ONLY EVER REFUSE MORE. It cannot retire a row that is refused
today — the only safe direction for an arm that writes a terminal status. The
rows already written are NOT un-retired here; that is #2693's, and it needs the
anchor channel (#1946).

WHY THE VERDICT TEST IS THE LOAD-BEARING ONE. The screen is an optimisation —
it decides which rows the budget is spent on. The verdict runs per row,
immediately before the write, and is the thing that can actually stop a
retirement. The source scan below guards the screen; the behavioural tests guard
the verdict, and they are the ones that would have caught this.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.utils.event_completion import EVENT_SUSPENDED

from tests.test_the_unreachable_suspended_row_gets_a_door_5532 import (
    NOW,
    _floor,
    _verdict,
)


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_a_market_anchored_row_with_no_external_id_is_refused():
    """The defect, stated as the row that produced 7,360 of them.

    The production specimen is a Polymarket-minted `soccer_other` fixture: no
    `external_id` at all. Before this ship the verdict never reached its market
    test for such a row and answered True.
    """
    assert _verdict(external_id=None, market_anchored=True) is False


def test_the_original_specimen_still_retires():
    """Control. #5532's whole reason for existing must be untouched — this is a
    tightening, and a tightening that also stops the intended work is a revert."""
    assert _verdict(external_id=None, market_anchored=False) is True


@pytest.mark.parametrize(
    "commence_time_source",
    ["polymarket", "kalshi_ticker", "odds_api", None],
)
def test_the_refusal_does_not_depend_on_how_the_row_was_minted(
    commence_time_source,
):
    """A market is a live door however the row was minted.

    `commence_time_source` scopes the *`external_id` is inert* question, which is
    a different question. Reading the market refusal through that scope is
    exactly the nesting this ship undoes, so it is asserted on all four values
    the column actually takes — including `None`.
    """
    assert (
        _verdict(
            external_id=None,
            market_anchored=True,
            commence_time_source=commence_time_source,
        )
        is False
    )


@pytest.mark.parametrize("external_id", [None, "", "   ", "odds-api-abc123"])
def test_the_refusal_does_not_depend_on_whether_an_external_id_is_present(
    external_id,
):
    """Both arms, including the two spellings of "an id that says nothing"."""
    assert _verdict(external_id=external_id, market_anchored=True) is False


# ---------------------------------------------------------------------------
# Fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("unanswered", [None, 0, 1, "yes", "no", ""])
def test_a_caller_that_did_not_answer_the_question_retires_nothing(unanswered):
    """`is not False`, not a truth test, mirroring the sibling helper.

    The keyword is required at every call site with no default precisely so that
    "the caller is out of date" cannot look like "the row is genuinely inert".
    A stale caller passing `0` or the string `"no"` means it has not been taught
    to ask — the honest answer to which is to retire nothing. Note `"no"` and
    `0`: a truth test would read those as *not anchored* and retire the row.
    """
    assert _verdict(external_id=None, market_anchored=unanswered) is False


def test_the_refusal_outranks_every_other_reason_the_row_looks_dead():
    """A row can be dead by every other measure and still hold an open door."""
    assert (
        _verdict(
            status=EVENT_SUSPENDED,
            commence_time=NOW - timedelta(days=900),
            external_id=None,
            espn_id=None,
            statpal_fixture_id=None,
            home_score=None,
            away_score=None,
            completed_at=None,
            anchor_acquirable=False,
            now=NOW,
            floor=_floor(),
            commence_time_source="polymarket",
            market_anchored=True,
        )
        is False
    )


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------


def test_the_screens_market_exclusion_is_not_nested_in_the_external_id_branch():
    """Structural, because the defect was structural.

    The clause was always PRESENT — `test_the_screen_carries_every_refusal_the
    _verdict_does` in #5532's file asserts presence and passed throughout. What
    was wrong was where it sat: inside the `and_(...)` that is the second arm of
    the `or_`. So presence is not the assertion; POSITION is.

    Parsed rather than sliced. A text window between two landmarks moves when
    the clause it is looking for moves, which is the one thing it must not do —
    the first draft of this test read the hoisted line as still being nested,
    because hoisting it put it inside the window.
    """
    import ast
    import inspect
    import textwrap

    from app.tasks.espn_sync import _transition_event_statuses_impl

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(_transition_event_statuses_impl))
    )

    def _names(node):
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

    def _attrs(node):
        return {
            a.attr for a in ast.walk(node) if isinstance(a, ast.Attribute)
        }

    # The screen's own `or_`, identified by the two id arms it exists to hold
    # rather than by position in the file.
    or_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "or_"
        and "external_id" in _attrs(n)
        and "commence_time_source" in _attrs(n)
    ]
    assert or_calls, "the `or_` over the two id arms is gone — re-aim this test"

    assert "market_anchored_exists" in _names(tree), "the exclusion must exist"
    for call in or_calls:
        assert "market_anchored_exists" not in _names(call), (
            "the market exclusion is back inside the `or_` — a row with no "
            "external_id is not being asked the question again (#6927)"
        )
        # And no `and_` survives in there holding it: an `and_` with one member
        # left is the same trap wearing a smaller hat.
        assert not [
            n
            for n in ast.walk(call)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "and_"
        ]
