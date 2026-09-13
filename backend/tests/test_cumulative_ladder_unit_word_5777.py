"""#5777 — a cumulative rung stays a rung when a unit or label word sits beside it.

`Above 600,000 bales leads at 95%` survived #4640. It survived because the
cumulative grammar pinned the number to an END of the string, so three live leg
shapes were refused outright — and since
:func:`cumulative_outcome_ladder` disqualifies a market on its FIRST unparsed
leg, one refused leg hid the whole family from every ladder guard. The guards
then reported the silence as health, which is CAL-P134's blindness one layer in
(gotcha #53: the instrument reported its own blind spot as a clean cell).

The three shapes, each refused for a DIFFERENT reason, all measured on
production 2026-09-12 via `db-query` over `futures_outcomes`:

    Above 600,000 bales     the unit word TRAILS the number
    Category 3 or above     the label word LEADS the number   (33 markets × 5)
    26°C or below           a unit SYMBOL is glued to the digits

Only the second is named in the issue body; a trailing-only fix would have left
the other two live, which is why the arms below are three and not one.

WHAT THIS SUITE IS REALLY GUARDING is not the widening — it is the widening's
BLAST RADIUS. A liberal affix is the right instrument (an allowlist of units
goes stale the first time a venue lists a new commodity) but it is only safe
because of what it refuses, so every refusal has its own arm here:

  * a RANGE leg still refuses            (digits in the affix)
  * a two-sided leg still refuses        (a direction word in the affix)
  * a SPELLED magnitude still refuses    (reading "3 billion" as 3.0 would be a
                                          rung wrong by 1e9 — worse than a miss)
  * legs whose affixes DISAGREE refuse   (the over-reach this suite exists for)

That last one is the sharp edge and it is not hypothetical. The live market
`2028 Electoral College margin of victory?` (25922376) carries
`Democratic by 211 or more` AND `Republican by 211 or more`: both parse under
the widened grammar, both point the same way, and they mean opposite things.
Its other twelve legs are ranges, so the all-legs discriminator already refuses
the real market — which means the real market could NOT have caught a missing
label check. The two-leg arm below manufactures the market that would
(a defect on a path with no natural specimen has to have one manufactured).
"""

import pytest

from app.utils.ladder_monotonicity import (
    DEC,
    INC,
    cumulative_outcome_ladder,
    parse_cumulative_leg,
)


def _legs(*names: str) -> list[dict[str, str]]:
    return [{"name": name} for name in names]


# ─── Populations, read from production 2026-09-12 ────────────────────────────
#
# `Hurricane Norbert category?` (futures market 59699697), the whole outcome set
# in the row order `futures_outcomes` returned it. 33 markets share this shape
# (`KXHURCAT-26<NAME>`, ids 59699680–59699713), five rungs each = 165 outcomes.
NORBERT = (
    "Category 5 or above", "Category 1 or above", "Category 2 or above",
    "Category 3 or above", "Category 4 or above",
)

# `2028 Electoral College margin of victory?` (futures market 25922376), all 14.
ELECTORAL_COLLEGE = (
    "Democratic by 91 to 130", "Democratic by 61 to 90", "Democratic by 31 to 60",
    "Democratic by 11 to 30", "Republican by 61 to 90", "Republican by 91 to 130",
    "Republican by 31 to 60", "Republican by 211 or more", "Democratic by 1 to 10",
    "Democratic by 211 or more", "Democratic by 131 to 210", "Republican by 1 to 10",
    "Republican by 11 to 30", "Republican by 131 to 210",
)


# ─── The three shapes that were refused ──────────────────────────────────────

@pytest.mark.parametrize("leg,value,direction", [
    # the unit word TRAILS — this issue's headline specimen
    ("Above 600,000 bales", 600_000.0, DEC),
    # the label word LEADS — the 33-market hurricane family
    ("Category 3 or above", 3.0, DEC),
    ("Category 1 or above", 1.0, DEC),
    # a unit SYMBOL glued to the digits — named in neither the issue nor its
    # comments; found by censusing the leg shapes before designing the grammar
    ("26°C or below", 26.0, INC),
    ("36°C or higher", 36.0, DEC),
])
def test_a_rung_with_a_unit_or_label_word_is_still_a_rung(leg, value, direction):
    assert parse_cumulative_leg(leg) == (value, direction)


@pytest.mark.parametrize("leg,value,direction", [
    ("7,175 or above", 7175.0, DEC),
    ("$25,600 or higher", 25_600.0, DEC),
    ("Above 410M", 410_000_000.0, DEC),
    ("above $68.25", 68.25, DEC),
    ("3.0% or less", 3.0, INC),
    ("0.0% or Below", 0.0, INC),
    ("2400+", 2400.0, DEC),
])
def test_the_shapes_that_already_parsed_are_untouched(leg, value, direction):
    """The widening adds shapes; it may not move one that already worked."""
    assert parse_cumulative_leg(leg) == (value, direction)


