"""#7702 — "Settled" stops being a caption for a refusal.

THE DEFECT, PHOTOGRAPHED ON PRODUCTION 2026-09-21 06:1xZ.
``/events/15310805`` (Tijuana de Caliente vs Queretaro, nine days past its own
start) served the entire hero as::

    ✎ Settled                       Sep 11, 2026 · 9:00 PM PDT
      CAL Caliente                    QUE Queretaro

No score, no probability, no winner — and not even the "No price" line, because
#6438 suppresses that on the stated grounds that "the settled pill in this same
card already carries the result". On ``/search?q=Queretaro`` at 390px the same
row is a card reading **"Settled · Sep 11"** over two team names and nothing
else, one card above a sibling in the identical state reading the honest thing,
``No result reported · Sep 19``.

THE TWO STANDARDS OVER ONE SET OF ROWS
--------------------------------------

``settlement_from_graded_rows`` keyed the CLAIM on ``graded`` being non-empty
and the CONTENT on the far stricter question "did a namer admit any of these
legs". Where they disagreed only the claim survived. The specimen's two
``is_winner IS TRUE`` legs, read off production:

    Team Total           → "Queretaro over 0.5 goals"   not a score, not a moneyline
    Second Half Winner   → "Tie 2nd Half"               a HALF, not the match

Both refusals are RIGHT — ``choose_settled_winner``'s own table is why — and
nothing here loosens them. What moves is that the refusal stops being published
as a settlement.

HOW BIG, MEASURED BY RUNNING THE POLICY AND NOT A SQL PROXY
-----------------------------------------------------------

Production 2026-09-21, over events holding a positive venue grade with no score
past kickoff — every row that reaches this code. The verdict for each event was
produced by calling ``settlement_from_graded_rows`` on that event's own graded
legs:

    kickoff 3–30 days ago   population 1,705   45 sampled   19 said "Settled" and named nothing
    last 30 days, newest    population 2,595   60 sampled   11 said "Settled" and named nothing

The newest slice is lower because some of those still get a late moneyline
grade; the aged window is the one that cannot improve.

WHAT THIS FILE IS NOT
---------------------

🔴 It is not a regression of #7070 or #6381, and it does not weaken them. Those
fixed cards that DENIED a result we held. This is the same field's opposite
failure — claiming one we cannot state — and every row those issues won still
names its winner. :class:`TestANamedResultIsUnchanged` is that promise, and it
is the half of this file that would catch an over-reach.

It DOES reverse #6381's Acceptance 4 ("settled without inventing a result is
sufficient"), which two guards pinned and which now carry a note pointing here.
That acceptance was true for the event page as it stood and was since inherited
by surfaces it was not written for: #6438 removed the hero's fallback on the
strength of the pill carrying a result, and #7070/#7092 put the pill onto
league-rail and events-list cards where it is the entire card. Alex's standing
ruling — settled means settled, heroes show winners and cards show results —
outranks an implementation acceptance inside one issue.
"""

from __future__ import annotations

from app.utils.venue_settlement import (
    NO_VENUE_GRADE,
    settlement_from_graded_rows,
)

# The specimen's own rows, production 2026-09-21. `(market_name,
# market_external_id, outcome_name)` is the shape both readers' queries produce.
SPECIMEN_HOME = "Tijuana de Caliente"
SPECIMEN_AWAY = "Queretaro"
SPECIMEN_TEAM_TOTAL = (
    "Tijuana de Caliente vs Queretaro: Team Total",
    "KXLIGAMXTEAMTOTAL-26SEP11TIJQUE",
    "Queretaro over 0.5 goals",
)
SPECIMEN_SECOND_HALF = (
    "Tijuana de Caliente vs Queretaro: Second Half Winner",
    "KXLIGAMX2H-26SEP11TIJQUE",
    "Tie 2nd Half",
)

# The shapes #6739 measured as ADMITTED, which must keep answering.
NAMED_HOME = "Crawley"
NAMED_AWAY = "Bains"
NAMED_MONEYLINE = (
    "W75 Le Neubourg: Fiona Crawley vs Naiktha Bains",
    None,
    "Fiona Crawley",
)
NAMED_SCORE_MARKET = (
    "Sabalenka vs. Townsend: Correct Score",
    None,
    "Sabalenka wins 2-0",
)


