"""Tennis's agreement row: split by draw, joined on identity, scored on neither clock.

#2867 / D50. The ship is that tennis gets a daily agreement row at all; these are
the four ways that row could be published and be WRONG, each of which reads as a
healthy number rather than as a failure:

  * one denominator over both draws — a large phantom gap nothing could close;
  * a clock comparison between two placeholder times — manufactured disagreement;
  * an AMBIGUOUS resolution counted as "StatPal has a match we do not";
  * a governing number defaulted in, starting a clock nobody ruled on.

Every test here is named after the invariant, not after the feature, so the band
runs against any later edit to the row builder (`r_guards_are_named_after_the_
invariant_not_the_feature`).
"""

from __future__ import annotations

import itertools
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.authority_agreement import (
    DEFAULT_EXCLUDED_KEYS,
    GATE_PENDING,
    Join,
    GOVERNING_IDENTITY_NUMBERS,
    MEASUREMENT_POPULATIONS,
    SHADOW_STAMPERS,
    Side,
    build_agreement_row,
    ledger_line,
    pair_by_normalized_key,
)
from app.utils.authority_tennis_agreement import (
    AMBIGUOUS_CANDIDATE_ROWS,
    AMBIGUOUS_REFUSAL,
    MAX_ASSIGNMENTS_PER_COMPONENT,
    TENNIS_DENOMINATOR_IS,
    DOUBLES,
    SINGLES,
    STATPAL_TENNIS_REACH,
    TENNIS_MEASUREMENT_HORIZON,
    TENNIS_REFUSAL_NAMES,
    UNSOLVED_COMPONENT_FIXTURES,
    UNSOLVED_COMPONENT_ROWS,
    TENNIS_TIGHTEST_GAP,
    build_tennis_agreements,
    pair_tennis_sides,
    split_by_draw,
)

NOW = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)

#: Everything one draw's row published, counts AND identity. The identity half is
#: not decoration: a mis-assignment that swaps two partners conserves `both`,
#: `statpal_only` and `ours_only` exactly, so a signature made only of counts
#: cannot see it (CERT-1917).
Published = namedtuple(
    "Published",
    "both statpal_only ours_only denominator ambiguous ambiguous_rows "
    "pairs spare_fixtures spare_rows",
)


def f(ref, home, away, start=NOW):
    return Side(ref=ref, home=home, away=away, start=start)


def r(ref, home, away, start=NOW, held_id=None):
    return Side(ref=ref, home=home, away=away, start=start, held_id=held_id)


class TestTheTwoDrawsNeverShareADenominator:
    """Doubles outnumber singles better than 2:1 on a US Open day.

    Under one denominator every doubles fixture StatPal publishes lands in
    `statpal_only`, and the row reports a gap that no amount of matching could
    ever close — spec rule 5's unreachable-by-design, manufactured by the shape
    of the denominator rather than by the data.
    """

    def test_a_doubles_fixture_is_absent_from_the_singles_denominator(self):
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "C. Alcaraz", "J. Sinner"),
                f("2", "Galloway/ Goransson", "Arevalo/ Pavic"),
                f("3", "Bolelli/ Vavassori", "Granollers/ Zeballos"),
            ],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        singles = rows[SINGLES]["identity"]
        assert singles["both"] == 1
        # The two doubles fixtures are not "StatPal has a match we do not".
        assert singles["statpal_only"] == 0
        assert rows[SINGLES]["denominator"] == 1

    def test_our_doubles_rows_are_absent_from_the_singles_denominator(self):
        """The mirror. Splitting only THEIR side leaves ours in the wrong pool.

        Our doubles rows would then be `ours_only` in the singles row — we would
        publish our own doubles inventory as matches StatPal is missing.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[
                r("11", "Carlos Alcaraz", "Jannik Sinner"),
                r("12", "Robert Galloway/ Andre Goransson", "M. Arevalo/ M. Pavic"),
            ],
        )
        assert rows[SINGLES]["identity"]["ours_only"] == 0
        assert rows[SINGLES]["denominator"] == 1
        assert rows[DOUBLES]["denominator"] == 1

    def test_the_doubles_draw_is_measured_rather_than_dropped(self):
        """Refusing to score doubles is not the same as not counting them.

        The linker skips doubles when WRITING a link. If the row skipped them
        too, "does StatPal have our doubles matches?" would have no answer at
        all, and an unanswered question looks identical to a healthy one.
        """
        rows = build_tennis_agreements(
            fixtures=[f("2", "Galloway/ Goransson", "Arevalo/ Pavic")],
            rows=[],
        )
        assert rows[DOUBLES]["denominator"] == 1
        assert rows[DOUBLES]["identity"]["statpal_only"] == 1

    def test_a_doubles_pair_matches_regardless_of_which_partner_is_written_first(self):
        rows = build_tennis_agreements(
            fixtures=[f("2", "Galloway/ Goransson", "Arevalo/ Pavic")],
            rows=[r("12", "Goransson/ Galloway", "Pavic/ Arevalo")],
        )
        assert rows[DOUBLES]["identity"]["both"] == 1

    def test_split_by_draw_puts_every_side_in_exactly_one_pool(self):
        sides = [
            f("1", "C. Alcaraz", "J. Sinner"),
            f("2", "Galloway/ Goransson", "Arevalo/ Pavic"),
        ]
        singles, doubles = split_by_draw(sides)
        assert len(singles) + len(doubles) == len(sides)
        assert set(s.ref for s in singles) & set(s.ref for s in doubles) == set()


class TestTheClockIsNotEvidenceHere:
    """StatPal stamps 15:00 UTC as a session placeholder on unplayed tennis.

    `governs: False` was already true of every schedule bucket and is not
    enough: it says the count does not gate a flip, not that the count is
    manufactured. A published number is read.
    """

    def test_the_schedule_bucket_is_refused_rather_than_counted(self):
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner", start=NOW)],
            # Our midnight-UTC placeholder against their 15:00 one: 15 hours
            # apart, which a scored bucket calls `off_by_hours`.
            rows=[
                r(
                    "11",
                    "Carlos Alcaraz",
                    "Jannik Sinner",
                    start=NOW.replace(hour=0),
                )
            ],
        )
        schedule = rows[SINGLES]["schedule"]
        assert schedule["scored"] is False
        assert "off_by_hours" not in schedule
        assert "wrong_day" not in schedule
        # And the pairing still HAPPENED — the clock is refused as evidence, not
        # as a tiebreak. A refusal that also dropped the match would trade a
        # phantom disagreement for a phantom miss.
        assert rows[SINGLES]["identity"]["both"] == 1

    def test_a_refused_clock_emits_no_schedule_receipts_either(self):
        """The counts are only half of it — the receipts are the other half.

        Found by mutation: suppressing the schedule BLOCK while still walking
        the buckets leaves `receipts.schedule_disagreements` full of
        placeholder-versus-placeholder pairs. The row then says the clock was
        not scored and hands the reader a list of clock disagreements, which is
        the same manufactured number wearing a different key.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner", start=NOW)],
            rows=[
                r(
                    "11",
                    "Carlos Alcaraz",
                    "Jannik Sinner",
                    start=NOW.replace(hour=0),
                )
            ],
        )
        assert rows[SINGLES]["receipts"]["schedule_disagreements"] == []

    def test_a_scored_sport_still_emits_its_schedule_receipts(self):
        """The mutation guard for the test above: emitting none always passes it."""
        row = build_agreement_row(
            sport_key="americanfootball_nfl",
            fixtures=[f("1", "Bears", "Packers", start=NOW)],
            rows=[r("11", "Bears", "Packers", start=NOW.replace(hour=0))],
            normalize=lambda v: (v or "").strip().lower(),
        )
        assert row["receipts"]["schedule_disagreements"] != []

    def test_the_ledger_line_says_not_scored_rather_than_four_zeros(self):
        """`0/0/0/0` is what perfect agreement looks like."""
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        line = ledger_line(rows[SINGLES], day="2026-09-05")
        assert "schedule=NOT-SCORED" in line
        assert "schedule=0/0/0/0" not in line

    def test_a_scored_sport_still_prints_its_four_counts(self):
        """The refusal is opt-in; the team sports must be untouched by it."""
        row = build_agreement_row(
            sport_key="americanfootball_nfl",
            fixtures=[f("1", "Bears", "Packers")],
            rows=[r("11", "Bears", "Packers")],
            normalize=lambda v: (v or "").strip().lower(),
        )
        assert row["schedule"]["scored"] is True
        assert "schedule=1/0/0/0" in ledger_line(row, day="2026-09-05")


