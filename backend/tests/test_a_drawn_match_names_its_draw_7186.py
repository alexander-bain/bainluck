"""#7186 — a drawn match stops printing "No result reported" over the venue's own Draw.

THE DEFECT, READ OFF THE SERVED PAYLOAD 2026-09-22 ~03:1xZ.
``/api/events/15307278`` (CD Tolima v América de Cali, kicked off 2026-09-20
23:10Z) serves::

    status                   "suspended"
    home_score / away_score  null / null
    venue_settled            false
    venue_settled_result     null

so ``eventState.hasNoReportedResult`` is true and the page prints **"No result
reported"**. One join away, on that same event, Polymarket's own three-way
moneyline carries::

    market   CD Tolima vs. América de Cali          status  resolved
    outcome  Draw (CD Tolima vs. América de Cali)   is_winner  true

The venue said the most definite thing it can say about a football match, and
we told the reader nothing.

TWO CORRECT REFUSALS COMPOSING INTO A WRONG PAGE
------------------------------------------------

Neither half of :func:`choose_settled_winner` is buggy on its own:

1. :data:`DRAW_OUTCOME_NAMES` is normalised-exact — ``{"tie", "draw"}`` — and
   deliberately so (a substring test would adopt ``Tie 1st Half``). It does not
   hold ``draw (cd tolima vs. américa de cali)``.
2. The name then falls through to :func:`_names_a_participant`, where the
   parenthetical trips :data:`_OUTCOME_IS_A_MATCHUP_RE` — #4629's guard against
   a full-matchup outcome name being read as its first-named side.

Each refusal is right about the question it was asked. The composition is a
third draw spelling that nothing in the module holds.

THE POPULATION, AND THE BASIS IT HAS TO BE MEASURED ON
-------------------------------------------------------

🔴 THE FIRST MEASUREMENT OF THIS SHIP WAS TAKEN ON THE WRONG LEG SET AND READ
16× TOO BIG. It selected ``fo.is_winner IS TRUE AND fm.status = 'resolved'`` —
the shape the PRODUCER side of #2591 uses. Both readers here select
:func:`~app.utils.venue_settlement_reader.venue_grade_filters`, which is
``fo.is_winner IS TRUE AND fo.resolution_source = 'api_settlement'`` and says
nothing about market status. Those are different sets, and on this population
they disagree enormously: **68 of the 77** ``Draw (<matchup>)`` legs carry
``resolution_source = 'clean_resolution'``, which no reader can see. Sized on
the producer's filter the ship reads 47 events; sized on the filter the page
actually uses it is **3**. A reach claim must be measured on the query the
CONSUMER runs.

Production ``db-query`` 2026-09-22, the readers' own filter: every positive
``api_settlement`` grade on the scoreless ``suspended`` events with a kickoff
inside 7 days — **1,784 events / 8,003 legs**, paged on an id cursor because the
endpoint truncates at 1,000 and a page cut mid-event drops legs in the direction
that makes the namer look MORE certain, not less. Every draw-ish graded outcome
in that set:

    ====================================  =====  ==========================
    graded outcome                        legs   verdict
    ====================================  =====  ==========================
    bare ``Draw`` / ``Tie``, moneyline      83   already admitted
    bare ``Draw`` / ``Tie``, derivative     19   refused — not full-scope
    ``Tie 1st Half``                        10   refused — not full-scope
    ``Draw (<matchup>)``                     9   THIS FILE
    ``Reg Time: Tie``                        5   refused — see below
    ``Decision / Draw / No Contest``         1   refused — not full-scope
    ====================================  =====  ==========================

All 9 sit on a ``moneyline``-classified market, **0** carry a parenthetical that
is not the matchup, and all 9 name their own event's two sides.

Replaying the shipped policy over all 1,784 events, before and after, in one run
(``artifacts-live-498/before_after_routefilter.py`` — BEFORE recomputed by
reverting the predicate rather than remembered, so a churned population cannot
be read as a gain):

    named BEFORE  1,482   named AFTER  1,485
    GAINED 3 · LOST 0 · result CHANGED 0

**3 events, not 9**, and the gap is not a refusal: the other six are already
answered by :func:`choose_settled_score`, which the policy evaluates FIRST and
short-circuits through ``or``. Their richer score sentence is untouched, which
is what ``CHANGED 0`` records.

WHY THE OTHER 68 MUST NOT BE PUBLISHED
---------------------------------------

``clean_resolution`` is **price-derived** — ``backfill_winners`` writes
``is_winner = (fo.current_probability >= 0.95)``. It is our inference from the
market's own price, not the venue's statement, which is why
``CALIBRATION_TRUTH_ELIGIBLE_SOURCES`` fails it closed and why
:data:`VENUE_SETTLEMENT_SOURCE` is one value rather than a list. #7186's own body
puts it as a trap: *"Do not settle from the win-probability curve. A curve
reaching 100% is a model output; reading a winner off it invents settlement from
a probability."* So the 68 are a population this module is correctly blind to,
and widening the source to reach them is a different decision with a different
warrant — not this ship.

WHAT STAYS REFUSED, AND WHY EACH ONE IS A CHOICE
-------------------------------------------------

``Reg Time: Tie`` (5 legs) is a statement about ninety minutes, not about the
match — the same fixture can be graded ``Reg Time: Tie`` and still have a winner
after extra time or penalties. ``Tie 1st Half`` and every ``- Halftime Result``
/ ``- Second Half Result`` draw are refused by the market-class test that
already existed. `TestTheDrawsThatAreNotTheMatch` is that list with its real
names on it, because a widening is only trustworthy beside the near-misses it
did not take.
"""