class TestTheSpecimen:
    """The Queretaro hero, from the rows that drew it."""

    def test_the_specimen_publishes_no_settlement(self):
        assert (
            settlement_from_graded_rows(
                [SPECIMEN_TEAM_TOTAL, SPECIMEN_SECOND_HALF],
                SPECIMEN_HOME,
                SPECIMEN_AWAY,
            )
            == NO_VENUE_GRADE
        )

    def test_the_claim_and_the_content_cannot_disagree(self):
        """The invariant stated as itself, over every shape in this file.

        Written as a loop over the cases rather than as one more assertion
        beside them because the defect WAS the two keys being decided
        separately: a reader of this file should be able to see the property
        asserted about the pair, not infer it from four examples.
        """
        cases = [
            [SPECIMEN_TEAM_TOTAL],
            [SPECIMEN_SECOND_HALF],
            [SPECIMEN_TEAM_TOTAL, SPECIMEN_SECOND_HALF],
            [NAMED_MONEYLINE],
            [NAMED_SCORE_MARKET],
            [SPECIMEN_TEAM_TOTAL, NAMED_MONEYLINE],
            [],
        ]
        for graded in cases:
            home = NAMED_HOME if NAMED_MONEYLINE in graded else SPECIMEN_HOME
            away = NAMED_AWAY if NAMED_MONEYLINE in graded else SPECIMEN_AWAY
            served = settlement_from_graded_rows(graded, home, away)
            assert served["venue_settled"] == bool(
                served["venue_settled_result"]
            ), served

    def test_a_derivative_grade_alone_is_not_a_settlement(self):
        """#6381 Acceptance 4's own example, with the verdict reversed.

        A graded `Set 1 Winner` is the shape that outnumbers the moneyline on
        this population. It was already refused as a RESULT; it is now also
        refused as a claim.
        """
        assert (
            settlement_from_graded_rows(
                [("Set 1 Winner: Fiona Crawley vs Naiktha Bains", None, "Fiona Crawley")],
                NAMED_HOME,
                NAMED_AWAY,
            )
            == NO_VENUE_GRADE
        )


class TestANamedResultIsUnchanged:
    """🔴 THE OVER-REACH GUARD. #6739's win must be byte-identical.

    If the new refusal were keyed on anything but "the namers produced
    nothing", these are the rows it would eat.
    """

    def test_the_moneyline_winner_still_publishes(self):
        assert settlement_from_graded_rows(
            [NAMED_MONEYLINE], NAMED_HOME, NAMED_AWAY
        ) == {"venue_settled": True, "venue_settled_result": "Crawley wins"}

    def test_a_full_scope_score_still_publishes(self):
        assert settlement_from_graded_rows(
            [NAMED_SCORE_MARKET], "Sabalenka", "Townsend"
        ) == {"venue_settled": True, "venue_settled_result": "Sabalenka wins 2-0"}

    def test_a_derivative_grade_beside_a_moneyline_does_not_suppress_it(self):
        """The mixed row: the new arm must read the ANSWER, not the legs.

        A predicate keyed on "are all the legs admissible" would refuse this
        and take a real winner off the page — which is #7070 undone.
        """
        assert settlement_from_graded_rows(
            [SPECIMEN_TEAM_TOTAL, NAMED_MONEYLINE], NAMED_HOME, NAMED_AWAY
        ) == {"venue_settled": True, "venue_settled_result": "Crawley wins"}

    def test_the_score_still_outranks_the_winner(self):
        """#6739's ORDER, re-pinned here because this change rewrote the
        expression that carries it. Score first, winner second.
        """
        assert settlement_from_graded_rows(
            [
                ("Crawley vs Bains: Correct Score", None, "Crawley wins 2-0"),
                NAMED_MONEYLINE,
            ],
            NAMED_HOME,
            NAMED_AWAY,
        ) == {"venue_settled": True, "venue_settled_result": "Crawley wins 2-0"}


class TestTheUnchangedEdges:
    def test_no_grade_at_all_is_still_a_stated_false(self):
        """Unmoved: the keys are PRESENT and false, never absent. A failed
        read is the caller's job and still produces neither key.
        """
        served = settlement_from_graded_rows([], SPECIMEN_HOME, SPECIMEN_AWAY)
        assert served == {"venue_settled": False, "venue_settled_result": None}
        assert set(served) == {"venue_settled", "venue_settled_result"}

    def test_the_constant_is_copied_and_not_handed_out(self):
        """Both refusal paths return a fresh dict. A caller mutating one
        served payload must not edit the module constant for every later row.
        """
        first = settlement_from_graded_rows(
            [SPECIMEN_TEAM_TOTAL], SPECIMEN_HOME, SPECIMEN_AWAY
        )
        first["venue_settled"] = "mutated"
        assert NO_VENUE_GRADE == {
            "venue_settled": False,
            "venue_settled_result": None,
        }
        assert settlement_from_graded_rows(
            [SPECIMEN_SECOND_HALF], SPECIMEN_HOME, SPECIMEN_AWAY
        ) == {"venue_settled": False, "venue_settled_result": None}