class TestAmbiguityIsPublishedNotAbsorbed:
    """Two of our rows for one match is a duplicate, and it is D39/#2693's.

    The two flattering readings are the ones to refuse: counting it as
    `statpal_only` says StatPal has a match we do not when we have two, and
    pairing the nearest kickoff reports the leftover as `ours_only`, which
    prints a duplicate as a disagreement about a match.
    """

    def test_an_ambiguous_name_leaves_the_denominator_under_its_own_name(self):
        rows = build_tennis_agreements(
            # `G. Garcia` is reachable from both of our rows below, which name
            # two different players: `keys_agree` reads a missing given name as
            # UNKNOWN, never as a difference.
            fixtures=[f("1", "G. Garcia", "J. Sinner")],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
            ],
        )
        singles = rows[SINGLES]
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 1
        assert singles["identity"]["statpal_only"] == 0

    def test_the_refusal_receipt_names_both_candidates(self):
        rows = build_tennis_agreements(
            fixtures=[f("1", "G. Garcia", "J. Sinner")],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
            ],
        )
        receipts = rows[SINGLES]["receipts"][AMBIGUOUS_REFUSAL]
        assert len(receipts) == 1
        assert len(receipts[0]["our_candidates"]) == 2
        assert receipts[0]["unresolved_name"] == "G. Garcia"

    def test_the_candidate_rows_leave_the_denominator_too(self):
        """CERT-1904 finding 1, pinned as the exact specimen it was found on.

        Excluding the FIXTURE alone was half a repair and the wrong half. Both of
        our rows stayed in the population, nothing could pair them, and the row
        published `ambiguous_identity=1` beside `ours_only=2`, denominator 2,
        coverage 0% — a duplicate of ours printed as two matches StatPal is
        missing. That is the outcome this module's own docstring says it refuses,
        reached from the side I was not looking at.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "G. Garcia", "J. Sinner")],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
            ],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["ours_only"] == 0
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 2
        assert singles["denominator"] == 0
        # `None`, not 0.0 — there is nothing to divide by, and a coverage of 0%
        # here would be the same lie in a percentage (gotcha #53).
        assert singles["identity"]["ours_covered_pct"] is None

    def test_the_held_out_rows_are_receipted_by_event_id(self):
        """A count with no ids is not actionable for the #2693 work it feeds."""
        rows = build_tennis_agreements(
            fixtures=[f("1", "G. Garcia", "J. Sinner")],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
            ],
        )
        held = rows[SINGLES]["receipts"][AMBIGUOUS_CANDIDATE_ROWS]
        assert {h["event_id"] for h in held} == {"11", "12"}
        assert rows[SINGLES]["receipts"][AMBIGUOUS_REFUSAL][0]["our_event_ids"] == [
            "11",
            "12",
        ]

    def test_a_contested_name_with_a_different_opponent_is_not_ambiguous(self):
        """CERT-1909, and the exact specimen it was found on.

        A name being contested somewhere in the draw is not ambiguity. It is only
        ambiguity when it leaves two COMPLETE matches we cannot choose between.

        `Garcia Garcia–Daniil Medvedev` shares a contested surname with
        `Garcia–Jannik Sinner`, and it cannot be the `G. Garcia–J. Sinner`
        fixture, because the opponent settles it. Judging ambiguity per NAME
        against the whole window held it out anyway, and a real match left the
        denominator: the row read 0 / 0 / 0 where the honest answer is 1 / 1 / 2.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "G. Garcia", "J. Sinner")],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Daniil Medvedev"),
            ],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 1, (
            "the Sinner fixture has exactly one candidate and must pair with it"
        )
        assert singles["identity"]["ours_only"] == 1, (
            "the Medvedev match is genuinely one StatPal does not have — it is a "
            "finding, not an exclusion"
        )
        assert singles["denominator"] == 2
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 0
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 0

    def test_an_ambiguity_does_not_remove_an_unrelated_row(self):
        """The other over-removal direction: a wholly unrelated pairing survives."""
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "G. Garcia", "J. Sinner"),
                f("2", "C. Alcaraz", "N. Djokovic"),
            ],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
                r("13", "Carlos Alcaraz", "Novak Djokovic"),
            ],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 1
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 2
        assert singles["identity"]["ours_only"] == 0

    def test_two_repeat_meetings_resolve_one_to_one_rather_than_refusing(self):
        """CERT-1910, and the exact specimen it was found on.

        The same pair meets twice a week apart. Each fixture has TWO complete
        candidates, so a "two candidates means refuse" rule threw the whole
        component away and published `0/0/0/0` — bypassing the nearest-kickoff
        pairing this module's own docstring says handles repeat meetings.

        Two fixtures and two rows are not an ambiguity. They are a one-to-one
        assignment with a tiebreak already specified for it.
        """
        early, late = NOW, NOW + timedelta(days=7)
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            rows=[
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=early),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=late),
            ],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 2
        assert singles["identity"]["statpal_only"] == 0
        assert singles["identity"]["ours_only"] == 0
        assert singles["denominator"] == 2
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 0

    def test_the_repeat_meetings_pair_by_nearest_start(self):
        """Not just THAT they pair — that they pair with the right one.

        Two pairings and two rows can be fully consumed by pairing them
        crosswise, which would report agreement while joining Monday's match to
        next Monday's row. The count alone cannot see that.
        """
        early, late = NOW, NOW + timedelta(days=7)
        join = pair_tennis_sides(
            [
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            [
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=early),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=late),
            ],
        )
        assert {(fx.ref, row.ref) for fx, row in join.paired} == {("1", "11"), ("2", "12")}

    def test_a_clean_pair_survives_a_tie_beside_it(self):
        """CERT-1913's boundary case: a proven match is not collateral.

        One fixture pairs unambiguously on the exact kickoff; a second is tied
        between two of our rows at the same distance. Refusing the whole
        component discards the match we CAN prove in order to refuse the one we
        cannot — turning a repair for over-publishing into a defect of
        under-publishing.
        """
        early, late = NOW, NOW + timedelta(days=7)
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            rows=[
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=early),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=late),
                r("13", "Carlos Alcaraz", "Jannik Sinner", start=late),
            ],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 1, "the provable pair must survive"
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 1
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 2
        assert singles["identity"]["ours_only"] == 0

    def test_a_spare_fixture_is_an_honest_miss_when_the_clock_distinguishes(self):
        """CERT-1913, and the specimen it was found on.

        StatPal has two meetings of one pair; we hold one row sitting on the
        EARLIER kickoff exactly. That is not indistinguishable — the clock says
        which one we have — so the row pairs and the later fixture is a genuine
        `statpal_only`.

        I refused this case in the previous presentation on the grounds that the
        two spares are not equally suspicious. That was the wrong instinct and
        the contract already said so: the start time chooses WHICH pairing is
        made and never whether one is made. A refusal is a TIE, not a shape.
        """
        early, late = NOW, NOW + timedelta(days=7)
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner", start=early)],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 1
        assert singles["identity"]["statpal_only"] == 1
        assert singles["denominator"] == 2
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 0

    def test_a_genuinely_tied_spare_fixture_still_refuses(self):
        """The other half: when the clock CANNOT distinguish, it is still a tie.

        Both StatPal fixtures sit at the same moment and our single row could be
        either. Nothing breaks it, so nothing is published — the boundary that
        keeps the test above from being an argument for guessing.
        """
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "C. Alcaraz", "J. Sinner", start=NOW),
                f("2", "C. Alcaraz", "J. Sinner", start=NOW),
            ],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner", start=NOW)],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 0
        assert singles["identity"]["statpal_only"] == 0, (
            "pairing one and calling the other statpal_only asserts which of two "
            "simultaneous meetings we hold, which is exactly what is unknown"
        )
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 2

    def test_an_untimed_contest_is_a_tie_because_nothing_can_break_it(self):
        """With no clock there is no tiebreak, and arrival order is not evidence.

        Found by mutation: the untimed arm silently paired the first candidate it
        reached. A fixture StatPal has not timed yet, against two of our rows, is
        the same unknowable choice as two rows at an identical kickoff — the
        absence of a clock cannot be weaker evidence than a tied one.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner", start=None)],
            rows=[
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=None),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=None),
            ],
        )
        singles = rows[SINGLES]
        assert singles["identity"]["both"] == 0
        assert singles["identity"]["ours_only"] == 0
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 2

    def test_an_uncontested_untimed_pair_still_pairs(self):
        """The mutation guard for the test above: refusing all untimed passes it."""
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner", start=None)],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner", start=None)],
        )
        assert rows[SINGLES]["identity"]["both"] == 1
        assert rows[SINGLES]["excluded"][AMBIGUOUS_REFUSAL] == 0

    def test_ambiguity_is_counted_over_matches_not_over_names(self):
        """The invariant behind both regressions, stated once.

        Two rows sharing a contested name refuse ONLY when both agree with the
        fixture on both players. Same contested name, different opponents, two
        different outcomes — that is the discriminator, and a name-level rule
        cannot express it.
        """
        contested_rows = [
            r("11", "Garcia", "Jannik Sinner"),
            r("12", "Garcia Garcia", "Jannik Sinner"),
        ]
        split_rows = [
            r("11", "Garcia", "Jannik Sinner"),
            r("12", "Garcia Garcia", "Daniil Medvedev"),
        ]
        fixtures = [f("1", "G. Garcia", "J. Sinner")]

        refused = build_tennis_agreements(fixtures=fixtures, rows=contested_rows)
        allowed = build_tennis_agreements(fixtures=fixtures, rows=split_rows)

        assert refused[SINGLES]["excluded"][AMBIGUOUS_REFUSAL] == 1
        assert allowed[SINGLES]["excluded"][AMBIGUOUS_REFUSAL] == 0
        assert refused[SINGLES]["identity"]["both"] == 0
        assert allowed[SINGLES]["identity"]["both"] == 1

    def test_an_unambiguous_name_is_not_refused(self):
        """The mutation guard for the test above: refusing everything passes it."""
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        assert rows[SINGLES]["excluded"][AMBIGUOUS_REFUSAL] == 0
        assert rows[SINGLES]["identity"]["both"] == 1


