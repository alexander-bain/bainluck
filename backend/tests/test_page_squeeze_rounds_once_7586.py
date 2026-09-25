"""#7586 exclusive remainder — the page's squeezed leg is rounded ONCE, like the card's.

After #8471 the last three card-vs-page splits on #7586 were all one point, all on
one-winner fields, all with the page one point HIGHER. Both surfaces divide the field
by the same raw sum. The difference is what happens to the quotient afterwards:

    card  `feed._scale_display_probability`   round(raw / sum, 4)          .6447 -> 64
    page  `normalize_display_probs` -> politics `_normalize_outcome_probs`
          round(raw / sum * 100, 1) / 100                                  .645  -> 65

The page's one decimal of a percent is a first rounding, and the client's half-up
`renderedPercent` is a second one. 0.88 / 1.365 = .64469 is 64.47%, the page
served 64.5, and 64.5 rounds up. The card is the arithmetically correct surface.

MEASURED on production 2026-09-25 05:20Z (fresh read, legs copied verbatim off
`futures_outcomes` below):

    62121678 What will be the #2 US Netflix movie   card .6447 64 · page .645 65
    52756008 Big Brother Season 28 · 3rd place      card .4545 45 · page .455 46
    56947465 NASCAR Cup Series: 2026 Champion       card .2848 28 · page .285 29  (05:44Z)

🪤 THE HAND-OFF'S MECHANISM WAS WRONG, AND THIS IS THE CHECK THAT REFUTED IT. The
hand-off read "the card renormalizes a field summing ~1.001". The ~1.001 was the
ratio between the two printed values. The field sums are 1.365 and 1.155. On the
Netflix card the second leg is .1832 against the page's .183. The card is HIGHER, which no
divisor >= 1 on the card side can produce. A tolerance band around 1.0 would have
been inert.

The repair moves the page: `normalize_display_probs` asks for two decimals of a
percent (the card's 4dp). `/politics`, which prints the column itself, keeps its
default single decimal.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from app.routes import politics
from app.routes.feed import _feed_display_scale, _scale_display_probability
from app.utils.outcome_display import normalize_display_probs

# `62121678` What will be the #2 US Netflix movie this week? — mutually_exclusive,
# 5/5 priced, raw sum 1.365. Off `futures_outcomes` 2026-09-25 05:20Z.
NETFLIX_LEGS = [
    ("The Ministry of Ungentlemanly Warfare", 0.88),
    ("Best of the Best", 0.25),
    ("A Minecraft Movie", 0.135),
    ("Riot", 0.05),
    ("Why Did I Get Married Again?", 0.05),
]

# `52756008` Big Brother Season 28 · 3rd place — mutually_exclusive, 17/17 priced,
# raw sum 1.155. Same read.
BIG_BROTHER_LEGS = [
    ("Rick Devens", 0.525),
    ("Taylor Brown", 0.355),
    ("Drew Campbell", 0.11),
    ("Dee Valladares", 0.035),
] + [(f"leg{i}", 0.01) for i in range(13)]

# `56947465` NASCAR Cup Series: 2026 Champion — the third d485 specimen, re-read
# 2026-09-25 05:44Z. Its price moved since d485 (Hamlin was the 27/28 leader) and
# landed on the boundary AGAIN one leg up: Hamlin .325 / 1.141 = .28484 — the old
# page wrote 28.5 and printed 29 beside the card's 28. Twenty real zeros ride along.
NASCAR_LEGS = [
    ("Denny Hamlin", 0.325),
    ("Kyle Larson", 0.2735),
    ("Joey Logano", 0.139),
    ("Christopher Bell", 0.1315),
    ("Ryan Blaney", 0.085),
    ("Bubba Wallace", 0.039),
    ("Ty Gibbs", 0.038),
    ("Tyler Reddick", 0.032),
    ("Carson Hocevar", 0.0315),
    ("Chase Briscoe", 0.024),
    ("Daniel Suarez", 0.007),
    ("William Byron", 0.0065),
    ("Chase Elliott", 0.0025),
    ("Chris Buescher", 0.0025),
    ("Ryan Preece", 0.0025),
    ("Austin Cindric", 0.0015),
] + [(f"zero{i}", 0.0) for i in range(20)]

FIELDS = {
    "62121678": NETFLIX_LEGS,
    "52756008": BIG_BROTHER_LEGS,
    "56947465": NASCAR_LEGS,
}


def rendered_percent(p: float) -> int:
    """`frontend/lib/renderedPercent.ts` `renderedPercent`: Math.round(p*1000/10)."""
    return math.floor(p * 1000 / 10 + 0.5)


def page_legs(legs, **kwargs) -> list[float]:
    rows = [{"probability": p} for _name, p in legs]
    normalize_display_probs(rows, **kwargs)
    return [r["probability"] for r in rows]


def card_legs(legs) -> list[float]:
    outs = [SimpleNamespace(name=n, current_probability=p) for n, p in legs]
    scale = _feed_display_scale(outs, "field", mutually_exclusive=True)
    return [_scale_display_probability(p, scale) for _n, p in legs]


class TestTheSpecimensPrintOneNumber:
    @pytest.mark.parametrize(
        "legs, leader_value, leader_pct",
        [
            (NETFLIX_LEGS, 0.6447, 64),
            # #8595 re-pins Big Brother: its thirteen legs at exactly 0.01 are
            # Kalshi's one-cent floor, upper bounds out of the divisor. The four
            # priced legs sum 1.025, inside the threshold, so it prints raw.
            # NASCAR's sub-cent legs are real prices and stay in the divisor.
            (BIG_BROTHER_LEGS, 0.525, 53),
            (NASCAR_LEGS, 0.2848, 28),
        ],
        ids=["62121678", "52756008", "56947465"],
    )
    def test_the_leader_prints_the_cards_percent_on_the_page(
        self, legs, leader_value, leader_pct
    ):
        page = page_legs(legs)
        card = card_legs(legs)
        # Pinned by hand, not by calling either normalizer: raw / sum to 4dp (#8595: floor legs out).
        assert card[0] == leader_value
        assert page[0] == leader_value
        assert rendered_percent(card[0]) == leader_pct  # the card was never wrong
        assert rendered_percent(page[0]) == leader_pct, (
            f"page served {page[0]} -> {rendered_percent(page[0])}%; the card "
            f"prints {leader_pct}% for the same leg"
        )

    @pytest.mark.parametrize("market_id", list(FIELDS))
    def test_every_leg_of_every_field_is_the_same_value_on_both_surfaces(
        self, market_id
    ):
        legs = FIELDS[market_id]
        page = page_legs(legs)
        card = card_legs(legs)
        for (name, _raw), p, c in zip(legs, page, card):
            assert p == pytest.approx(
                c, abs=1e-9
            ), f"{market_id} {name}: page {p} card {c}"
            assert rendered_percent(p) == rendered_percent(c)

    def test_the_boundary_specimens_really_sit_on_the_boundary(self):
        """If .88/1.365 did not land between 64.45 and 64.5, the tests above
        would pass without testing double rounding at all."""
        for raw, total, old_write in (
            (0.88, 1.365, 64.5),
            (0.525, 1.155, 45.5),
            (0.325, 1.141, 28.5),
        ):
            exact = raw / total
            assert old_write - 0.05 <= exact * 100 < old_write  # rounds down once
            assert round(exact * 100, 1) == old_write  # the old first rounding


class TestTheOldRoundingFailsThisGuard:
    """Strawman: put the one-decimal call back and the specimen splits again."""

    def test_one_decimal_on_the_page_reopens_the_split(self, monkeypatch):
        real = politics._normalize_outcome_probs

        def _one_decimal(outcomes, key="prob", *, decimals=1):
            real(outcomes, key=key, decimals=1)

        monkeypatch.setattr(politics, "_normalize_outcome_probs", _one_decimal)
        page = page_legs(NETFLIX_LEGS)
        card = card_legs(NETFLIX_LEGS)
        assert page[0] == 0.645
        assert rendered_percent(page[0]) == 65 != rendered_percent(card[0]) == 64


class TestControls:
    def test_politics_keeps_its_own_single_decimal(self):
        rows = [{"prob": p * 100} for _n, p in NETFLIX_LEGS]
        politics._normalize_outcome_probs(rows)
        assert rows[0]["prob"] == 64.5

    def test_a_non_exclusive_field_stays_raw(self):
        assert page_legs(NETFLIX_LEGS, mutually_exclusive=False) == [
            p for _n, p in NETFLIX_LEGS
        ]

    def test_a_field_with_withheld_members_stays_raw(self):
        assert page_legs(NETFLIX_LEGS, field_complete=False) == [
            p for _n, p in NETFLIX_LEGS
        ]

    def test_a_real_zero_stays_zero(self):
        page = page_legs(NASCAR_LEGS)
        assert page[-2:] == [0.0, 0.0]

    def test_a_field_already_near_one_is_not_squeezed(self):
        legs = [("a", 0.5), ("b", 0.3), ("c", 0.2015)]
        assert page_legs(legs) == [0.5, 0.3, 0.2015]
