"""#8210 — a 25-name field stops being crowned by a player nobody will bid a cent for.

WHAT A READER SAW, on production 2026-09-23. `/futures/61003887` ("Australian
Open Women's Singles Winner") printed, in the page's largest type:

    58%
    Karolina Muchova
    Resolves Feb 1, 2027

rank 1 of 25, above Elena Rybakina 25%, Aryna Sabalenka 23% and Coco Gauff 18% —
and repeated the board as a card in TOURNAMENT WINNERS on `/hub/tennis`, where
her bar is more than twice the length of every other bar on the card.

Read at the venue the same morning — Kalshi's own `/trade-api/v2/markets?
event_ticker=KXWTA-27AO`, not our mirror (notices 26/27):

    yes_bid 0.0000 (size 0)      yes_ask 0.7000 (size 50)
    last_price 0.5800            volume_fp 1.00  <- ONE CONTRACT, LIFETIME
    volume_24h_fp 0.00           liquidity_dollars 0.0000      status active
    updated_time 2026-09-13T23:30:00Z

Nobody is bidding anything. The 58 is a single contract that changed hands ten
days earlier, and it is the only thing calling her the favourite.

🔴 THIS IS RULE 2's EXEMPTION, WHICH #7747 LEFT WHOLE ON A MEASUREMENT THAT
COULD NOT SEE THIS LEG. `price_is_unsupported` spares any leg with a positive
`last_price`; `price_is_an_unbacked_ask` declined to re-litigate that on a
cross-tab whose last row reads `either | INSIDE the spread | 0`. That row's
population is screened on the price sitting AT its own ask, so "a trade inside
the spread" is empty by construction. Muchova is that empty cell.

🔴 THE FIXTURE IS THE SPECIMEN. Every row in `AO_2027_WOMENS` is a real
production row of market 61003887 — book, newest Kalshi trade and the venue's
own 24-hour volume included. Its most useful property is that the SHIPPED arms
already withhold exactly three of these legs, which is what production served
(`prices_withheld: 3`), so any drift shows up as the shipped count moving rather
than as a silent strawman.

🪤 THE CONTROLS ARE ON THE SPECIMEN'S OWN BOARD, which is what makes them worth
more than invented ones. Every one of them is a leg this arm MUST NOT reach:

  * Elena Rybakina — 0.25 on a 0.1600/0.3400 book. A real two-sided book, and
    she is the board's hero AFTER the fix. A rule that blanked her would replace
    one wrong hero with no hero.
  * Iga Swiatek — 0.095 on a 0.0100/0.1800 book. A bid of ONE CENT, the
    tightest possible separation from "nobody is bidding". If this leg falls,
    the rule is keyed on something other than the zero bid it claims.
  * Jessica Pegula (0.29 on 0.0000/0.2900) and Naomi Osaka (0.17 on
    0.0000/0.1700) — zero bids and NO trade, already withheld by #6846 and both
    BELOW the half. They prove this arm is not what catches them.
  * Alexandra Eala — 0.08 on a 0.0300/0.1300 book, a two-sided longshot.

🪤 AND THE WHOLE-BOARD CONTROL IS THE ONE THAT CAN FAIL. The first draft of this
rule used the sibling arm's spread fence (`ASK_ONLY_TRUSTED_MAX`) instead of a
half, and it withheld 33 legs on 15 boards — mostly 1-3% longshots whose stale
print agrees with their own book. `test_the_board_loses_exactly_one_leg` is
what refutes any such widening: it pins the served column, not just the
specimen, so a predicate that reaches one leg further fails here rather than in
production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.futures_unsupported_price import (
    UNBID_CLAIM_CEILING,
    market_is_proved_exclusive_field,
    needs_unbacked_majority_evidence,
    price_is_an_unbacked_ask,
    price_is_an_unbacked_majority,
    price_is_unsupported,
)

# The classifier's persisted verdict for market 61003887, copied from
# `market_metadata->'shape'` on production. `exhaustive`/`expected_winners`/
# `outcome_relation` are the three `market_is_proved_exclusive_field` reads.
AO_SHAPE = {
    "v": 2,
    "shape": "field",
    "side_kind": "competitors",
    "confidence": "high",
    "exhaustive": True,
    "outcome_count": 25,
    "expected_winners": 1,
    "outcome_relation": "competitors",
    "classifier_version": 2,
}
AO_METADATA = {"shape": AO_SHAPE}

# (name, probability, yes_bid, yes_ask, newest kalshi last_price)
# The nine legs of market 61003887 that carry a stored price, verbatim from
# production 2026-09-23. The other sixteen are unpriced and are not candidates.
AO_2027_WOMENS = [
    ("Amanda Anisimova", 0.71, 0.0000, 0.7100, 0.7100),
    ("Karolina Muchova", 0.58, 0.0000, 0.7000, 0.5800),
    ("Jessica Pegula", 0.29, 0.0000, 0.2900, 0.0000),
    ("Elena Rybakina", 0.25, 0.1600, 0.3400, 0.3400),
    ("Aryna Sabalenka", 0.23, 0.1500, 0.3100, 0.3100),
    ("Coco Gauff", 0.18, 0.1100, 0.2500, 0.2500),
    ("Naomi Osaka", 0.17, 0.0000, 0.1700, 0.0000),
    ("Iga Swiatek", 0.095, 0.0100, 0.1800, 0.0000),
    ("Alexandra Eala", 0.08, 0.0300, 0.1300, 0.1300),
]

BY_NAME = {row[0]: row for row in AO_2027_WOMENS}

#: The three legs the SHIPPED arms already withhold. Production served
#: `prices_withheld: 3` on this board, and this set reproducing it exactly is
#: what makes the fixture a replay rather than an invention.
#:
#: Anisimova is the SIBLING arm's (#7747) — a zero bid with the price AT its own
#: ask. Pegula and Osaka are #6846's — a zero bid with no trade at all.
ALREADY_WITHHELD_BY_SHIPPED_RULES = {
    "Amanda Anisimova",
    "Jessica Pegula",
    "Naomi Osaka",
}

#: The one leg this ship adds, and the name the hero stops crowning.
NEWLY_WITHHELD = "Karolina Muchova"

#: The touch-stamp every leg of this board carries. Production value at capture.
LAST_SEEN = datetime(2026, 9, 23, 9, 52, 24, tzinfo=timezone.utc)

#: The venue's own 24-hour volume, READ FROM KALSHI 2026-09-23
#: (`GET /trade-api/v2/markets?event_ticker=KXWTA-27AO`, notice 26 — the venue's
#: API, not our mirror). `volume_24h_fp` is 0.00 for all 25 legs of this board:
#: it is a 2027 futures field and nobody is trading any of it today.
#:
#: 🪤 THE BOARD BEING UNIFORM ON THIS COLUMN IS EXACTLY WHY THE VOLUME TERM GETS
#: ITS OWN CLASS BELOW rather than being exercised by the fixture. A constant
#: column cannot discriminate, so `TestTheVolumeTermIsLoadBearing` varies it on
#: the specimen's own row instead of pretending the board does.
UNTRADED = (0.00, LAST_SEEN, LAST_SEEN)

#: What the venue says about a leg somebody IS trading. 1.74 is the figure
#: #7747's own fixture carries for Jannik Sinner, reused so the two arms agree
#: about what "traded" looks like.
TRADED = (1.74, LAST_SEEN, LAST_SEEN)

#: "We have never asked the venue" — NULL, which is not "nobody traded it"
#: (gotcha #53). It must FAIL OPEN.
NEVER_ASKED = (None, None, LAST_SEEN)


def _majority(name, *, volume=UNTRADED, resolution_source=None, in_field=True):
    """Run the new arm over one real row of the specimen board."""
    _, probability, yes_bid, yes_ask, last_price = BY_NAME[name]
    volume_24h, volume_24h_at, last_seen_at = volume
    return price_is_an_unbacked_majority(
        "kalshi",
        resolution_source,
        probability,
        yes_bid,
        yes_ask,
        last_price,
        has_trade_evidence=last_price is not None,
        in_exclusive_field=in_field,
        volume_24h=volume_24h,
        volume_24h_at=volume_24h_at,
        last_seen_at=last_seen_at,
    )


def _shipped_arms_withhold(name):
    """The two arms that shipped before #8210, over one real row."""
    _, probability, yes_bid, yes_ask, last_price = BY_NAME[name]
    has_trade = last_price is not None
    if price_is_unsupported(
        "kalshi",
        None,
        yes_bid,
        yes_ask,
        last_price,
        has_trade_evidence=has_trade,
        in_exclusive_field=True,
    ):
        return True
    return price_is_an_unbacked_ask(
        "kalshi",
        None,
        probability,
        yes_bid,
        yes_ask,
        last_price,
        has_trade_evidence=has_trade,
        in_exclusive_field=True,
        volume_24h=UNTRADED[0],
        volume_24h_at=UNTRADED[1],
        last_seen_at=UNTRADED[2],
    )


