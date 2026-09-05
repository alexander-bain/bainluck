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

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.authority_agreement import (
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
    TENNIS_DENOMINATOR_IS,
    DOUBLES,
    SINGLES,
    STATPAL_TENNIS_REACH,
    TENNIS_MEASUREMENT_HORIZON,
    TENNIS_TIGHTEST_GAP,
    build_tennis_agreements,
    pair_tennis_sides,
    split_by_draw,
)

NOW = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)


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
        assert AMBIGUOUS_REFUSAL not in singles["excluded"]
        assert AMBIGUOUS_CANDIDATE_ROWS not in singles["excluded"]

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
        assert AMBIGUOUS_REFUSAL not in singles["excluded"]

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

    def test_a_spare_row_in_the_component_still_refuses_the_whole_component(self):
        """The boundary between CERT-1910's case and CERT-1904's.

        Two fixtures against THREE indistinguishable rows does not resolve
        one-to-one: something is left over and there is nothing to choose on. It
        refuses, as the one-fixture-two-rows case does.
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
        assert singles["excluded"][AMBIGUOUS_CANDIDATE_ROWS] == 3
        assert singles["identity"]["both"] == 0
        assert singles["identity"]["ours_only"] == 0

    def test_a_spare_fixture_refuses_the_component_too(self):
        """The MIRROR of the spare-row case, and a mutation found it missing.

        StatPal has two meetings of one pair; we hold one row that could be
        either. Tolerating a spare fixture pairs ours with whichever kickoff is
        nearest and reports the other as `statpal_only` — asserting WHICH of the
        two we have, which is the one thing this component cannot say.

        The refusal is deliberately SYMMETRIC even though the two spares are not
        equally suspicious: a spare row of ours is most likely our own duplicate,
        while a spare fixture of theirs is most likely a real match we lack. That
        asymmetry is an argument for treating them differently and it rests on a
        claim about which side's duplicate is more common — a judgment no
        measurement here supports. Refusing both is the loud answer; guessing
        either is the silent one.
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
        assert singles["excluded"][AMBIGUOUS_REFUSAL] == 2
        assert singles["identity"]["both"] == 0
        assert singles["identity"]["statpal_only"] == 0, (
            "pairing one and reporting the other as statpal_only asserts which "
            "of the two meetings we hold, which is exactly what is unknown"
        )

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
        assert AMBIGUOUS_REFUSAL not in allowed[SINGLES]["excluded"]
        assert refused[SINGLES]["identity"]["both"] == 0
        assert allowed[SINGLES]["identity"]["both"] == 1

    def test_an_unambiguous_name_is_not_refused(self):
        """The mutation guard for the test above: refusing everything passes it."""
        rows = build_tennis_agreements(
            fixtures=[f("1", "C. Alcaraz", "J. Sinner")],
            rows=[r("11", "Carlos Alcaraz", "Jannik Sinner")],
        )
        assert AMBIGUOUS_REFUSAL not in rows[SINGLES]["excluded"]
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