# ─── The refusals that make the widening safe ────────────────────────────────

@pytest.mark.parametrize("leg", [
    "Yes", "No", "", None, "Trump",
    "5-6", "$100 to $200", "5 to 10",          # ranges partition, never nest
    "Democratic by 91 to 130",                 # a range wearing a label
    "<5", ">16",                               # tail legs of a bracket market
    "Above 410M or below 400M",                # two rungs in one leg
    "Above 5 or below 10",
    "Under 5 or above",                        # a direction word LEADING a post leg
    "Above 3 billion", "at least 2000 million",  # spelled magnitude: refuse,
                                               # never read as a bare noun
])
def test_the_widened_grammar_still_refuses_what_is_not_one_rung(leg):
    assert parse_cumulative_leg(leg) is None


def test_a_spelled_magnitude_is_refused_rather_than_valued_wrong():
    """Refusing is the status quo; a wrong magnitude would be new damage.

    `_NUM` knows the letter suffixes (`410M`, `3bn`) and nothing else. Admitting
    "billion" as an ordinary affix noun would value this rung at 3.0 inside a
    law whose only job is comparing rung values to each other — a silent error
    of 1e9, and strictly worse than the miss it would be replacing.
    """
    assert parse_cumulative_leg("Above 3 billion") is None
    assert parse_cumulative_leg("Above 3 billion") != (3.0, DEC)
    assert parse_cumulative_leg("Above 3bn") == (3_000_000_000.0, DEC)


# ─── Whole markets ───────────────────────────────────────────────────────────

def test_the_hurricane_family_is_now_one_ladder():
    ladder = cumulative_outcome_ladder(_legs(*NORBERT))
    assert ladder is not None, "the 33-market hurricane family is still invisible"
    ordered, direction = ladder
    assert [value for value, _ in ordered] == [1.0, 2.0, 3.0, 4.0, 5.0]
    # P(at least category N) can only FALL as N rises — the containment argument,
    # not a convention.
    assert direction == DEC


def test_the_electoral_college_market_is_still_refused():
    """The mixed set the widening must NOT reach.

    Twelve of its fourteen legs are ranges, so the all-legs discriminator
    refuses the market on the first of them. This asserts the discriminator
    still bites after the grammar got more permissive — the single most likely
    way this change could go wrong at scale.
    """
    assert cumulative_outcome_ladder(_legs(*ELECTORAL_COLLEGE)) is None


def test_two_legs_that_parse_but_mean_opposite_things_are_not_a_ladder():
    """The manufactured specimen — see this module's docstring.

    Both legs parse, both point DEC, and their values differ, so every check
    that existed before #5777 passes them. Only comparing the LABELS refuses
    them, and the real market that inspired this arm cannot exercise it because
    its range legs disqualify it earlier.
    """
    assert parse_cumulative_leg("Democratic by 211 or more") == (211.0, DEC)
    assert parse_cumulative_leg("Republican by 130 or more") == (130.0, DEC)
    assert cumulative_outcome_ladder(
        _legs("Democratic by 211 or more", "Republican by 130 or more")) is None
    # ...and the same two rungs on ONE side ARE a ladder, so the refusal above
    # is about the labels disagreeing and not about the shape.
    assert cumulative_outcome_ladder(
        _legs("Democratic by 211 or more", "Democratic by 130 or more")) is not None


@pytest.mark.parametrize("legs,is_ladder", [
    (("Above 600,000 bales", "Above 700,000 bales"), True),
    (("Above 600,000 bales", "Above 700,000 tonnes"), False),   # two quantities
    (("26°C or below", "27°C or below", "28°C or below"), True),
    (("26°C or below", "27°F or below"), False),                # two scales
    (("Category 1 or above", "Above 2"), False),                # labelled vs bare
])
def test_a_ladders_rungs_must_carry_the_same_unit(legs, is_ladder):
    assert (cumulative_outcome_ladder(_legs(*legs)) is not None) is is_ladder


@pytest.mark.parametrize("legs", [
    ("Above 410M", "420M or above"),      # direction word leads, then trails
    ("2400+", "Above 2500"),              # the pre-CAL-P134 bracket, then PRE
    ("2400+", "2500 or above"),           # ...and then POST
])
def test_one_ladder_may_spell_its_rungs_two_ways(legs):
    """The same-affix rule is about the QUANTITY, never about the spelling.

    These legs carry no unit and no label at all, so nothing distinguishes them
    but which grammar matched — and the two grammars yield a different NUMBER of
    affix parts (PRE has a trailing one, POST has a leading and a trailing one).
    A same-affix check that joined parts positionally would key the unadorned
    ``Above 410M`` as ``""`` and the equally unadorned ``420M or above`` as
    ``"|"`` and refuse a perfectly good ladder for an artefact of its own
    bookkeeping. This regression was live in the first cut of #5777 and these
    three pairs are what caught it.
    """
    assert cumulative_outcome_ladder(_legs(*legs)) is not None