class TestTheSpecimen:
    def test_the_board_is_a_proved_exclusive_field(self):
        """Without this the arm never runs, so the fixture asserts its own gate."""
        assert market_is_proved_exclusive_field("field", AO_METADATA)

    def test_muchova_is_withheld(self):
        assert _majority(NEWLY_WITHHELD) is True

    def test_no_shipped_arm_reaches_her_which_is_why_this_arm_exists(self):
        """The issue's central claim, asserted rather than quoted.

        If a later change makes a shipped arm catch her, this fails and the new
        arm is redundant — that is a result worth being told about, not a
        nuisance.
        """
        assert _shipped_arms_withhold(NEWLY_WITHHELD) is False

    def test_her_price_is_a_trade_strictly_inside_an_unbid_spread(self):
        """The shape #7817's cross-tab could not contain, stated on the row."""
        _, probability, yes_bid, yes_ask, last_price = BY_NAME[NEWLY_WITHHELD]
        assert yes_bid == 0.0
        assert last_price == probability
        assert 0 < last_price < yes_ask
        assert probability > UNBID_CLAIM_CEILING


class TestTheControlsOnHerOwnBoard:
    """Legs this arm must not reach. Each is a real row of market 61003887."""

    @pytest.mark.parametrize(
        "name",
        ["Elena Rybakina", "Aryna Sabalenka", "Coco Gauff", "Alexandra Eala"],
    )
    def test_a_two_sided_book_keeps_its_price(self, name):
        assert _majority(name) is False

    def test_a_one_cent_bid_is_still_a_bid(self):
        """Swiatek, 0.0100 — the tightest separation from "nobody is bidding"."""
        assert _majority("Iga Swiatek") is False

    def test_the_replacement_hero_survives(self):
        """Rybakina inherits rank 1. A rule that blanks her fixes nothing."""
        assert _majority("Elena Rybakina") is False

    @pytest.mark.parametrize("name", ["Jessica Pegula", "Naomi Osaka"])
    def test_an_untraded_zero_bid_below_the_half_is_not_this_arms(self, name):
        """Already #6846's, and below the ceiling. This arm declines them."""
        assert _majority(name) is False
        assert _shipped_arms_withhold(name) is True

    def test_the_sibling_arms_leg_is_deliberately_also_caught(self):
        """Anisimova prints AT her ask, so both arms fire. The route ORs them.

        Asserted rather than left implicit because the overlap is intentional:
        an arm that had to be disjoint from its sibling would need a term whose
        only job is avoiding the sibling, and that term would be untested.
        """
        assert _majority("Amanda Anisimova") is True
        assert _shipped_arms_withhold("Amanda Anisimova") is True


