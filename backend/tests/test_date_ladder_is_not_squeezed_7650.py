"""#7650 — a DATE-shaped cumulative ladder is not divided by its own rungs either.

PILLAR: TRUTH. SHIP: a Discover card stops printing 32% for a market whose own
page prints 45.5%.

#7641 fixed the magnitude half of this class. The date half is the same defect in
the same function: "Before Oct 1, 2026" is contained in "Before Jan 1, 2027", so
the legs do not partition anything, their sum is not a total, and the quotient is
not a probability. MEASURED on the deployed feed 2026-09-21, each card cross-read
against its own `/api/futures/{id}`; the split is exactly the divisor:

    Will Trump declare a national emergency?  `Before Jan 1, 2027`  .455 / 1.42 -> .3204  (13.5 pts)
    When will Apple release the iPhone 18?    `Before April 2027`   .825 / 1.11 -> .7432  ( 8.2 pts)

═══ WHY THE GRAMMAR IS OPT-IN AND THE CONTROLS BELOW ARE THE SHIP'S REAL RISK ═══

`cumulative_outcome_ladder` is ONE predicate read by four reader-visible sites: the
card's divisor, the incoherent-rung drop, the field-collapse refusal, and the
leader copy. A widening lands on the POPULATION predicate, so all four move at
once and three of them are not the ship — which is the mistake #7641's abandoned
first build (`690ea46cb`) made with a different gate.

So the date grammar sits behind `dates=`, defaulting False, and the sites that
opted in did so on a census
(`artifacts/d352-7650/sibling-census.py`, 110 of 110 feed cards read:
5 fields flip, 2 card numbers move, 0 bars change, 0 fields collapse, 0 leader
captions are withheld). `test_a_numeric_ladder_is_byte_unchanged_by_the_widening`
is the control that keeps that census true: it is the assertion that would fail if
someone later made the date grammar reachable from the magnitude path.
"""

import pytest

from app.routes.feed import (
    _feed_display_scale,
    _leader_is_ladder_rung,
    _normalize_feed_probabilities,
    _outcomes_are_cumulative_ladder,
)
from app.utils.ladder_monotonicity import (
    cumulative_outcome_ladder,
    parse_cumulative_date_leg,
    parse_cumulative_leg,
)
from app.utils.outcome_display import (
    drop_incoherent_ladder_outcomes,
    incoherent_ladder_indexes,
    ladder_treatment_collapsed,
)


class _Outcome:
    """The two shapes `_feed_display_scale` sees — a live ORM `FuturesOutcome`
    and a rebuilt snapshot row — agree on these two attributes. `name` is in
    `OUTCOME_COLUMNS`, so the cached path carries it too."""

    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability


def _scale(pairs):
    return _feed_display_scale([_Outcome(n, p) for n, p in pairs])


#: `59693686` to the leg and to the price, off `futures_outcomes` 2026-09-21.
#: The unpriced `Before Dec 29, 2026` leg is real and is kept: a priceless rung
#: must not disqualify a ladder, and dropping it here would hide that.
TRUMP_EMERGENCY = [
    ("Before Jan 1, 2027", 0.455),
    ("Before Dec 1, 2026", 0.405),
    ("Before Nov 1, 2026", 0.355),
    ("Before Oct 1, 2026", 0.205),
    ("Before Dec 29, 2026", None),
]

#: `109349`, and the more demanding specimen: it mixes four date spellings —
#: month+year, bare year, and bare month with NO year at all — inside one family.
IPHONE_18 = [
    ("Before April 2027", 0.825),
    ("Before March 2027", 0.175),
    ("Before February 2027", 0.055),
    ("Before 2027", 0.045),
    ("Before October", 0.010),
    ("Before July", 0.0),
    ("Before April", 0.0),
]

#: #4079 test_7's fixture. Independent, NOT nested, sums to 1.40, must keep
#: dividing — the control whose failure killed #7641's first build.
INDEPENDENT_4079 = [
    ("Studio Aster", 0.60),
    ("Studio Birch", 0.50),
    ("Studio Cedar", 0.30),
]

#: The magnitude ladder #7641 shipped for. Nothing about it may move.
PANAMA = [
    ("Above 175", 0.965),
    ("Above 200", 0.42),
    ("Above 225", 0.18),
    ("Above 250", 0.06),
    ("Above 275", 0.025),
]


# ── THE SHIP ──────────────────────────────────────────────────────────────────

