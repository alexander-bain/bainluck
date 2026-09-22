"""#8044 — three runners vanished from a settled board instead of losing a number.

THE DEFECT THIS GUARDS. `https://bainluck.com/events/14780545`, Rams 28 – Giants 6,
FINAL. The *1st Touchdown* board served **28** runners before #7987 went live and
**25** after it. Puka Nacua, Jordan Whittington and CJ Daniels were not shown
without a price and not shown as ungraded: they were ABSENT. A reader who knows
the card has no way to tell whether those three were scratched, never listed, or
quietly dropped.

═══ 🔴 WHAT IS **NOT** THE BUG ═══

**#7987's writer half is correct and must not be reverted.** Those three legs read
`finalized` / `result: "scalar"` at Kalshi: the venue answered on a NUMBER, so
there is no side to grade, and #1852 established that grading a scalar as a loss
poisons the calibration curve. Withdrawing their fossil 9% / 3% / 1% was right.
This is the serve-side surface that correct write newly reaches.

**The 24 graded losers are also not the bug**, and they are why a fix keyed on the
SERVED null would be wrong. They are stored `0.000000`, not NULL, so they clear the
dropped-row guard — and are then served `"probability": null` anyway by
`round(prob, 4) if prob else None`, because `0.0` is falsy. Their grade badge
carries the meaning, so that reads correctly today. Two paths reach an identical
`probability: null` in the payload for opposite reasons; the predicate under test
keys on the STORED columns, where they are still distinguishable.

═══ THE MECHANISM ═══

`routes/events.py`, the `other`-market outcome loop: `prob = ... else None` then
`if prob is None: continue`. The leg is skipped before it can reach
`other_markets`, so it never appears in the payload at all. The guard predates
#7987 by a long way; #7987 merely created the first population it deletes rows
from.

═══ WHY THE SCOPE IS THE POINT OF THIS FILE ═══

14,743 priceless legs sit on 586 finished events (production, 30 days, measured
2026-09-22). Serving all of them would not repair a board, it would rewrite one.
The issue's acceptance names one control and production showed the other:

  * a leg that NEVER carried a price is unlisted, not withheld — 11,327 of the
    14,743                                  -> `TestAnUnlistedLegIsNotAWithheldOne`
  * a live board must not newly carry priceless rows — 1,814 legs
                                            -> `TestALiveBoardIsUntouched`
  * the settled-rendering path must not move -> `TestTheGradedRowsAreUnmoved`

🔴 THE ASSERTION THIS FILE REFUSES TO MAKE is "the route returned 28 rows". Nothing
here owns a database, so that could only be asserted against a fake session
returning what it was told — a property of the fixture, not of the ship. That was
`test_the_leg_is_withheld_not_dropped`'s mistake in #7747's file. The decision is
guarded behaviourally on the real predicate, and the WIRING — that the route asks
it at all — is pinned separately, because a predicate nothing calls is the failure
mode this repo has paid for most often.
"""

import inspect
from types import SimpleNamespace

import pytest

from app.utils.settled_price import priceless_leg_keeps_its_row


def leg(current=None, opening=None):
    """A `FuturesOutcome`-shaped row, stored values only.

    The two columns this predicate reads are the two the specimens differ on;
    nothing else about an outcome is consulted, and a fixture that carried more
    would invite a reader to think it was.
    """
    return SimpleNamespace(current_probability=current, opening_probability=opening)


# ── 1. THE SHIPPED POPULATION ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,opening",
    [("Puka Nacua", 0.100), ("Jordan Whittington", 0.020), ("CJ Daniels", 0.015)],
)
def test_the_three_specimens_keep_their_row(name, opening):
    """The exact production rows, with their real opening prices.

    Spelled one per specimen rather than as a single representative case: these
    three are the issue, and a regression that resurrected only the largest of
    them would still be the defect for the other two.
    """
    assert priceless_leg_keeps_its_row(
        leg(current=None, opening=opening), event_is_finished=True
    ) is True


# ── 2. THE CONTROLS — each condition alone is unsound ────────────────────────


class TestAnUnlistedLegIsNotAWithheldOne:
    """`opening_probability IS NULL` — 11,327 of the 14,743. New content, not a
    repaired row."""

    def test_a_leg_that_never_carried_a_price_stays_hidden(self):
        assert priceless_leg_keeps_its_row(
            leg(current=None, opening=None), event_is_finished=True
        ) is False

    def test_an_opening_of_exactly_zero_still_counts_as_having_been_priced(self):
        """0.0 is a PRICE — "we quoted this at nothing" — not an absence.

        The bug class this pins is the one the 24 graded losers already exhibit
        one layer up: `if opening` would read a stored `0.000000` as missing and
        hide a leg we really did quote. The predicate tests `is not None`, and
        this asserts it stays that way.
        """
        assert priceless_leg_keeps_its_row(
            leg(current=None, opening=0.0), event_is_finished=True
        ) is True