class TestTheJoinIsTheMatchersOwnRelation:
    def test_a_statpal_initial_resolves_against_our_full_name(self):
        """A string-equality join cannot do this, which is why tennis has its own."""
        join = pair_tennis_sides(
            [f("1", "B. Van De Zandschulp", "A. De Minaur")],
            [r("11", "Botic van de Zandschulp", "Alex de Minaur")],
        )
        assert len(join.paired) == 1

    def test_orientation_is_not_a_difference(self):
        """Which player our column stored first is an artifact of ingestion."""
        join = pair_tennis_sides(
            [f("1", "C. Alcaraz", "J. Sinner")],
            [r("11", "Jannik Sinner", "Carlos Alcaraz")],
        )
        assert len(join.paired) == 1

    def test_one_agreeing_player_is_not_half_a_match(self):
        join = pair_tennis_sides(
            [f("1", "C. Alcaraz", "J. Sinner")],
            [r("11", "Carlos Alcaraz", "Novak Djokovic")],
        )
        assert join.paired == []
        assert len(join.statpal_only) == 1
        assert len(join.ours_only) == 1

    def test_a_name_that_is_not_a_player_is_unusable_rather_than_missing(self):
        """Futures titles leaked into the tennis team-name column."""
        join = pair_tennis_sides(
            [f("1", "C. Alcaraz", "J. Sinner")],
            [r("11", "Black Desert Resort (Men's Doubles) Winner", "Field")],
        )
        assert len(join.unusable_rows) == 1
        assert join.ours_only == []


