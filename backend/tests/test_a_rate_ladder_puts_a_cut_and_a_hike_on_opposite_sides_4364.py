"""#4364 — a rate ladder's axis is SIGNED, and a cut is not a hike.

Served on production page one 2026-09-09 (`33d3a00e`), two cards — "South
African Reserve Bank rate decision in September" and "Bank of Japan rate
decision in December" — drew a `threshold_heatmap` with exactly two rungs:

    Hike more than 25bps   ->  25.0
    Cut more than 25bps    ->  25.0

A rate CUT and a rate HIKE at one identical coordinate, and the three middle
outcomes ("Hike 25bps", "Cut 25bps", "No change") absent from the ladder
entirely, because none of them was threshold-SHAPED. So the reader was shown
the two LEAST likely outcomes, stacked on one bar, with the modal outcome — a
62% hold — nowhere on the card.

Two independent causes, both fixed here:

  1. the direction word was read for its COMPARATOR ("more than") and never for
     its SIGN, so nothing knew "Cut" belongs below zero;
  2. `25bps` is not `25 bps`: with the unit glued to the number there is no word
     boundary after the 5, so `\\bbps\\b` refused the label and it scored nothing.

The class guard is the assertion `test_no_ladder_puts_a_rise_and_a_fall_at_one
_value`, and it is deliberately NOT "no ladder may serve two rungs at the same
value" — #4226 measured that blanket rule false against 277 production band
ladders and shipped `test_two_rungs_at_one_value_is_NOT_the_guard_for_this_class`
to stop anyone adopting it. The distinction is the cause, not the count: a band
ladder collides at a bucket boundary and stays monotone either side; this
collided because a sign was lost and the colliding labels are opposites.
"""

from app.utils.discover_card_archetypes import (
    _LADDER_FALL_RE,
    _LADDER_RISE_RE,
    _outcome_threshold_value,
    _threshold_points,
)

# The SARB card as production served it, probabilities included so the modal
# outcome is visible in the assertions rather than implied.
SARB_OUTCOMES = [
    ("Hike more than 25bps", 0.02),
    ("Hike 25bps", 0.08),
    ("No change", 0.62),
    ("Cut 25bps", 0.24),
    ("Cut more than 25bps", 0.04),
]


def _ladder(name, outcomes):
    return _threshold_points(
        name=name,
        outcomes=[{"name": n, "probability": p} for n, p in outcomes],
        outcome_count=len(outcomes),
    )


def _by_label(points):
    return {p["label"]: p["value"] for p in points}


def test_a_cut_and_a_hike_of_the_same_size_are_not_the_same_rung():
    # The whole reader-visible defect, in one assertion.
    points = _ladder("South African Reserve Bank rate decision in September", SARB_OUTCOMES)
    values = _by_label(points)

    assert values["Cut more than 25bps"] != values["Hike more than 25bps"]
    assert values["Cut more than 25bps"] < 0 < values["Hike more than 25bps"]
    assert values["Cut 25bps"] < 0 < values["Hike 25bps"]


def test_the_modal_outcome_is_on_the_ladder_at_zero():
    # BEFORE: a 62% hold had no rung at all — "No change" carries no number, so
    # it was never threshold-shaped. On a signed axis it is the interior rung.
    points = _ladder("South African Reserve Bank rate decision in September", SARB_OUTCOMES)

    assert _by_label(points)["No change"] == 0.0
    modal = max(points, key=lambda p: p["probability"])
    assert modal["label"] == "No change"


def test_every_outcome_earns_a_rung_and_the_ladder_reads_in_order():
    # BEFORE: 2 rungs of 5. The order is asserted as LABELS, not just values,
    # because two rungs legitimately share a value here (the open-ended buckets)
    # and a value-only assertion could not tell a correct ladder from a shuffled
    # one.
    points = _ladder("Bank of Japan rate decision in December", SARB_OUTCOMES)

    assert len(points) == len(SARB_OUTCOMES), "every outcome is a rung"
    assert [p["label"] for p in points] == [
        "Cut more than 25bps",
        "Cut 25bps",
        "No change",
        "Hike 25bps",
        "Hike more than 25bps",
    ]
    assert [p["value"] for p in points] == [-25.0, -25.0, 0.0, 25.0, 25.0]


