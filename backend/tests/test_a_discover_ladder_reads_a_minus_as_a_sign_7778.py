"""#7778 — a minus in front of a number is a SIGN, and the negative half of a
mixed-sign axis stops folding onto the positive half.

Served on production 2026-09-21 (`5db738f9`), `GET /api/feed` market 60608886,
*South Africa GDP growth rate QoQ for Q3 2026*, `suggested_format =
threshold_heatmap`. Its rungs, verbatim from the payload:

    Above 0.0%    value 0.0    72.5%
    Above -0.2%   value 0.2    81.5%
    Above 0.2%    value 0.2    62.5%
    Above -0.4%   value 0.4    90.5%
    Above 0.4%    value 0.4    40.5%
    Above 0.6%    value 0.6    20.5%
    ...

Two pairs on one coordinate each, and a cumulative ladder reading
72.5 -> 81.5 -> 62.5 -> 90.5 -> 40.5 up its own bars: the card said the chance
of growth above 0.4% was HIGHER than the chance of growth above 0.0%, which
cannot be true, and it said two different things about "0.2%" in adjacent rows.

Cause: `_COMPACT_VALUE_RE`'s value group starts at `\\d`, so a leading minus was
invisible to it. This is #7081's defect (`routes/economics.py`, 42 points of
probability put on deflation) in a second module — never a regression of it, and
not covered by #4364, which signs a ladder off POLICY VERBS ("Cut"/"Hike") and
finds none on a board whose labels are bare signed percentages.

MEASURED BEFORE SHIPPING, old module loaded from git beside the new one over
every open-board label that could move (`artifacts/d383-7778/`):

  * 4,357 distinct hyphen-bearing labels on open boards — 121 move, every one of
    them from a positive magnitude to its negative twin, 4,236 byte-unchanged;
  * 265 open boards carry a sign-shaped label — 106 ladders reorder, **0 lose a
    rung, 0 gain one, 0 lose the ladder treatment**: this moves ORDER, never
    membership;
  * 36 boards drew two rungs at one coordinate and now draw none;
  * of the 43 cumulative ("Above …") boards in that set, 28 doubled back on
    themselves and now fall monotonically.

The one board that reads as a regression and is not (#363886, "CPI in
November") is asserted below: correcting the order exposes a 0.5pp inversion in
the venue's own prices that the fold was hiding.
"""

import pytest

from app.utils.discover_card_archetypes import (
    _compact_value_thresholds,
    _outcome_threshold_value,
    _threshold_points,
    classify_discover_card_archetype,
)

# Market 60608886 exactly as production holds it (db-query 2026-09-21 12:5xZ),
# in the venue's own row order — the reordering is the fix, so a fixture that
# arrived pre-sorted would assert nothing.
SA_GDP = [
    ("Above -0.4%", 0.905),
    ("Above -0.2%", 0.815),
    ("Above 0.0%", 0.725),
    ("Above 0.2%", 0.625),
    ("Above 0.4%", 0.405),
    ("Above 0.6%", 0.205),
    ("Above 0.8%", 0.105),
    ("Above 1.0%", 0.055),
    ("Above 1.2%", 0.040),
]

# #363886 "CPI in November", production row order. `Above -0.1%` is priced 80.5%
# under an `Above 0.0%` priced 81.0% — a looser rung cheaper than a tighter one.
CPI_NOVEMBER = [
    ("Above -0.1%", 0.805),
    ("Above 0.1%", 0.67),
    ("Above 0.0%", 0.81),
    ("Above 0.2%", 0.43),
    ("Above 0.5%", 0.135),
    ("Above 0.4%", 0.185),
    ("Above 0.3%", 0.295),
]


def _ladder(name, outcomes):
    return _threshold_points(
        name=name,
        outcomes=[{"name": n, "probability": p} for n, p in outcomes],
        outcome_count=len(outcomes),
    )


def _values(points):
    return {p["label"]: p["value"] for p in points}


# ── THE SPECIMEN ──


def test_the_two_halves_of_the_axis_stop_sharing_a_coordinate():
    values = _values(_ladder("South Africa GDP growth rate QoQ for Q3 2026", SA_GDP))
    assert values["Above -0.2%"] == pytest.approx(-0.2)
    assert values["Above 0.2%"] == pytest.approx(0.2)
    assert values["Above -0.4%"] == pytest.approx(-0.4)
    assert values["Above 0.4%"] == pytest.approx(0.4)
    assert len(set(values.values())) == len(values), values