class TestTheDefaultJoinDidNotMove:
    """Three sports have seven-day clocks running on numbers this join produces.

    A refactor that moved one of them by a game would restart three clocks to
    tidy a signature.
    """

    def test_the_default_join_is_still_keyed_and_still_oriented(self):
        join = pair_by_normalized_key(
            [f("1", "Bears", "Packers")],
            # Reversed: for a team sport this is a DIFFERENT fixture (the away
            # leg), and folding the two would pair Week 6 with Week 14.
            [r("11", "Packers", "Bears")],
            lambda v: (v or "").strip().lower(),
        )
        assert join.paired == []
        assert len(join.statpal_only) == 1
        assert len(join.ours_only) == 1

    def test_the_row_builder_uses_the_key_join_when_none_is_given(self):
        row = build_agreement_row(
            sport_key="americanfootball_nfl",
            fixtures=[f("1", "Bears", "Packers")],
            rows=[r("11", "Bears", "Packers")],
            normalize=lambda v: (v or "").strip().lower(),
        )
        assert row["identity"]["both"] == 1
        assert row["excluded"] == {
            "statpal_placeholders": 0,
            "statpal_unusable_names": 0,
            "our_unusable_names": 0,
        }


class TestThePublishedNumberDoesNotDependOnArrivalOrder:
    """CERT-1915. SQL arrival order is not identity evidence.

    The join used to discover equal-distance rivals while it was already
    consuming availability, so a chain like `f1->{r1,r2}, f2->{r2,r3}` published
    one pair under one ordering and none under a permutation. A row whose numbers
    move when the same data arrives in a different order is not a measurement.

    These sweep EVERY permutation rather than checking one alternative ordering:
    a single swap can miss the case, and the invariant is over the whole
    symmetric group, not over one sample of it.

    The signature carries the pairing IDENTITY as well as the counts, because a
    mis-assignment that swaps two partners conserves every total (CERT-1917) and
    a census cannot see it. Which rows were refused and which were called misses
    are in it for the same reason.
    """

    @staticmethod
    def _signature(fixtures, rows):
        singles = build_tennis_agreements(
            fixtures=list(fixtures), rows=list(rows)
        )[SINGLES]
        identity = singles["identity"]
        join = pair_tennis_sides(list(fixtures), list(rows))
        return Published(
            both=identity["both"],
            statpal_only=identity["statpal_only"],
            ours_only=identity["ours_only"],
            denominator=singles["denominator"],
            ambiguous=singles["excluded"].get(AMBIGUOUS_REFUSAL, 0),
            ambiguous_rows=singles["excluded"].get(AMBIGUOUS_CANDIDATE_ROWS, 0),
            # Deliberately NOT sorted here. Sorting in the harness would hide the
            # thing the harness exists to catch: these lists feed capped
            # receipts, so their ORDER decides which examples a reader is shown,
            # and an order that follows the SQL row order is the same defect in
            # the half of the row a human reads.
            pairs=tuple((fx.ref, row.ref) for fx, row in join.paired),
            spare_fixtures=tuple(fx.ref for fx in join.statpal_only),
            spare_rows=tuple(row.ref for row in join.ours_only),
        )

    def _invariant(self, fixtures, rows):
        seen = {
            self._signature(pf, pr)
            for pf in itertools.permutations(fixtures)
            for pr in itertools.permutations(rows)
        }
        assert len(seen) == 1, (
            f"what this row published depends on arrival order: {sorted(seen)}"
        )
        published = seen.pop()
        # A pairing is a one-to-one assignment or it is not a pairing. Asserted
        # here rather than in one test so every case below carries it.
        assert len({fx for fx, _ in published.pairs}) == len(published.pairs)
        assert len({row for _, row in published.pairs}) == len(published.pairs)
        return published

    def test_the_chain_graph_is_order_invariant(self):
        """CERT-1915's exact shape: two fixtures sharing a middle row."""
        alc = lambda ref: f(ref, "C. Alcaraz", "J. Sinner")  # noqa: E731
        ours = lambda ref: r(ref, "Carlos Alcaraz", "Jannik Sinner")  # noqa: E731
        pub = self._invariant(
            [alc("f1"), alc("f2")], [ours("r1"), ours("r2"), ours("r3")]
        )
        # Nothing in the data chooses, so nothing is published — and crucially
        # the SAME nothing under all twelve orderings. Two fixtures CAN be paired
        # here, so this is also the guard on "maximise the pairing" not becoming
        # "publish any maximum pairing": every one of the six is equally good.
        assert (pub.both, pub.statpal_only, pub.ours_only, pub.denominator) == (
            0,
            0,
            0,
            0,
        )
        assert (pub.ambiguous, pub.ambiguous_rows) == (2, 3)
        assert pub.pairs == ()

    def test_a_forced_pair_beside_a_contest_is_order_invariant(self):
        early, late = NOW, NOW + timedelta(days=7)
        pub = self._invariant(
            [
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            [
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=early),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=late),
                r("13", "Carlos Alcaraz", "Jannik Sinner", start=late),
            ],
        )
        assert pub.both == 1 and (pub.ambiguous, pub.ambiguous_rows) == (1, 2)
        # Both maximum pairings contain this edge and differ only in the other
        # one, so it is published and the rest is refused.
        assert pub.pairs == (("1", "11"),)

    def test_the_repeat_meeting_pairing_is_order_invariant(self):
        early, late = NOW, NOW + timedelta(days=7)
        pub = self._invariant(
            [
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            [
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=early),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=late),
            ],
        )
        assert (
            pub.both,
            pub.statpal_only,
            pub.ours_only,
            pub.denominator,
            pub.ambiguous,
        ) == (2, 0, 0, 2, 0)
        assert pub.pairs == (("1", "11"), ("2", "12"))

    def test_a_timed_candidate_outranks_an_untimed_one(self):
        """Which row paired, not how many — the counts cannot see this.

        A fixture with one timed and one untimed candidate must take the timed
        one: a start we can compare is evidence and a missing start is not.
        Found by mutation, because inverting the two produces the SAME
        `both=1, ours_only=1` while joining the fixture to the wrong row. A
        count-shaped assertion is blind to a mis-assignment that conserves
        totals.
        """
        join = pair_tennis_sides(
            [f("1", "C. Alcaraz", "J. Sinner", start=NOW)],
            [
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=NOW),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=None),
            ],
        )
        assert [(fx.ref, row.ref) for fx, row in join.paired] == [("1", "11")]
        assert [row.ref for row in join.ours_only] == ["12"]

    def test_a_resolved_pair_can_force_a_second_one(self):
        """The fixpoint earns its loop, and the inference is real.

        `r11` is provably fixture 1's — it is the unique nearest of a fixture
        that is its own unique nearest. Fixture 2 is equidistant from `r11` and
        `r12`, so it is contested in round one and FORCED in round two: if `r11`
        belongs to fixture 1, fixture 2 must be `r12`.
        """
        early = NOW
        late = NOW + timedelta(days=2)
        pub = self._invariant(
            [
                f("1", "C. Alcaraz", "J. Sinner", start=early),
                f("2", "C. Alcaraz", "J. Sinner", start=late),
            ],
            [
                r("11", "Carlos Alcaraz", "Jannik Sinner", start=early),
                r("12", "Carlos Alcaraz", "Jannik Sinner", start=late + timedelta(days=2)),
            ],
        )
        assert (pub.both, pub.ambiguous) == (2, 0)
        assert pub.pairs == (("1", "11"), ("2", "12"))

    def test_the_receipts_are_order_invariant_too_and_not_only_the_counts(self):
        """A receipt is capped, so its ORDER decides which examples a reader sees.

        The counts beside it were made order-invariant first and that is the
        governing half, but a truncated list whose contents shuffle with the
        SQL row order is the same defect in the half a human actually reads.
        """
        fixtures = [f("f1", "G. Garcia", "J. Sinner")]
        rows = [
            r("11", "Garcia", "Jannik Sinner"),
            r("12", "Garcia Garcia", "Jannik Sinner"),
        ]
        seen = set()
        for permuted in itertools.permutations(rows):
            join = pair_tennis_sides(fixtures, list(permuted))
            seen.add(
                (
                    tuple(
                        tuple(receipt["our_event_ids"])
                        for receipt in join.refusals[AMBIGUOUS_REFUSAL]
                    ),
                    tuple(
                        receipt["event_id"]
                        for receipt in join.refusals[AMBIGUOUS_CANDIDATE_ROWS]
                    ),
                )
            )
        assert seen == {((("11", "12"),), ("11", "12"))}

    def test_a_locally_exact_edge_never_costs_the_graph_a_pairing(self):
        """CERT-1917, and the exact asymmetric graph it was found on.

        Two Garcias are in the draw and one of our rows carries no given name,
        so the candidate graph is genuinely lopsided:

            fA `Garcia`     → our `Caroline Garcia` AND our `Garcia`
            fD `D. Garcia`  → our `Garcia` only  (a `D.` cannot be Caroline)

        `fA` sits on our bare-`Garcia` row's kickoff EXACTLY, so a rule that
        takes the locally nearest edge first takes `fA→Garcia` — and that single
        choice destroys the only full pairing the graph has. `fD` is then left
        with nothing and `Caroline Garcia` with nothing, and the row publishes
        `1/1/1` over a denominator of 3: two manufactured misses, in opposite
        directions, from two matches that both exist.

        The graph has exactly ONE pairing of maximum size and every permutation
        agrees on it, so there is nothing to refuse here. Cardinality is settled
        before the clock is consulted; the clock chooses among pairings of equal
        size and never buys a local minute with a whole match.
        """
        pub = self._invariant(
            [
                f("fA", "Garcia", "J. Sinner", start=NOW),
                f("fD", "D. Garcia", "J. Sinner", start=NOW + timedelta(days=3)),
            ],
            [
                r("rX", "Caroline Garcia", "Jannik Sinner", start=NOW + timedelta(days=5)),
                r("rY", "Garcia", "Jannik Sinner", start=NOW),
            ],
        )
        assert pub.pairs == (("fA", "rX"), ("fD", "rY")), (
            "the unique maximum pairing is the answer; taking the exact-time "
            "edge first publishes fA→rY and strands both fD and rX"
        )
        assert (
            pub.both,
            pub.statpal_only,
            pub.ours_only,
            pub.denominator,
        ) == (2, 0, 0, 2)
        assert (pub.ambiguous, pub.ambiguous_rows) == (0, 0)

    def test_the_clock_still_chooses_between_pairings_of_the_same_size(self):
        """The other half: maximising cardinality is not licence to ignore time.

        The same lopsided graph, with our bare-`Garcia` row moved so that BOTH
        full pairings exist — `fA` can take either row and `fD` the other is
        impossible, so there is still one maximum pairing. This is the guard that
        keeps the test above from passing under "always pair `fA` with whatever
        `fD` cannot have", which is a rule about the graph's shape rather than a
        maximisation.
        """
        join = pair_tennis_sides(
            [
                f("fA", "Garcia", "J. Sinner", start=NOW),
                f("fD", "D. Garcia", "J. Sinner", start=NOW),
            ],
            [
                r("rX", "Caroline Garcia", "Jannik Sinner", start=NOW),
                r("rY", "Garcia", "Jannik Sinner", start=NOW),
            ],
        )
        assert {(fx.ref, row.ref) for fx, row in join.paired} == {
            ("fA", "rX"),
            ("fD", "rY"),
        }

    def test_maximising_the_pairing_never_publishes_a_name_disagreement(self):
        """A bigger pairing may only be built out of edges the matcher allows.

        Two fixtures and two rows, and yet the largest honest pairing is ONE
        edge: our `Garcia–Daniil Medvedev` row agrees with neither fixture,
        because the opponent settles it (CERT-1909). A maximiser reaching for the
        larger number by relaxing the relation would publish agreement about a
        match against the wrong opponent, which is the failure this whole module
        is an argument against — so the second fixture and that row stay honest
        misses in opposite directions.
        """
        join = pair_tennis_sides(
            [
                f("fA", "Garcia", "J. Sinner", start=NOW),
                f("fD", "D. Garcia", "J. Sinner", start=NOW + timedelta(days=3)),
            ],
            [
                r("rY", "Garcia", "Jannik Sinner", start=NOW),
                r("rMed", "Garcia", "Daniil Medvedev", start=NOW),
            ],
        )
        assert [(fx.ref, row.ref) for fx, row in join.paired] == [("fA", "rY")]
        assert [fx.ref for fx in join.statpal_only] == ["fD"]
        assert [row.ref for row in join.ours_only] == ["rMed"]

    def test_a_component_too_large_to_solve_exactly_is_refused_not_guessed(self):
        """The bound is a refusal, and it is stated rather than discovered.

        The published edges are the ones every optimal pairing agrees on, which
        is a question about ALL of them. That search is bounded, and past the
        bound this module says so: the whole component leaves the denominator.
        It never falls back to a walk, because a walk is the arrival-order defect
        of CERT-1915 wearing a budget.

        And it says so under its OWN name. "The data does not choose" and "we did
        not finish asking" leave the denominator the same way and are not the
        same finding — one is about the field, the other is about our bound, and
        only the second is a reason to change this constant.
        """
        fixtures = [f(f"f{i}", "C. Alcaraz", "J. Sinner") for i in range(20)]
        rows = [r(f"r{i}", "Carlos Alcaraz", "Jannik Sinner") for i in range(20)]
        join = pair_tennis_sides(fixtures, rows)
        assert join.paired == []
        assert join.statpal_only == [] and join.ours_only == []
        assert len(join.refusals[UNSOLVED_COMPONENT_FIXTURES]) == 20
        assert len(join.refusals[UNSOLVED_COMPONENT_ROWS]) == 20
        assert AMBIGUOUS_REFUSAL not in join.refusals, (
            "our own bound is not an ambiguity in the draw"
        )
        assert AMBIGUOUS_CANDIDATE_ROWS not in join.refusals

        # And they LEAVE, rather than merely being receipted on the way past.
        # Refusing a row in the receipt while keeping it in the population is
        # CERT-1904's exact defect, reached from the bound instead of the draw.
        # `Join.rows` is the span a StatPal-only fixture's horizon is measured
        # against, so a component we could not solve must not widen the span we
        # claim to have read — a refusal is a refusal whichever reason it has.
        assert join.rows == [] and join.fixtures == []
        singles = build_tennis_agreements(fixtures=fixtures, rows=rows)[SINGLES]
        assert singles["denominator"] == 0
        assert singles["identity"]["ours_only"] == 0
        assert singles["excluded"][UNSOLVED_COMPONENT_ROWS] == 20
        assert singles["excluded"][UNSOLVED_COMPONENT_FIXTURES] == 20

    def test_a_real_tie_is_never_reported_as_our_bound_giving_up(self):
        """The mutation guard for the test above, in the other direction.

        Two of our rows for one fixture is squarely inside the bound and is a
        genuine tie. Reporting it as an unsolved component would blame the field
        on our own search and send a reader to raise a constant that is not the
        problem.
        """
        join = pair_tennis_sides(
            [f("1", "G. Garcia", "J. Sinner")],
            [
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
            ],
        )
        assert len(join.refusals[AMBIGUOUS_REFUSAL]) == 1
        assert UNSOLVED_COMPONENT_FIXTURES not in join.refusals
        assert UNSOLVED_COMPONENT_ROWS not in join.refusals

    def test_the_bound_does_not_refuse_an_ordinary_days_component(self):
        """The mutation guard for the test above: a bound of 1 would pass it.

        Four repeat meetings of one pair against four of our rows is a real
        shape and it must still resolve, so the bound cannot be set below what a
        tennis day actually produces. The bound is asserted by RELATION to the
        shape it has to admit, so lowering the constant reddens this test rather
        than silently converting live matches into refusals.
        """
        assert 5**4 <= MAX_ASSIGNMENTS_PER_COMPONENT, (
            "four fixtures each with four candidates must stay solvable exactly"
        )
        starts = [NOW + timedelta(days=2 * i) for i in range(4)]
        join = pair_tennis_sides(
            [f(f"f{i}", "C. Alcaraz", "J. Sinner", start=s) for i, s in enumerate(starts)],
            [
                r(f"r{i}", "Carlos Alcaraz", "Jannik Sinner", start=s)
                for i, s in enumerate(starts)
            ],
        )
        assert {(fx.ref, row.ref) for fx, row in join.paired} == {
            (f"f{i}", f"r{i}") for i in range(4)
        }