def test_the_reading_order_does_not_depend_on_the_order_the_venue_listed_them():
    # The two open-ended buckets tie with their neighbours on value, so before
    # the direction tie-break the venue's arrival order decided what the reader
    # saw. Same five outcomes, reversed: the ladder must be identical.
    forward = _ladder("BoJ rate decision", SARB_OUTCOMES)
    reversed_ = _ladder("BoJ rate decision", list(reversed(SARB_OUTCOMES)))

    assert [p["label"] for p in forward] == [p["label"] for p in reversed_]


def test_no_ladder_puts_a_rise_and_a_fall_at_one_value():
    # THE CLASS GUARD (#4364 sketch item 3). Not "no two rungs at one value" —
    # #4226 measured that false on 277 band ladders. Opposite DIRECTION WORDS at
    # one value is the shape that can only mean a lost sign.
    ladders = [
        ("SARB September", SARB_OUTCOMES),
        ("BoJ December", list(reversed(SARB_OUTCOMES))),
        (
            "Fed rate decision in November",
            [("Cut 50bps", 0.05), ("Cut 25bps", 0.55), ("No change", 0.3), ("Hike 25bps", 0.1)],
        ),
        (
            "ECB deposit rate in October",
            [
                ("Lower more than 25bps", 0.03),
                ("Lower 25bps", 0.2),
                ("Unchanged", 0.7),
                ("Raise 25bps", 0.07),
            ],
        ),
    ]
    for name, outcomes in ladders:
        points = _ladder(name, outcomes)
        by_value = {}
        for point in points:
            by_value.setdefault(point["value"], []).append(point["label"])
        for value, labels in by_value.items():
            rises = [x for x in labels if _LADDER_RISE_RE.search(x)]
            falls = [x for x in labels if _LADDER_FALL_RE.search(x)]
            assert not (rises and falls), (
                f"{name}: {rises} and {falls} both drawn at {value}"
            )


def test_a_glued_unit_is_still_a_unit():
    # "25bps" has no word boundary after the 5. Both halves of the parse failed
    # on it: the shape test refused the label, and the value parser's trailing
    # `\b` refused the number.
    assert _outcome_threshold_value("Hike 25bps") == (25.0, "", "exact")
    assert _outcome_threshold_value("Cut 50bps") == (50.0, "", "exact")
    # The spaced form was always fine and must stay fine.
    assert _outcome_threshold_value("Hike 25 bps")[0] == 25.0


def test_an_ordinal_against_a_digit_is_not_a_glued_unit():
    # The near-miss on this fix, and the reason the bound admits a bps unit
    # rather than relaxing to "the number ended". Measured over 12,077
    # production outcome labels, the general relaxation moved 3,477 of them:
    # a digit against a letter is far more often an ORDINAL than a unit, so
    # every quarter/half prop in the book started scoring its PERIOD NUMBER
    # instead of its line. Same class as #4226 ("Claude Opus 4-7") and #3567
    # ("SF 49ers"): a number inside a name.
    assert _outcome_threshold_value("ARI Cardinals wins 2Q by over 7.5 points") == (
        7.5,
        "",
        "exact",
    )
    assert _outcome_threshold_value("AC Goianiense wins the 1H by more than 1.5 goals") == (
        1.5,
        "",
        "exact",
    )
    # A gamer tag acquired a rung at 3 under the same relaxation.
    assert _outcome_threshold_value("Bimbo + Rad3on") is None


def test_the_rate_move_is_read_and_not_the_dissent_count():
    # "25bp" defeated the value parser, so the only number this label yielded
    # was the one AFTER it — the ladder rung was the dissent count, at 0.
    assert _outcome_threshold_value("Rate: 25bp hike, Dissents: >0") == (25.0, "", "exact")