def test_the_specimens_prices_stop_doubling_back_up_the_ladder():
    points = _ladder("South Africa GDP growth rate QoQ for Q3 2026", SA_GDP)
    prices = [p["probability"] for p in points]
    assert prices == sorted(prices, reverse=True), [
        (p["label"], p["value"], p["probability"]) for p in points
    ]
    # The reader's own sentence: the looser bar is the likelier one.
    assert prices[0] == pytest.approx(0.905)
    assert prices[-1] == pytest.approx(0.040)


def test_the_specimen_keeps_every_rung_it_had():
    """Order moves; membership does not. 0 of 265 production boards lost a rung."""
    points = _ladder("South Africa GDP growth rate QoQ for Q3 2026", SA_GDP)
    assert [p["label"] for p in points] == [
        "Above -0.4%",
        "Above -0.2%",
        "Above 0.0%",
        "Above 0.2%",
        "Above 0.4%",
        "Above 0.6%",
        "Above 0.8%",
        "Above 1.0%",
        "Above 1.2%",
    ]


def test_the_card_the_reader_gets_is_the_fixed_one():
    """Through the public entry point, not the private parser.

    `classify_discover_card_archetype` is what the feed calls, and it runs the
    labels through `display_outcome_names` first — a rung fixed only in
    `_threshold_points` but re-derived downstream would pass every test above
    and change nothing on the card (the #4151 lesson, same module).
    """
    card = classify_discover_card_archetype(
        name="South Africa GDP growth rate QoQ for Q3 2026",
        category="economics",
        outcomes=[{"name": n, "probability": p} for n, p in SA_GDP],
        outcome_count=len(SA_GDP),
    )
    assert card["suggested_format"] == "threshold_heatmap"
    drawn = [(p["label"], p["value"]) for p in card["threshold_points"]]
    assert drawn[0] == ("Above -0.4%", pytest.approx(-0.4))
    assert drawn[1] == ("Above -0.2%", pytest.approx(-0.2))
    assert [v for _, v in drawn] == sorted(v for _, v in drawn)


def test_correcting_the_order_exposes_a_price_inversion_it_did_not_cause():
    """#363886 is the honest residual, pinned so nobody reads it as a regression.

    The fold sorted `Above -0.1%` (80.5%) after `Above 0.0%` (81.0%) and the
    ladder looked monotone by accident. In the true order the two are adjacent
    and 0.5pp apart the wrong way — a venue/blend pricing disagreement this
    parser neither created nor can repair. What the fix owes the reader here is
    the honest coordinate, which it now serves.
    """
    points = _ladder("CPI in November", CPI_NOVEMBER)
    values = _values(points)
    assert values["Above -0.1%"] == pytest.approx(-0.1)
    assert [p["label"] for p in points][:2] == ["Above -0.1%", "Above 0.0%"]
    prices = [p["probability"] for p in points]
    assert prices != sorted(prices, reverse=True)
    # ...and the inversion is the DATA's, not a second folded pair.
    assert len(set(values.values())) == len(values)


# ── WHAT A MINUS IS NOT: the range separator ──
#
# Every one of these is a live production label shape. The value each scores is
# pinned to what master scores today, so a widening shows up as a failure here
# rather than as a moved population nobody measured.
@pytest.mark.parametrize(
    "label,expected",
    [
        ("7-8m", 7_000_000.0),  # a band, suffix governing both numbers
        ("160-170m", 160_000_000.0),
        ("$1.00-$1.10T", 1_000_000_000_000.0),
        ("Hike 1-25bps", 1.0),  # #4364's glued-unit label
        ("Republican 0-3%", 0.0),
        ("Under 4-6 inches", 4.0),
        ("80–83", 80.0),  # en dash, a genuine band
        ("72-73°F", 72.0),
    ],
)
def test_a_hyphen_between_two_numbers_is_still_a_range(label, expected):
    resolved = _outcome_threshold_value(label)
    assert resolved is not None, label
    assert resolved[0] == pytest.approx(expected), (label, resolved)


@pytest.mark.parametrize(
    "label",
    [
        "COVID-19",  # a letter before the hyphen: a name, not a sign
        "F-150",
        "Claude Opus 4-6 Thinking",  # #4226's model version
        "Barcelona SC 0 - 1 Delfin SC",  # a scoreline
        "September 15 - 30, 2026",  # a spaced date range
        "2026-27 Stanley Cup® Finals Winner",  # a season
    ],
)
def test_a_hyphen_inside_a_name_mints_no_negative_rung(label):
    resolved = _outcome_threshold_value(label)
    assert resolved is None or resolved[0] >= 0, (label, resolved)