class TestARowDescribesTheJoinItActuallyUsed:
    """CERT-1904 finding 3. A denominator described by the wrong join is a
    measurement with the wrong source attached to it (CERT-1895's lesson)."""

    def test_the_tennis_row_does_not_claim_an_ordered_pair_key(self):
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        described = rows[SINGLES]["denominator_is"]
        assert described == TENNIS_DENOMINATOR_IS
        # Every clause of the default is false here: there is no key, kickoff is
        # not an in-key tiebreak, and orientation is not part of the identity.
        assert "keyed on the normalised (away, home) pair" not in described
        assert "resolve_tennis_name" in described
        assert "either orientation" in described

    def test_the_default_join_still_describes_itself(self):
        row = build_agreement_row(
            sport_key="americanfootball_nfl",
            fixtures=[f("1", "Bears", "Packers")],
            rows=[r("11", "Bears", "Packers")],
            normalize=lambda v: (v or "").strip().lower(),
        )
        assert "keyed on the normalised (away, home) pair" in row["denominator_is"]

    def test_every_join_strategy_describes_its_own_denominator(self):
        """A strategy whose relation differs must not keep the default sentence.

        Named as a sweep rather than as two assertions so a THIRD strategy cannot
        be added with the key join's description still attached — which is
        exactly how tennis shipped for one grading round.
        """
        default = Join(
            fixtures=[], rows=[], paired=[], statpal_only=[], ours_only=[],
            unusable_fixtures=[], unusable_rows=[],
        ).denominator_is
        tennis = pair_tennis_sides([], [])
        assert tennis.denominator_is != default
        assert pair_by_normalized_key([], [], str).denominator_is == default


