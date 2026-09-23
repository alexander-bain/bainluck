"""A settled multi-leg Kalshi board is read per leg — and the 38% is not graded.

#2077. ``classify_kalshi`` held a payload that named every leg's verdict and threw
it away: an event-200 whose ``markets`` list was non-empty answered
``AMBIGUOUS_EMPTY`` — *"do not interpret"*. Our ``external_id`` is the EVENT ticker
on ~96% of rows, so the market call 404s and that branch is where almost every
settled Kalshi board landed.

THE MEASUREMENT THAT SHAPED THIS FILE, and the reason it is not simply "grade the
boards". 42 age-stratified boards inside the retention wall (``ntile(6)``, 7 per
stratum), split by the actual ``result`` VALUE rather than by its presence:

    NAMED_WINNER   (``yes``/``no``)      12   29%   write the verdict
    SCALAR_ONLY                          16   38%   price-down only, NEVER is_winner
    NO_REAL_RESULT (``closed``, ``''``)  11   26%   leave it
    PURGED_EMPTY                          3    7%   the wall is real

Legs: 167 ``no``, 156 ``yes``, **73 ``scalar``**, 27 empty. The first pass at this
repair scored 67% recoverable by asking "is the result non-empty?" — because
``scalar`` is absent from ``_KALSHI_NON_RESULTS``. Grading that 38% would write
~1,800 false verdicts: #6619 (608 rows) at roughly three times the scale, on the
authority rung ``is_downgrade`` protects from later correction.

So every test below is written against the SPLIT, not against the count. The
per-leg reader is only safe because it refuses two thirds of what it reads.
"""

from __future__ import annotations

import pytest

from app.utils.kalshi_market_status import (
    KNOWN_STATUSES,
    NON_VERDICT_RESULTS,
    gradeable_winner,
    settled_without_verdict,
)
from app.utils.settlement_sweep_query import (
    RETRYABLE_DISPOSITIONS,
    TERMINAL_DISPOSITIONS,
)
from app.utils.settlement_truth import (
    Disposition,
    LegSettlement,
    ProbeOutcome,
    SettlementClaim,
    UnverifiedGradingRefused,
    assert_grading_licensed,
    classify_kalshi,
)

#: A leg in each of the three states the venue actually produces, verbatim in the
#: shape ``GET /events/{ticker}`` returns them. Read from the live public API
#: 2026-09-22 — the ``yes``/``no`` pair off ``KXNASDAQ100U-26AUG17H1200`` (400
#: legs, 216/184) and the ``scalar`` off ``KXATPDOUBLES-26JUL30CASGLADOUREB``.
WON = {"ticker": "KXNASDAQ100U-26AUG17H1200-T27999.99", "status": "finalized", "result": "yes"}
LOST = {"ticker": "KXNASDAQ100U-26AUG17H1200-T28009.99", "status": "finalized", "result": "no"}
SCALAR = {"ticker": "KXATPDOUBLES-26JUL30CASGLADOUREB-CASGLA", "status": "finalized", "result": "scalar"}
TRADING = {"ticker": "KXNASDAQ100U-26AUG17H1200-T28019.99", "status": "active", "result": ""}
CLOSED_UNCALLED = {"ticker": "KXNASDAQ100U-26AUG17H1200-T28029.99", "status": "closed", "result": ""}


def board(*legs: dict) -> ProbeOutcome:
    """Classify an event-200 listing ``legs`` after the market call 404s."""
    return classify_kalshi(404, None, 200, {"markets": list(legs)})


def leg_by_id(out: ProbeOutcome, external_id: str) -> LegSettlement:
    return next(leg for leg in out.leg_claims if leg.external_id == external_id)