def test_a_spaced_minus_is_a_separator_even_where_the_label_is_threshold_shaped():
    """`- 30` detached from its digits is a range dash; `-30` is a sign.

    This is the whole discriminator on the right-hand side, and it is the one a
    widened regex loses first.
    """
    assert _compact_value_thresholds("$100 - $200")[1][0] == pytest.approx(200.0)
    assert _compact_value_thresholds("Above -200")[0][0] == pytest.approx(-200.0)


# ── WHAT A MINUS IS: the sign ──


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Above -0.2%", -0.2),
        ("<-1.0%", -1.0),  # a comparator directly against the sign
        ("-0.3% to -0.1%", -0.3),  # a band entirely below zero
        ("(-2.5%)", -2.5),  # bracketed
        ("Above −0.2%", -0.2),  # U+2212, the venue's other minus
        ("<-50k", -50_000.0),  # the suffix multiplies the signed magnitude
        ("Above -25,000", -25_000.0),
    ],
)
def test_a_minus_in_front_of_a_number_reaches_the_rung(label, expected):
    resolved = _outcome_threshold_value(label)
    assert resolved is not None, label
    assert resolved[0] == pytest.approx(expected), (label, resolved)


def test_a_signed_number_is_never_read_as_a_year():
    """The bare-year guard reads an UNSIGNED number.

    "2026-27 Stanley Cup" is a season and scores nothing; "-2026" is a quantity.
    Without the sign in the guard's own condition a negative year-shaped value
    would be dropped from a ladder that has one.
    """
    assert _compact_value_thresholds("Before 2026") == []
    assert _compact_value_thresholds("Above -2026")[0][0] == pytest.approx(-2026.0)


def test_a_signed_magnitude_is_scaled_exactly_like_its_positive_twin():
    """`abs()` in the scale test, or the two halves of one axis use two rules."""
    assert _outcome_threshold_value("Above 50,000m")[0] == pytest.approx(
        -_outcome_threshold_value("Above -50,000m")[0]
    )


# ── THE TWO SIGNING MECHANISMS MUST NOT CANCEL (#4364 × #7778) ──


def test_a_policy_verb_does_not_flip_a_label_that_already_carries_its_sign():
    """A verb negates a MAGNITUDE. A label in signed coordinates has none.

    Without the guard, "Cut to -0.25%" is parsed at -0.25 and then negated by
    `_LADDER_FALL_RE` back to +0.25 — the rung lands on the hike side of the
    axis, which is the very defect #4364 shipped to remove.
    """
    points = _ladder(
        "Policy rate in December",
        [
            ("Hike to 0.75%", 0.10),
            ("No change", 0.55),
            ("Cut to -0.25%", 0.35),
        ],
    )
    values = _values(points)
    assert values["Cut to -0.25%"] == pytest.approx(-0.25)
    assert values["Hike to 0.75%"] == pytest.approx(0.75)
    assert values["No change"] == pytest.approx(0.0)
    assert [p["value"] for p in points] == sorted(p["value"] for p in points)


def test_the_4364_verb_ladder_is_byte_unchanged():
    """The SARB card #4364 shipped for carries no minus and must not move."""
    points = _ladder(
        "South African Reserve Bank rate decision in September",
        [
            ("Hike more than 25bps", 0.02),
            ("Hike 25bps", 0.08),
            ("No change", 0.62),
            ("Cut 25bps", 0.24),
            ("Cut more than 25bps", 0.04),
        ],
    )
    assert [(p["label"], p["value"], p["direction"]) for p in points] == [
        ("Cut more than 25bps", -25.0, "below"),
        ("Cut 25bps", -25.0, "exact"),
        ("No change", 0.0, "exact"),
        ("Hike 25bps", 25.0, "exact"),
        ("Hike more than 25bps", 25.0, "above"),
    ]


def test_a_one_sided_ladder_is_untouched():
    """The harmful direction: nothing that has no minus may move."""
    outcomes = [
        ("Above 52", 0.94),
        ("Above 58", 0.88),
        ("Above 67", 0.42),
    ]
    assert [(p["label"], p["value"]) for p in _ladder("Netflix top film", outcomes)] == [
        ("Above 52", 52.0),
        ("Above 58", 58.0),
        ("Above 67", 67.0),
    ]