def test_a_comparator_survives_the_glued_unit():
    # Regression on the fix itself: once "25bps" matched the compact VALUE
    # parser, it stopped falling through to the parser that reads comparators,
    # and "more than" was silently lost.
    assert _outcome_threshold_value("Hike more than 25bps") == (25.0, "", "above")
    # Mirrored on the far side of zero: "more than a 25bp cut" is BELOW -25.
    points = _ladder("SARB", SARB_OUTCOMES)
    cut_more = next(p for p in points if p["label"] == "Cut more than 25bps")
    assert cut_more["direction"] == "below"


def test_a_currency_code_is_not_a_basis_point():
    # The glued-unit fix is a lookbehind, not a dropped boundary: "GBP" ends in
    # "bp" and must not become threshold-shaped on that account.
    assert _outcome_threshold_value("GBPUSD") is None
    # ...and a label that was already shaped on its own account parses exactly
    # as it did before, direction included. The comparator borrow is scoped to
    # the glued-bps shape for this reason: unscoped it re-read 3,399 production
    # labels, bands among them.
    assert _outcome_threshold_value("GBP/USD above 1.30") == (1.3, "", "exact")


def test_the_venues_own_word_for_hold_is_the_zero_rung():
    # The lexicon is read off the live population, not off the two markets in
    # the issue. Eight live "Fed decision in <month>" ladders phrase their hold
    # as "Fed maintains rate" — and it is the MODAL outcome, 65% here. A lexicon
    # of only "no change"/"unchanged" leaves those eight cards without their most
    # likely outcome while looking entirely correct.
    points = _ladder(
        "Fed decision in Jan 2028?",
        [
            ("Cut 25bps", 0.20),
            ("Hike 25bps", 0.05),
            ("Hike >25bps", 0.02),
            ("Cut >25bps", 0.08),
            ("Fed maintains rate", 0.65),
        ],
    )

    assert len(points) == 5
    assert _by_label(points)["Fed maintains rate"] == 0.0
    assert max(points, key=lambda p: p["probability"])["label"] == "Fed maintains rate"


def test_a_zero_rung_is_never_a_ladder_by_itself():
    # A signed set that carries a hold label and NO number anywhere. Without the
    # guard this mints a one-rung "ladder" out of a market that has no magnitudes
    # at all — and a one-row heatmap falls through PAST the distribution branch
    # to the plain leader card, taking the whole field with it (the UX-P008
    # failure). Verified to REACH the guard: with it removed this returns a lone
    # rung at 0.0, so the assertion is not passing for some other reason.
    points = _ladder(
        "Central bank decision",
        [("Rate hike", 0.3), ("Rate cut", 0.3), ("No change", 0.4)],
    )

    assert points == []


def test_a_signed_set_with_no_magnitudes_draws_no_ladder():
    # The live specimen, "US test scores in Math in 2026?". Its direction words
    # sign the axis while it carries no number anywhere. Refused one step
    # earlier than the case above — "No significant difference" is not in the
    # zero lexicon and deliberately not added to it, because a market with no
    # magnitudes has no ladder to join.
    points = _ladder(
        "US test scores in Math in 2026?",
        [
            ("Significant decrease", 0.25),
            ("No significant difference", 0.5),
            ("Significant increase", 0.25),
        ],
    )

    assert points == []