class TestNeitherDrawStartsAClockItCannotScore:
    def test_both_populations_gate_pending(self):
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        for key in (SINGLES, DOUBLES):
            assert rows[key]["identity"]["governing"]["gate"] == GATE_PENDING

    def test_neither_population_has_a_governing_number(self):
        """The gate above is only PENDING because of this; pin the cause too."""
        for key in (SINGLES, DOUBLES):
            assert not GOVERNING_IDENTITY_NUMBERS.get(key)

    def test_a_perfect_day_still_gates_pending(self):
        """100% must not read as MEETS for a sport nobody ruled on."""
        rows = build_tennis_agreements(
            fixtures=[
                f("1", "C. Alcaraz", "J. Sinner"),
                f("2", "N. Djokovic", "D. Medvedev"),
            ],
            rows=[
                r("11", "Carlos Alcaraz", "Jannik Sinner"),
                r("12", "Novak Djokovic", "Daniil Medvedev"),
            ],
        )
        assert rows[SINGLES]["identity"]["ours_covered_pct"] == 100.0
        assert rows[SINGLES]["identity"]["governing"]["gate"] == GATE_PENDING


class TestAMeasurementPopulationIsNeverASportKey:
    def test_both_tennis_keys_are_declared_as_populations(self):
        assert MEASUREMENT_POPULATIONS == {SINGLES, DOUBLES}
        for key in MEASUREMENT_POPULATIONS:
            assert key in SHADOW_STAMPERS

    def test_no_measurement_population_is_in_the_flip_switch(self):
        from app.config.authority_by_sport import AUTHORITY_BY_SPORT

        assert set(AUTHORITY_BY_SPORT) & MEASUREMENT_POPULATIONS == set()

    @pytest.mark.parametrize("key", sorted(MEASUREMENT_POPULATIONS))
    def test_flip_permitted_refuses_a_population_as_the_wrong_question(self, key):
        from app.config.authority_by_sport import flip_permitted

        permitted, why = flip_permitted(key, [])
        assert permitted is False
        # And it refuses for the RIGHT reason. Falling through to "no shadow
        # stamper" would describe it as a build step and send someone to build
        # one that already exists.
        assert "MEASUREMENT POPULATION" in why

    def test_a_population_refusal_does_not_depend_on_the_ledger(self):
        """Seven perfect banked days must not turn the refusal into a yes."""
        from app.config.authority_by_sport import flip_permitted

        days = [
            {"day": f"2026-09-{d:02d}", "state": "MEETS"} for d in range(1, 15)
        ]
        permitted, _ = flip_permitted(SINGLES, days)
        assert permitted is False