class TestTheBoardIsReadInsteadOfDiscarded:
    """The ship: a settled board stops answering "do not interpret"."""

    def test_a_fully_settled_board_grades_every_leg(self):
        out = board(WON, LOST)
        assert out.disposition is Disposition.SETTLED_PER_LEG
        assert leg_by_id(out, WON["ticker"]).is_winner is True
        assert leg_by_id(out, LOST["ticker"]).is_winner is False

    def test_the_leg_id_is_the_venue_ticker_verbatim(self):
        """The join to ``futures_outcomes.external_id`` is exact string equality.

        Verified both sides on production rows: our outcome for that board carries
        ``KXNASDAQ100U-26AUG17H1200-T27999.99`` and so does the venue. A reader who
        assumed a name match, a prefix strip or a normalisation would find the
        tests still green, so this asserts the byte-for-byte identity directly.
        """
        out = board(WON)
        assert [leg.external_id for leg in out.leg_claims] == [WON["ticker"]]

    def test_the_old_refusal_is_gone_for_a_readable_board(self):
        """The regression this ships against, named as its own assertion."""
        assert board(WON, LOST).disposition is not Disposition.AMBIGUOUS_EMPTY

    def test_a_board_carries_no_single_claim_however_uniform(self):
        """400 legs settling the same way still name no board-level winner.

        The tempting shortcut is "every leg says yes, so the board says yes". It
        is wrong for a threshold ladder, where 216 ``yes`` and 184 ``no`` is the
        NORMAL settled shape, and the type refuses to represent it at all.
        """
        out = board(WON, WON | {"ticker": "KXX-T2"})
        assert out.claim is None


class TestTheThirtyEightPercentIsNeverGraded:
    """`result='scalar'` is a settlement TYPE, not a verdict. The whole risk."""

    def test_a_scalar_leg_is_settled_and_carries_no_winner(self):
        out = board(SCALAR)
        leg = leg_by_id(out, SCALAR["ticker"])
        assert leg.disposition is Disposition.SETTLED_NO_VERDICT
        assert leg.is_winner is None

    def test_a_scalar_leg_does_not_license_a_grading_write(self):
        """The gate the follow-on write calls, on the leg that would poison it.

        ~1,800 rows. #1852 established that grading a ``scalar`` as a loss poisons
        the calibration curve; this is the assertion that keeps the refusal.
        """
        leg = leg_by_id(board(SCALAR), SCALAR["ticker"])
        assert leg.disposition.licenses_grading() is False
        with pytest.raises(UnverifiedGradingRefused):
            assert_grading_licensed(leg.disposition, "missing_winner")

    def test_a_named_winner_leg_DOES_license_the_write(self):
        """The control. Refusing everything would pass every test above.

        Without this, a mutant that returned ``SETTLED_NO_VERDICT`` for all four
        leg states survives the whole suite — the repair would ship inert and read
        as maximally safe.
        """
        leg = leg_by_id(board(WON), WON["ticker"])
        assert leg.disposition.licenses_grading() is True
        assert_grading_licensed(leg.disposition, "missing_winner")

    def test_scalar_on_the_market_path_is_not_a_winner_called_scalar(self):
        """The latent fourth-module bug, fixed in the same ship.

        ``_KALSHI_NON_RESULTS`` never knew about ``scalar``, so this branch scored
        it a settlement and would have written the literal string ``"scalar"``
        into ``winning_outcome``. ``backfill_winners`` and two write sites in
        ``tasks/kalshi.py`` were each bitten by this before.
        """
        out = classify_kalshi(200, {"market": {"result": "scalar", "status": "finalized"}})
        assert out.disposition is Disposition.SETTLED_NO_VERDICT
        assert out.claim is None
        assert out.disposition.licenses_grading() is False

    def test_a_named_outcome_on_the_market_path_still_settles(self):
        """The capability control for the clause above.

        Kalshi answers a multi-outcome market with the outcome NAME. Fixing the
        ``scalar`` leak with the binary allowlist would have discarded these — a
        capability regression wearing a safety fix, which is why the denylist and
        the allowlist are kept as separate constants.
        """
        out = classify_kalshi(200, {"market": {"result": "Sevilla", "status": "settled"}})
        assert out.disposition is Disposition.SETTLED
        assert out.claim.winning_outcome == "Sevilla"

    def test_scalar_is_named_in_the_shared_constant_not_a_local_copy(self):
        assert "scalar" in NON_VERDICT_RESULTS