import pytest

from app.utils.venue_settlement import (
    _names_a_draw,
    choose_settled_winner,
    settlement_from_graded_rows,
)

#: The photographed specimen.
HOME = "CD Tolima"
AWAY = "América de Cali"
MONEYLINE = "CD Tolima vs. América de Cali"
VENUE_DRAW = "Draw (CD Tolima vs. América de Cali)"

#: Measured on production 2026-09-22 over the 7-day scoreless-`suspended` arm,
#: on the READERS' filter (`venue_grade_filters`), not the producer's.
MEASURED = {
    "events_in_population": 1784,
    "graded_legs": 8003,
    "named_before": 1482,
    "named_after": 1485,
    "events_gained": 3,
    "events_lost": 0,
    "results_changed": 0,
    "draw_with_matchup_legs": 9,
    "draw_with_matchup_legs_on_a_moneyline": 9,
    "parentheticals_that_are_not_a_matchup": 0,
    "reg_time_tie_legs_left_refused": 5,
    # The six that carry the shape and gain nothing: already answered by the
    # score path, which runs first. Gained + these == the legs.
    "draw_legs_already_answered_by_the_score_path": 6,
    # The same shape on a source no reader can see (price-derived).
    "draw_with_matchup_legs_stamped_clean_resolution": 68,
}


def _row(market_name, outcome_name, external_id=None):
    """One graded row in the shape the route hands the chooser."""
    return (market_name, external_id, outcome_name)


class TestTheSpecimen:
    """The served payload, end to end through the pure half."""

    def test_the_venues_parenthesised_draw_is_the_match_result(self):
        assert choose_settled_winner([_row(MONEYLINE, VENUE_DRAW)], HOME, AWAY) == "Draw"

    def test_the_page_receives_a_co_true_pair(self):
        """Through the one function both readers call, so a rail and the detail
        page cannot answer this row differently (#6739's second half)."""
        assert settlement_from_graded_rows(
            [_row(MONEYLINE, VENUE_DRAW)], HOME, AWAY
        ) == {"venue_settled": True, "venue_settled_result": "Draw"}

    def test_before_the_fix_this_row_published_nothing(self):
        """The defect, spelled as the thing that used to happen: neither namer
        could read this string, so the pair was the no-grade pair."""
        assert not _names_a_draw(VENUE_DRAW, None, None)

    @pytest.mark.parametrize(
        "outcome",
        [
            "Draw (PS Kalamáta vs. AE Lárisas 1964)",
            "Draw (Johor Darul Ta'zim vs. Buriram United)",
            "Draw (FC Arda Kardzhali vs. PFC Cherno More Varna)",
            "Draw (San Martin de San Juan vs. CSD Tristan Suarez)",
        ],
    )
    def test_four_more_real_rows_from_the_measured_population(self, outcome):
        home, away = outcome[len("Draw ("):-1].split(" vs. ")
        assert choose_settled_winner([_row(f"{home} vs. {away}", outcome)], home, away) == "Draw"