class TestTheSpanIsBoundedByWhatWasMeasured:
    def test_the_horizon_is_wider_than_the_providers_own_reach(self):
        """The surviving half of the team-sport bound (CERT-962's lesson).

        A horizon inside the provider's window lets SQL subtract a row of ours
        past the edge of a rolling schedule before it can be counted as missing.
        """
        assert TENNIS_MEASUREMENT_HORIZON > STATPAL_TENNIS_REACH

    def test_the_team_sport_offseason_ceiling_cannot_be_applied_to_tennis(self):
        """Derived from the measured gap, not from a remembered sentence.

        `MEASUREMENT_HORIZON`'s other bound is "narrower than half the tightest
        offseason gap". Tennis's tightest gap is 5.0 days — the tour is
        continuous — so that rule would cap the horizon at 2.5 days, which is
        narrower than StatPal's own reach. Obeying it would BE the bug, and this
        asserts the arithmetic rather than the conclusion.
        """
        ceiling_if_applied = TENNIS_TIGHTEST_GAP / 2
        assert ceiling_if_applied < STATPAL_TENNIS_REACH
        assert TENNIS_MEASUREMENT_HORIZON > ceiling_if_applied

    def test_the_measured_gap_is_a_tour_gap_and_not_a_season(self):
        """A guard against someone 'correcting' the constant to a team-sport one.

        97 days was measured on team sports. If this constant ever grows to
        anything season-shaped, the reasoning in the module docstring stops
        following and the horizon needs re-deriving rather than re-reading.
        """
        assert TENNIS_TIGHTEST_GAP < timedelta(days=30)