def test_a_percent_change_ladder_signs_the_same_way():
    # Not a rate market: the live "NYC population change" ladder. Before, every
    # decrease collided with the increase of the same size — 1.0, 1.0, 2.0, 2.0,
    # 3.0, 3.0 — so three pairs of opposite outcomes shared three bars.
    labels = [
        "Decrease 1-1.99%",
        "Decrease 0-0.99%",
        "Decrease 3% or more",
        "Decrease 2-2.99%",
        "Increase 0.01-0.99%",
        "Increase 1-1.99%",
        "Increase 2-2.99%",
        "Increase 3%",
    ]
    points = _ladder(
        "NYC population change (July 2025 - July 2027)?",
        [(label, 0.125) for label in labels],
    )

    assert [p["label"] for p in points] == [
        "Decrease 3% or more",
        "Decrease 2-2.99%",
        "Decrease 1-1.99%",
        "Decrease 0-0.99%",
        "Increase 0.01-0.99%",
        "Increase 1-1.99%",
        "Increase 2-2.99%",
        "Increase 3%",
    ]
    # No served rung is negative zero — "Decrease 0-0.99%" has magnitude 0.
    assert not any(str(p["value"]) == "-0.0" for p in points)


def test_the_cumulative_coherence_guard_does_not_eat_a_signed_ladder():
    # Interaction with #4610/#4679/#4680. That guard reads a ladder as CUMULATIVE
    # — each rung a strict subset of every looser one — and drops rungs whose
    # price contradicts a neighbour. A signed rate ladder is the opposite shape:
    # its rungs are EXCLUSIVE outcomes, so its prices are humped and under a
    # cumulative reading would look incoherent. All five rungs must survive
    # whatever shape the prices take, or the fix above gives with one hand and
    # the guard takes back with the other.
    shapes = {
        "humped": [0.02, 0.08, 0.62, 0.24, 0.04],
        "rising": [0.05, 0.10, 0.20, 0.30, 0.35],
        "falling": [0.35, 0.30, 0.20, 0.10, 0.05],
        "flat": [0.20, 0.20, 0.20, 0.20, 0.20],
        "bimodal": [0.40, 0.05, 0.10, 0.05, 0.40],
    }
    labels = [name for name, _ in SARB_OUTCOMES]
    for shape, probabilities in shapes.items():
        points = _ladder("Central bank rate decision", list(zip(labels, probabilities)))
        assert len(points) == 5, f"{shape}: lost a rung to the cumulative guard"
        assert [p["value"] for p in points] == [-25.0, -25.0, 0.0, 25.0, 25.0], shape


# ── THE SAFETY ARGUMENT: signing is a property of the SET ──


def test_a_one_directional_ladder_is_never_signed():
    # A ladder of cuts is a ladder of MAGNITUDES. Negating on a per-label token
    # — the obvious implementation — would have flipped every rung here.
    points = _ladder(
        "How big is the next Fed cut?",
        [("Cut 25bps", 0.5), ("Cut 50bps", 0.3), ("Cut 75bps", 0.2)],
    )

    assert [p["value"] for p in points] == [25.0, 50.0, 75.0]
    assert all(p["value"] > 0 for p in points)


def test_a_cumulative_above_ladder_is_untouched():
    # No direction word anywhere: the signing machinery must not see this.
    points = _ladder(
        "Where will the index close?",
        [("Above 52", 0.8), ("Above 58", 0.5), ("Above 67", 0.2)],
    )

    assert [p["value"] for p in points] == [52.0, 58.0, 67.0]


def test_a_band_ladder_keeps_its_boundary_collision():
    # #4226's 277 markets. The open-ended first bucket collides with the bucket
    # above it and that is CORRECT; this fix must not have taught anything to
    # reject it.
    points = _ladder(
        "US GDP growth in Q2 2026?",
        [("<1.0%", 0.2), ("1.0–1.5%", 0.4), ("1.5–2.0%", 0.3), ("2.0–2.5%", 0.1)],
    )

    assert [p["value"] for p in points] == [1.0, 1.0, 1.5, 2.0]


def test_no_change_scores_nothing_on_an_unsigned_ladder():
    # "Hold" is a team name as often as a rate decision, and "no change" is not
    # a magnitude. Only the bidirectional gate makes reading them as zero safe.
    assert _outcome_threshold_value("No change") is None
    points = _ladder(
        "Top global Netflix show this week?",
        [("No change", 0.3), ("The Idaho Murders", 0.4), ("Hold", 0.3)],
    )

    assert points == [], "an unsigned field must not acquire a zero rung"