class TestALiveBoardIsUntouched:
    """`event_is_finished` — the 1,814 once-priced-now-null legs on unfinished
    events are deliberately out of scope (acceptance control 2)."""

    def test_a_withdrawn_price_on_a_live_board_is_not_newly_introduced(self):
        assert priceless_leg_keeps_its_row(
            leg(current=None, opening=0.100), event_is_finished=False
        ) is False

    def test_an_unlisted_leg_on_a_live_board_stays_hidden_too(self):
        assert priceless_leg_keeps_its_row(
            leg(current=None, opening=None), event_is_finished=False
        ) is False


class TestTheGradedRowsAreUnmoved:
    """A leg that HAS a price is not this predicate's business.

    The settled-rendering path is what #7537/#7747/#8011 built and the issue's
    first control forbids moving it: the graded winner must still serve its
    verdict and the 24 graded losers theirs. All of them hold a stored price and
    never reach this predicate in the route — this pins that it would decline
    them even if they did, so a future caller cannot borrow it into a surface it
    has not reasoned about.
    """

    @pytest.mark.parametrize("current", [1.0, 0.0, 0.5])
    def test_a_priced_leg_is_declined(self, current):
        assert priceless_leg_keeps_its_row(
            leg(current=current, opening=0.055), event_is_finished=True
        ) is False

    def test_the_graded_loser_stored_zero_is_declined_on_its_stored_value(self):
        """`0.000000` is the 24 losers' stored price and is FALSY in Python.

        A predicate written `if outcome.current_probability:` would treat every
        graded loser as priceless and hand it back to the caller as a withheld
        row — which on a settled board is 24 rows losing their `Lost` badge. The
        `is not None` test is what prevents it and this is the mutant that
        catches a change to it.
        """
        assert priceless_leg_keeps_its_row(
            leg(current=0.0, opening=0.055), event_is_finished=True
        ) is False


# ── 3. THE WIRING — a predicate nothing calls is not a fix ───────────────────


class TestTheRouteActuallyAsksIt:
    """The #8044 failure mode most likely to recur is an UNWIRED repair.

    The decision above is correct in isolation and worth nothing unless the
    serve path consults it. `events.py` is 20k lines and its outcome loop is not
    importable on its own, so the call is pinned on the route module's own
    source — the one statement about this ship that a behavioural test on the
    predicate structurally cannot make.
    """

    def test_the_game_markets_loop_calls_the_predicate(self):
        from app.routes import events as events_module

        src = inspect.getsource(events_module)
        assert "priceless_leg_keeps_its_row(" in src, (
            "the game-markets outcome loop no longer consults the predicate; a "
            "priceless leg is being dropped again (#8044)"
        )

    def test_the_predicate_is_imported_rather_than_reimplemented(self):
        """One implementation, not a second copy in the route.

        `settled_price.py` exists because #5246 shipped inert as two lines at one
        call site while the live writers were elsewhere — "a settlement writer is
        a population, not a place". The serve half inherits that rule.
        """
        from app.routes import events as events_module

        assert getattr(events_module, "priceless_leg_keeps_its_row", None) is (
            priceless_leg_keeps_its_row
        ), "events.py must use the shared predicate, not a local re-implementation"

    def test_the_player_prop_rescues_still_require_a_number(self):
        """Both rescues compute `1.0 - prob`; a withheld leg must not reach them.

        Letting a priceless leg past the dropped-row guard is only safe because
        the two rescue branches below it are gated on `prob is not None`. If a
        future edit removes those gates the loop raises `TypeError` on the first
        withheld leg and the whole board 500s — a strictly worse outcome than the
        defect this ship repairs.
        """
        from app.routes import events as events_module

        src = inspect.getsource(events_module)
        assert "if prob is not None and _PLAYER_OUTCOME_RE.match(o.name):" in src, (
            "the player-outcome rescue lost its `prob is not None` gate; a "
            "withheld leg now reaches `1.0 - prob` (#8044)"
        )
        assert "prob is not None\n                    and _PLAYER_PROP_RE.search(market.name)" in src, (
            "the market-name rescue lost its `prob is not None` gate; a withheld "
            "leg now reaches `1.0 - prob` (#8044)"
        )