class TestAZeroYieldIsARowAndNotASkip:
    def test_an_empty_read_still_produces_both_rows(self):
        rows = build_tennis_agreements(fixtures=[], rows=[])
        assert set(rows) == {SINGLES, DOUBLES}
        for key in rows:
            assert rows[key]["identity"]["governing"]["gate"] == GATE_PENDING

    def test_an_empty_venue_against_a_nonempty_inventory_is_the_finding(self):
        """CERT-1904 finding 2, at the builder.

        StatPal serving no tennis while WE list matches is the strongest
        `statpal_only` signal the row can make. Banking `rows=[]` on that day
        publishes denominator 0 — "nobody lists anything" — which reads as a
        quiet Monday. The task-level half is
        `test_a_successful_empty_read_still_measures_our_inventory`.
        """
        rows = build_tennis_agreements(
            fixtures=[],
            rows=[
                r("11", "Carlos Alcaraz", "Jannik Sinner"),
                r("12", "Novak Djokovic", "Daniil Medvedev"),
            ],
        )
        singles = rows[SINGLES]
        assert singles["denominator"] == 2
        assert singles["identity"]["ours_only"] == 2
        assert singles["identity"]["ours_covered_pct"] == 0.0

    def test_a_failed_read_is_not_a_disagreement(self):
        rows = build_tennis_agreements(
            fixtures=[], rows=[], read_failures=["daily/d1: 500"]
        )
        for key in rows:
            assert rows[key]["read"] == "READ-FAILED"
            assert "identity" not in rows[key]


class TestARefusalNameReadsAsMeasuredWhetherOrNotItFired:
    """#3275. One census, one convention.

    `excluded` published its three default keys at `0` always, and a strategy's
    refusal names only when non-zero — so a default key at zero said *measured,
    none* and a strategy key at zero said nothing at all, in the same dict.

    That difference has teeth for `MAX_ASSIGNMENTS_PER_COMPONENT`, whose
    docstring says in as many words that **zero is the expected reading**: the
    bound exists to be raised when it bites. An operator watching for that could
    not tell *it did not bite today* from *it can no longer be reported* — a
    renamed key, a regressed refusal path, a strategy swapped out. Both looked
    identical, because the key was simply not there. It is the same "not
    measured" vs "measured and disagreed" distinction the row gets right one
    level up, where `agreement: null` carries a note saying which one it is.

    Each of the four names is separately shown NON-zero by the specimens above
    (`AMBIGUOUS_REFUSAL`, `AMBIGUOUS_CANDIDATE_ROWS`, and both
    `UNSOLVED_COMPONENT_*` under the oversized component), so a seeded `0` here
    is a reading and not a constant.
    """

    def test_a_strategy_refusal_name_publishes_zero_when_nothing_was_refused(self):
        """The failing test #3275 names. Before the fix this is a `KeyError`."""
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        singles = rows[SINGLES]
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 0
        assert singles["excluded"][UNSOLVED_COMPONENT_FIXTURES] == 0
        assert singles["excluded"][UNSOLVED_COMPONENT_ROWS] == 0
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 0

    def test_both_draws_publish_the_vocabulary_even_with_nothing_to_refuse(self):
        """The doubles row has no fixtures at all and still answers the question.

        A draw the pass barely touched is exactly where an absent key would be
        easiest to mistake for a quiet day.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        for key in (SINGLES, DOUBLES):
            for name in TENNIS_REFUSAL_NAMES:
                assert rows[key]["excluded"][name] == 0, (
                    f"{key} left {name} out of its census entirely"
                )

    def test_a_seeded_zero_still_rises_when_that_refusal_actually_fires(self):
        """The pairing the issue requires: the seed must not BE the answer.

        Satisfying the test above with a constant `0` would publish a number
        that can never move — the monitorability hole, one layer deeper. So the
        same two names are driven off zero by a real ambiguity while the two
        names that did NOT fire stay at a measured zero.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "G. Garcia", "J. Sinner")],
            rows=[
                r("11", "Garcia", "Jannik Sinner"),
                r("12", "Garcia Garcia", "Jannik Sinner"),
            ],
        )
        singles = rows[SINGLES]
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 1
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 2
        # Not seeded over: these two genuinely did not fire on this pass.
        assert singles["excluded"][UNSOLVED_COMPONENT_FIXTURES] == 0
        assert singles["excluded"][UNSOLVED_COMPONENT_ROWS] == 0

    def test_the_receipts_block_is_keyed_by_the_same_vocabulary(self):
        """`excluded` and `receipts` may not disagree about which names exist.

        Every other receipt key publishes an empty list when it has nothing to
        show; a refusal's receipt going absent instead would reintroduce the bug
        one field over, and an operator cross-reading the two blocks would find
        a count with no place to look.
        """
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        singles = rows[SINGLES]
        for name in TENNIS_REFUSAL_NAMES:
            assert singles["receipts"][name] == []

    def test_the_default_join_publishes_no_refusal_it_cannot_make(self):
        """The seeding is the STRATEGY's vocabulary, not a new shared default.

        NFL, NBA and NHL have seven-day clocks running on rows from the key
        join. Leaking tennis's four names into their census at `0` would invent
        four permanent readings about a refusal those sports have no code to
        make.
        """
        row = build_agreement_row(
            sport_key="americanfootball_nfl",
            fixtures=[f("1", "Bears", "Packers")],
            rows=[r("11", "Bears", "Packers")],
            normalize=lambda v: (v or "").strip().lower(),
        )
        assert set(row["excluded"]) == set(DEFAULT_EXCLUDED_KEYS)

    def test_a_join_emitting_a_refusal_name_it_never_declared_is_refused(self):
        """The wrong half of the vocabulary drifting is worse than the old bug.

        A typo'd or renamed emit would publish the real count under a name
        nothing watches, while the declared name sat at a seeded `0` — absent
        reads as unknown, but a wrong `0` reads as measured.
        """
        with pytest.raises(ValueError, match="did not declare"):
            Join(
                fixtures=[],
                rows=[],
                paired=[],
                statpal_only=[],
                ours_only=[],
                unusable_fixtures=[],
                unusable_rows=[],
                refusals={"unsolved_componant": [{"ref": "1"}]},
                refusal_names=(UNSOLVED_COMPONENT_FIXTURES,),
            )

    def test_a_refusal_name_colliding_with_a_default_excluded_key_is_refused(self):
        """The seed is merged into the same dict the defaults are counted into.

        A strategy declaring `our_unusable_names` would zero a count the row had
        already measured — an exclusion silently moving the denominator, which
        is the one thing `excluded` exists to prevent.
        """
        with pytest.raises(ValueError, match="collide"):
            Join(
                fixtures=[],
                rows=[],
                paired=[],
                statpal_only=[],
                ours_only=[],
                unusable_fixtures=[],
                unusable_rows=[],
                refusal_names=("our_unusable_names",),
            )