class TestAPartialBoardIsNotStranded:
    """Terminal means never asked again. A straggling leg must survive that."""

    def test_a_board_with_one_leg_still_trading_stays_reprobable(self):
        out = board(WON, LOST, TRADING)
        assert out.disposition is Disposition.OPEN_NO_SETTLEMENT
        assert out.disposition.value in RETRYABLE_DISPOSITIONS

    def test_a_partial_board_still_hands_back_the_verdicts_it_read(self):
        """Keeping the row re-probable must not cost the legs already answered.

        Dropping them to keep the disposition tidy would re-probe the whole board
        against a retention wall that is still moving, to re-learn what this call
        already knows.
        """
        out = board(WON, LOST, TRADING)
        assert leg_by_id(out, WON["ticker"]).is_winner is True
        assert leg_by_id(out, TRADING["ticker"]).disposition is Disposition.OPEN_NO_SETTLEMENT

    def test_closed_without_a_result_is_undeclared_not_settled(self):
        """`closed` is terminal at the venue and carries NO result (#1818).

        It is the status most likely to be read as "done, therefore graded". 832
        of the 2,000 markets in the CAL-P049 measurement were this.
        """
        out = board(CLOSED_UNCALLED)
        assert out.disposition is Disposition.OPEN_NO_SETTLEMENT
        assert leg_by_id(out, CLOSED_UNCALLED["ticker"]).is_winner is None

    def test_a_fully_scalar_board_is_terminal_with_no_verdicts(self):
        """Settled, complete, and nothing to write. Both halves matter: terminal
        so it is not re-probed forever, and verdict-free so nothing is invented."""
        out = board(SCALAR, SCALAR | {"ticker": "KXX-B"})
        assert out.disposition is Disposition.SETTLED_PER_LEG
        assert out.disposition.value in TERMINAL_DISPOSITIONS
        assert all(leg.is_winner is None for leg in out.leg_claims)


class TestAnUnreadableBoardStillRefuses:
    """"Do not interpret" must stay reachable after a reader exists."""

    def test_a_leg_with_an_unknown_status_is_unreadable_not_open(self):
        out = board({"ticker": "KXX-A", "status": "quantum", "result": ""})
        assert out.disposition is Disposition.AMBIGUOUS_EMPTY
        assert out.leg_claims == ()

    def test_a_leg_with_no_ticker_cannot_be_joined_so_the_board_is_not_terminal(self):
        """A verdict we cannot attach to a row is not a verdict we can use.

        Marking the board terminal on it would strand the unjoinable leg forever.
        """
        out = board(WON, {"status": "finalized", "result": "no"})
        assert out.disposition is Disposition.OPEN_NO_SETTLEMENT
        assert [leg.external_id for leg in out.leg_claims] == [WON["ticker"]]

    def test_an_empty_markets_list_is_still_the_retention_cliff(self):
        """The branch above this one, unmoved. ``markets: []`` is PURGED, and a
        per-leg reader must not turn the cliff into an empty grading pass."""
        out = classify_kalshi(404, None, 200, {"markets": []})
        assert out.disposition is Disposition.PURGED

    def test_every_board_shape_explains_itself_with_a_tally(self):
        """A capture row a human cannot triage is why ``reason`` exists."""
        for shape in ([WON], [WON, TRADING], [{"ticker": "X", "status": "quantum"}]):
            assert "legs:" in board(*shape).reason