class TestTheBoardAsAWhole:
    def test_the_shipped_arms_reproduce_production(self):
        """`prices_withheld: 3`, served 2026-09-23. The fixture is a replay."""
        withheld = {n for n, *_ in AO_2027_WOMENS if _shipped_arms_withhold(n)}
        assert withheld == ALREADY_WITHHELD_BY_SHIPPED_RULES

    def test_the_board_loses_exactly_one_leg(self):
        """🪤 THE CONTROL THAT CAN FAIL — it pins the column, not the specimen.

        A widening that reaches honest longshots (the 33-leg first draft) shows
        up here as a set that is too big, and a rule that stops working shows up
        as one that is too small. The specimen test alone can see neither.
        """
        after = {
            n
            for n, *_ in AO_2027_WOMENS
            if _shipped_arms_withhold(n) or _majority(n)
        }
        assert after == ALREADY_WITHHELD_BY_SHIPPED_RULES | {NEWLY_WITHHELD}

    def test_the_board_still_has_a_price(self):
        """#6846's "no price discovery to show" cost is NOT paid again here."""
        served = [
            p
            for n, p, *_ in AO_2027_WOMENS
            if not (_shipped_arms_withhold(n) or _majority(n))
        ]
        assert len(served) == 5
        assert max(served) == 0.25  # Rybakina, off a real two-sided book