class TestTheIdentityCheck:
    """The parenthetical says which fixture the verdict is about. We read it."""

    def test_a_draw_from_another_fixture_is_refused(self):
        """🔴 THE ARM THAT CONVICTS THE GUARD. Inert on today's data — 77 of 77
        parentheticals name their own event's two sides — so without this arm
        the both-sides test could be deleted and every other test in this file
        would stay green. The shape it refuses is a draw verdict landing on a
        mis-linked market, which is the standing twin/ghost-attachment class
        (#7186, #2693), not a hypothetical."""
        assert (
            choose_settled_winner(
                [_row(MONEYLINE, "Draw (Grazer AK 1902 vs. FK Austria Wien)")],
                HOME,
                AWAY,
            )
            is None
        )

    def test_one_side_matching_is_not_enough(self):
        """A derby: the parenthetical names our home side and somebody else."""
        assert not _names_a_draw("Draw (CD Tolima vs. Atlético Nacional)", HOME, AWAY)

    def test_our_spelling_may_differ_from_the_venues(self):
        """The one row in 77 whose spellings disagree. ``events`` stores
        ``Varazdin``/``Osijek``; Polymarket writes ``NK Varaždin vs. NK
        Osijek``. Admitted because the test is ``_fuzzy_team_match`` — the same
        primitive ``_names_a_participant`` orients with (#1951) — and not a
        second containment rule written for this arm. An equality test here
        costs a real drawn match."""
        assert _names_a_draw("Draw (NK Varaždin vs. NK Osijek)", "Varazdin", "Osijek")

    def test_a_row_missing_a_side_name_cannot_be_checked_and_is_refused(self):
        """Inherited from the primitive, not from a guard written here:
        ``_fuzzy_team_match`` answers False for a blank side, so the AND fails
        on its own. Pinned anyway — if the primitive ever starts admitting a
        blank, a row with one team name would acquire a draw, and this is the
        arm that would say so."""
        assert not _names_a_draw(VENUE_DRAW, HOME, None)
        assert not _names_a_draw(VENUE_DRAW, "", AWAY)
        assert not _names_a_draw(VENUE_DRAW, None, None)


class TestTheDrawsThatAreNotTheMatch:
    """Every draw-ish grade in the measured population this fix does NOT take."""

    def test_regulation_time_tie_is_not_the_match_result(self):
        """5 legs. A tie after ninety minutes is not a drawn match — the same
        fixture can go to extra time and have a winner. Refused, and named here
        so the omission reads as chosen rather than missed."""
        assert choose_settled_winner([_row(MONEYLINE, "Reg Time: Tie")], HOME, AWAY) is None

    @pytest.mark.parametrize(
        "outcome",
        [
            "Reg Time: Tie (CD Tolima vs. América de Cali)",
            "Tie 1st Half (CD Tolima vs. América de Cali)",
            "2nd Half Draw (CD Tolima vs. América de Cali)",
        ],
    )
    def test_a_qualified_draw_carrying_the_matchup_is_still_refused(self, outcome):
        """🔴 THE ARM THAT MAKES THE LEADING ANCHOR LOAD-BEARING. The pattern
        starts at ``^`` so the verdict word must be the WHOLE name before the
        parenthetical. Without the anchor these three read as match draws while
        every other test in this file stays green — the qualifier is the entire
        difference between "the match was drawn" and "the first half was", and
        the parenthetical makes them pass the identity check that would
        otherwise be the backstop. No specimen carries this shape today; the
        anchor is what keeps it that way when the venue adds one."""
        assert not _names_a_draw(outcome, HOME, AWAY)
        assert choose_settled_winner([_row(MONEYLINE, outcome)], HOME, AWAY) is None

    def test_a_halftime_result_draw_is_still_refused(self):
        """Live rows: ``/events/15310931`` grades a bare ``Draw`` on
        ``AE Kifisiás vs. Panathinaikós AO - Halftime Result``. The market-class
        test refuses it and this widening does not reach past that."""
        assert (
            choose_settled_winner(
                [_row("AE Kifisiás vs. Panathinaikós AO - Halftime Result", "Draw")],
                "AE Kifisiás",
                "Panathinaikós AO",
            )
            is None
        )

    def test_a_second_half_result_draw_is_still_refused(self):
        assert (
            choose_settled_winner(
                [_row("Union Espanola vs. Deportes Temuco - Second Half Result", "Draw")],
                "Union Espanola",
                "Deportes Temuco",
            )
            is None
        )

    @pytest.mark.parametrize("outcome", ["Tie 1st Half", "Decision / Draw / No Contest"])
    def test_the_remaining_drawish_vocabulary_is_not_a_draw(self, outcome):
        assert not _names_a_draw(outcome, HOME, AWAY)

    def test_a_truncation_that_ate_a_team_name_is_refused(self):
        """Polymarket cuts outcome names at 60 characters. Here the cut lands
        inside the away side, so the identity check is what refuses it — the
        closing-parenthesis anchor and the both-sides test would each have done
        it alone."""
        assert not _names_a_draw("Draw (CD Tolima vs. América de Ca", HOME, AWAY)

    def test_a_truncation_that_ate_ONLY_the_parenthesis_is_refused(self):
        """🔴 THE ARM THAT MAKES THE CLOSING PARENTHESIS LOAD-BEARING, and the
        one the first draft of this file was missing. Both sides are still
        readable here, so the identity check PASSES and the anchor is the only
        thing left refusing. Relaxing ``\\)`` to ``\\)?`` admits this string
        while every other test in the file stays green — which is how the
        original truncation trap (:data:`_OUTCOME_IS_A_MATCHUP_RE`) got in.

        Refusing is the conservative reading and it is the one this module
        already takes elsewhere: a name we can see was cut is a name whose
        unseen tail we cannot vouch for, and the tail is where a qualifier
        would live."""
        assert not _names_a_draw("Draw (CD Tolima vs. América de Cali", HOME, AWAY)
        # Same string, one character longer: the only difference is the paren.
        assert _names_a_draw("Draw (CD Tolima vs. América de Cali)", HOME, AWAY)

    def test_a_participant_whose_name_merely_contains_draw_is_not_a_draw(self):
        assert not _names_a_draw("Drawbridge United", "Drawbridge United", AWAY)