class TestTheTypeRefusesTheBadStates:
    """Invariants, because a docstring is not an enforcement."""

    def test_a_settled_per_leg_outcome_must_carry_legs(self):
        with pytest.raises(ValueError, match="must carry leg claims"):
            ProbeOutcome(Disposition.SETTLED_PER_LEG)

    @pytest.mark.parametrize(
        "disposition",
        [
            Disposition.PURGED,
            Disposition.TRANSPORT_ERROR,
            Disposition.AMBIGUOUS_EMPTY,
            Disposition.NOT_FOUND,
            Disposition.SETTLED_NO_VERDICT,
        ],
    )
    def test_a_disposition_that_learned_nothing_may_not_carry_legs(self, disposition):
        """Verdicts arriving under "we learned nothing" is the manufactured fact."""
        with pytest.raises(ValueError, match="may not carry leg claims"):
            ProbeOutcome(
                disposition,
                leg_claims=(LegSettlement("X", Disposition.SETTLED, is_winner=True),),
            )

    def test_a_leg_verdict_requires_the_disposition_that_licenses_it(self):
        with pytest.raises(ValueError, match="only a SETTLED leg may carry a winner"):
            LegSettlement("X", Disposition.SETTLED_NO_VERDICT, is_winner=False)

    def test_a_settled_leg_without_a_winner_is_unrepresentable(self):
        with pytest.raises(ValueError, match="must carry a winner"):
            LegSettlement("X", Disposition.SETTLED)

    def test_neither_new_disposition_may_carry_a_board_claim(self):
        for disposition in (Disposition.SETTLED_PER_LEG, Disposition.SETTLED_NO_VERDICT):
            with pytest.raises(ValueError, match="only SETTLED may carry a claim"):
                ProbeOutcome(disposition, claim=SettlementClaim("Yes", "kalshi_market"))


class TestTheVocabularyIsPartitionedDeliberately:
    """A new disposition must be PLACED, not defaulted."""

    def test_every_disposition_is_terminal_or_retryable_and_never_both(self):
        everything = {d.value for d in list(Disposition)}
        assert TERMINAL_DISPOSITIONS | RETRYABLE_DISPOSITIONS == everything
        assert not (TERMINAL_DISPOSITIONS & RETRYABLE_DISPOSITIONS)

    def test_both_settled_dispositions_are_terminal(self):
        """The venue answered. No re-probe turns a number into a side, and a
        complete board does not become more complete."""
        assert Disposition.SETTLED_NO_VERDICT.value in TERMINAL_DISPOSITIONS
        assert Disposition.SETTLED_PER_LEG.value in TERMINAL_DISPOSITIONS

    def test_board_level_grading_is_licensed_by_exactly_one_disposition(self):
        """The widening a future reader arrives intending to make.

        Per-leg grading needed NO widening here: the licence rides each leg.
        """
        assert [d for d in list(Disposition) if d.licenses_grading()] == [Disposition.SETTLED]


class TestTheHelpersAreMeasuredOnOurOwnRows:
    """A cert naming a helper is naming an assumption about that helper.

    ``gradeable_winner`` / ``settled_without_verdict`` were written for
    ``backfill_winners``, not for this reader. These pin their behaviour on the
    four leg states our sweep population actually contains, so a later change
    there cannot silently move what this classifier writes.
    """

    @pytest.mark.parametrize(
        "leg,expected_winner,expected_void",
        [
            (WON, True, False),
            (LOST, False, False),
            (SCALAR, None, True),
            (TRADING, None, False),
            (CLOSED_UNCALLED, None, False),
        ],
        ids=["yes", "no", "scalar", "active", "closed"],
    )
    def test_the_two_helpers_on_real_venue_legs(self, leg, expected_winner, expected_void):
        assert gradeable_winner(leg["status"], leg["result"]) is expected_winner
        assert settled_without_verdict(leg["status"], leg["result"]) is expected_void

    def test_every_status_our_reader_accepts_is_a_measured_one(self):
        """``KNOWN_STATUSES`` is the gate between "open" and "unreadable"."""
        for leg in (WON, LOST, SCALAR, TRADING, CLOSED_UNCALLED):
            assert leg["status"] in KNOWN_STATUSES
        assert "quantum" not in KNOWN_STATUSES