def test_the_trump_emergency_date_ladder_is_not_divided_by_its_own_rungs():
    """0.455 must survive to the card as 0.455, not 0.3204."""
    priced = [(n, p) for n, p in TRUMP_EMERGENCY if p is not None]
    assert sum(p for _, p in priced) == pytest.approx(1.42), (
        "the specimen no longer reproduces the 1.42 divisor it was chosen for"
    )
    assert _scale(TRUMP_EMERGENCY) == 1.0


def test_the_iphone_ladder_survives_four_date_spellings_in_one_family():
    """`Before April 2027` / `Before 2027` / `Before October` are one ladder.

    The bare-month legs carry no year at all, so this is also the pin on
    `DEFAULT_YEAR` doing its job: without it those three legs are unparseable and
    the all-legs discriminator refuses the whole market.
    """
    assert sum(p for _, p in IPHONE_18) == pytest.approx(1.11)
    assert _scale(IPHONE_18) == 1.0


def test_the_mini_list_shares_the_distribution_basis_on_a_date_ladder():
    """#7016: one outcome must not render at two numbers on one card. The
    divisor is decided in ONE place and `_normalize_feed_probabilities`
    delegates to it."""
    priced = [(n, p) for n, p in TRUMP_EMERGENCY if p is not None]
    outcomes = [_Outcome(n, p) for n, p in TRUMP_EMERGENCY]
    top = [{"name": n, "probability": p} for n, p in priced[:3]]
    out = _normalize_feed_probabilities(top, outcomes)
    assert [o["probability"] for o in out] == [0.455, 0.405, 0.355]


# ── THE CONTROLS: what the widening must NOT have moved ───────────────────────

def test_a_numeric_ladder_is_byte_unchanged_by_the_widening():
    """THE CONTROL THE CENSUS RESTS ON.

    The date grammar is additive and is tried LAST, so no magnitude leg can reach
    it and `dates=` cannot change a magnitude answer. If this fails, the 89
    unflipped fields in the d352 census were never really unflipped and every
    "0 of 5" in it is void.
    """
    for field in (PANAMA, INDEPENDENT_4079):
        rows = [{"name": n} for n, _ in field]
        assert (cumulative_outcome_ladder(rows, dates=False)
                == cumulative_outcome_ladder(rows, dates=True))
        for name, _ in field:
            assert (parse_cumulative_leg(name, dates=False)
                    == parse_cumulative_leg(name, dates=True))
    assert _scale(PANAMA) == 1.0
    assert _scale(INDEPENDENT_4079) == pytest.approx(1.40)


def test_the_gate_is_armed_and_not_a_no_op():
    """Anti-vacuity: a gate that answered 1.0 for everything passes every ship
    assertion above. The independent field and the date ladder differ ONLY in
    nestedness and must come back different."""
    assert _scale(TRUMP_EMERGENCY) != _scale(INDEPENDENT_4079)


def test_the_widening_is_off_by_default():
    """`dates` defaults False, so a caller that has not measured its population
    — `scripts/calibration_cell_exact.py` is the live one — keeps the narrow
    grammar. A default flip would re-base that instrument silently."""
    rows = [{"name": n} for n, _ in TRUMP_EMERGENCY]
    assert cumulative_outcome_ladder(rows) is None
    assert parse_cumulative_leg("Before Jan 1, 2027") is None


def test_the_drawn_bars_do_not_move_on_either_specimen():
    """SITES 2+3, the sibling consumers. Both live ladders are coherent, so the
    incoherent-rung drop must name nothing and the field must not collapse.
    Measured 0-of-5 across the feed; pinned here on the two specimens."""
    for field in (TRUMP_EMERGENCY, IPHONE_18):
        name_of, prob_of = (lambda o: o[0]), (lambda o: o[1])
        assert incoherent_ladder_indexes(field, name_of, prob_of) == set()
        assert ladder_treatment_collapsed(field, name_of, prob_of) is False
        assert drop_incoherent_ladder_outcomes(field, name_of, prob_of) == list(field)


def test_a_broken_date_ladder_still_loses_its_impossible_rung():
    """...and the drop is not inert BECAUSE it cannot see date ladders.

    The test above passes just as well if `incoherent_ladder_verdict` never
    recognised a date ladder at all. This is the same three specimens with one
    rung priced impossibly — `Before Nov 1` dearer than the `Before Jan 1` that
    contains it — and the drop must name exactly that rung.
    """
    broken = [("Before Oct 1, 2026", 0.20), ("Before Nov 1, 2026", 0.90),
              ("Before Dec 1, 2026", 0.40), ("Before Jan 1, 2027", 0.45)]
    named = incoherent_ladder_indexes(broken, lambda o: o[0], lambda o: o[1])
    assert named == {1}, "the drop did not name `Before Nov 1, 2026` (0.90)"