class TestNothingThatWorkedStoppedWorking:
    """LOST 0 / CHANGED 0, as assertions rather than as a summary line."""

    @pytest.mark.parametrize("venue_word", ["Tie", "Draw", "  tie ", "DRAW"])
    def test_the_bare_spellings_and_their_casing_are_unchanged(self, venue_word):
        assert (
            choose_settled_winner(
                [_row("Sturm Graz vs Stade Rennais", venue_word)],
                "Sturm Graz",
                "Stade Rennais",
            )
            == "Draw"
        )

    def test_the_winner_path_is_untouched(self):
        assert (
            choose_settled_winner(
                [_row("W75 Le Neubourg: Fiona Crawley vs Naiktha Bains", "Fiona Crawley")],
                "Crawley",
                "Bains",
            )
            == "Crawley wins"
        )

    def test_a_parenthesised_draw_and_a_named_side_still_refuse_each_other(self):
        """The third verdict competes in the same disagreement test the other
        two do: on a three-way moneyline "the venue graded Draw" and "the venue
        graded CD Tolima" are contradictory claims about one match, and the set
        holds SENTENCES so they collide rather than being published side by
        side."""
        assert (
            choose_settled_winner(
                [_row(MONEYLINE, VENUE_DRAW), _row(MONEYLINE, "CD Tolima")], HOME, AWAY
            )
            is None
        )

    def test_the_same_draw_spelled_both_ways_is_still_one_answer(self):
        assert (
            choose_settled_winner(
                [_row(MONEYLINE, VENUE_DRAW), _row(MONEYLINE, "Draw")], HOME, AWAY
            )
            == "Draw"
        )

    def test_an_event_with_only_derivative_grades_still_publishes_nothing(self):
        assert settlement_from_graded_rows(
            [_row("CD Tolima vs. América de Cali: O/U 2.5", "Over")], HOME, AWAY
        ) == {"venue_settled": False, "venue_settled_result": None}


class TestTheMeasurementIsOnTheRecord:
    """The numbers the ship is sized on, so a later reader can re-run them."""

    def test_the_population_adds_up(self):
        m = MEASURED
        assert m["named_before"] + m["events_gained"] == m["named_after"]
        assert m["events_lost"] == 0 and m["results_changed"] == 0
        assert m["named_after"] <= m["events_in_population"]

    def test_every_parenthesised_draw_was_on_a_moneyline(self):
        m = MEASURED
        assert m["draw_with_matchup_legs_on_a_moneyline"] == m["draw_with_matchup_legs"]
        assert m["parentheticals_that_are_not_a_matchup"] == 0

    def test_the_legs_this_shape_carries_are_fully_accounted_for(self):
        """Gained + already-answered == the legs. A shape that 'should have'
        gained and did not is the reading this arithmetic refuses to hide."""
        m = MEASURED
        assert (
            m["events_gained"] + m["draw_legs_already_answered_by_the_score_path"]
            == m["draw_with_matchup_legs"]
        )

    def test_the_reach_was_sized_on_the_readers_filter_not_the_producers(self):
        """🔴 The correction this file exists downstream of. Sized on
        ``fm.status='resolved'`` the ship reads 47 events; sized on the readers'
        ``resolution_source='api_settlement'`` it reads 3, because 68 of the 77
        legs carrying this shape are price-derived and no reader can see them.
        Pinned as arithmetic so the smaller number cannot quietly drift back."""
        m = MEASURED
        assert m["draw_with_matchup_legs_stamped_clean_resolution"] == 68
        assert (
            m["draw_with_matchup_legs"]
            + m["draw_with_matchup_legs_stamped_clean_resolution"]
            == 77
        )