class TestTheVolumeTermIsLoadBearing:
    """The axis CERT-3242 and CERT-3244 were both falsified for missing."""

    def test_a_leg_the_venue_reports_as_traded_keeps_its_price(self):
        """The Congo Republic / Arch Manning class, one venue shape over.

        A trade is independent information while somebody is still making it.
        Muchova's own row, with the ONE column that differs changed.
        """
        assert _majority(NEWLY_WITHHELD, volume=TRADED) is False

    def test_a_venue_we_never_asked_keeps_its_price(self):
        """NULL is "we never looked", not "nobody traded it" (gotcha #53)."""
        assert _majority(NEWLY_WITHHELD, volume=NEVER_ASKED) is False

    def test_a_stale_volume_reading_keeps_its_price(self):
        """The reading must come from our most recent write of the row.

        A writer that advanced the touch-stamp without taking a volume reading
        leaves the stamp behind, and this must not withhold on it — the
        row-relative freshness test that carries no constant.
        """
        stale = (0.00, LAST_SEEN - timedelta(hours=6), LAST_SEEN)
        assert _majority(NEWLY_WITHHELD, volume=stale) is False


class TestTheGates:
    def test_a_graded_row_keeps_its_number(self):
        """A settled board is a RESULT, and settled means settled."""
        assert _majority(NEWLY_WITHHELD, resolution_source="api_settlement") is False

    def test_outside_a_proved_field_nothing_is_withheld(self):
        """#6846's frame. An upper bound is defensible when it is the only
        number in the frame; this rule only speaks about a distribution."""
        assert _majority(NEWLY_WITHHELD, in_field=False) is False

    def test_another_venue_is_never_reached(self):
        _, probability, yes_bid, yes_ask, last_price = BY_NAME[NEWLY_WITHHELD]
        assert (
            price_is_an_unbacked_majority(
                "polymarket",
                None,
                probability,
                yes_bid,
                yes_ask,
                last_price,
                has_trade_evidence=True,
                in_exclusive_field=True,
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
            )
            is False
        )

    def test_an_absent_snapshot_fails_open(self):
        """gotcha #53 at the arm's own boundary: "we never looked" is not
        "it never traded"."""
        _, probability, yes_bid, yes_ask, last_price = BY_NAME[NEWLY_WITHHELD]
        assert (
            price_is_an_unbacked_majority(
                "kalshi",
                None,
                probability,
                yes_bid,
                yes_ask,
                last_price,
                has_trade_evidence=False,
                in_exclusive_field=True,
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
            )
            is False
        )

    def test_a_leg_that_never_traded_is_6846s_arm_not_this_one(self):
        """`last_price` of 0.0 is "never traded". Requiring a positive trade is
        what keeps this arm strictly complementary to the exemption it
        qualifies."""
        _, _, yes_bid, yes_ask, _ = BY_NAME[NEWLY_WITHHELD]
        assert (
            price_is_an_unbacked_majority(
                "kalshi",
                None,
                0.58,
                yes_bid,
                yes_ask,
                0.0,
                has_trade_evidence=True,
                in_exclusive_field=True,
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
            )
            is False
        )


class TestTheCeiling:
    """The bound is argued from the reader, so it is asserted as a boundary."""

    def test_exactly_a_half_is_not_a_majority(self):
        """The comparison is STRICT. A coin flip claims nothing."""
        assert (
            needs_unbacked_majority_evidence(
                "kalshi",
                None,
                UNBID_CLAIM_CEILING,
                0.0000,
                0.7000,
                in_exclusive_field=True,
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
            )
            is False
        )

    def test_a_hair_above_a_half_is(self):
        assert (
            needs_unbacked_majority_evidence(
                "kalshi",
                None,
                UNBID_CLAIM_CEILING + 0.01,
                0.0000,
                0.7000,
                in_exclusive_field=True,
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
            )
            is True
        )

    def test_the_ceiling_is_a_half(self):
        """Pinned so a later edit that 'tunes' it has to say so out loud."""
        assert UNBID_CLAIM_CEILING == 0.50