# ── THE GRAMMAR: accepts, refusals, and the sign ──────────────────────────────

@pytest.mark.parametrize("leg,value,direction", [
    ("Before Jan 1, 2027", 20270101, "inc"),
    ("Before Sept. 5, 2026", 20260905, "inc"),
    ("before jan 1 2027", 20270101, "inc"),
    ("By Dec 31, 2026", 20261231, "inc"),
    # A month with no day is pinned either side of every dated rung inside it,
    # by the WORD: `before April` is the 1st, `by April` is through the 30th.
    ("Before April 2027", 20270400, "inc"),
    ("By April 2027", 20270499, "inc"),
    ("Before 2027", 20270000, "inc"),
    ("By 2027", 20271299, "inc"),
    # `after` is the only descending date word: a later floor contains less.
    ("After 2027", 20271299, "dec"),
    ("After Mar 2027", 20270399, "dec"),
])
def test_the_date_grammar_reads_the_leg_and_the_sign(leg, value, direction):
    assert parse_cumulative_date_leg(leg) == (float(value), direction)


@pytest.mark.parametrize("leg", [
    # A 4-digit QUANTITY is not a year. Without the plausibility fence this
    # reads as the year 5000 and a threshold market becomes a date ladder.
    "Before 5000",
    "Before 1999",
    "Before 2101",
    # Trailing or leading prose is text the grammar cannot account for, which is
    # exactly the text that decides whether the leg is one-sided.
    "Before April 2027 or later",
    "Not before 2027",
    # A RANGE leg is the partition shape and must never read as one rung.
    "Before Jan-Mar 2027",
    # No direction word, no month, no leg.
    "Jan 2027",
    "Before the election",
    "Before",
    "Yes",
])
def test_the_date_grammar_refuses(leg):
    assert parse_cumulative_date_leg(leg) is None


@pytest.mark.parametrize("names,why", [
    (["Before Jan 1, 2027", "By Mar 1, 2027"],
     "a family may not MIX the date words: `before D` and `by D` are a day apart "
     "in meaning and identical in this encoding"),
    (["Before Jan 1, 2027", "Above 175"],
     "a date leg and a magnitude leg are not rungs of one quantity"),
    (["Before Jan 2027", "Jan-Mar 2027", "After Mar 2027"],
     "the bracketed date PARTITION dies on its middle leg"),
    (["Before Jan 1, 2027", "After Jan 1, 2027"],
     "a two-tail pair points both ways and is not a ladder"),
    (["Before Jan 1, 2027", "Before Feb 1, 2027", "Something else"],
     "one prose leg disqualifies the market rather than being skipped"),
    (["Before Jan 1, 2027", "Before Jan 1, 2027"],
     "a duplicate rung is the outcome-site form of a key that groups two ladders"),
    (["Before Jan 1, 2027"],
     "a single leg is never a ladder"),
])
def test_the_set_level_discriminator_fails_closed(names, why):
    assert cumulative_outcome_ladder(
        [{"name": n} for n in names], dates=True) is None, why


def test_a_genuine_after_family_is_still_read():
    """Anti-vacuity for the refusal table: `after` legs are refused above only
    when they are mixed or bracketed, not because the word is unreadable."""
    read = cumulative_outcome_ladder(
        [{"name": n} for n in
         ("After Jan 1, 2027", "After Feb 1, 2027", "After Mar 1, 2027")],
        dates=True,
    )
    assert read is not None
    legs, direction = read
    assert direction == "dec"
    assert [v for v, _ in legs] == [20270101.0, 20270201.0, 20270301.0]


def test_both_ladder_predicates_answer_the_same_field_the_same_way():
    """Two helpers, one question (#7641's own pin, extended to the date shape).
    The failure mode is that they drift and the card calls a field a ladder for
    its COPY and a distribution for its NUMBERS."""
    for field in (TRUMP_EMERGENCY, IPHONE_18, PANAMA, INDEPENDENT_4079):
        dicts = [{"name": n} for n, _ in field]
        objects = [_Outcome(n, p) for n, p in field]
        assert _leader_is_ladder_rung(dicts) == _outcomes_are_cumulative_ladder(objects)
