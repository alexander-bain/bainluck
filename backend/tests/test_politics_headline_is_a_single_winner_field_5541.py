"""#5541 — a /politics headline market must be a SINGLE-WINNER FIELD.

`_is_headline_market` reads the TITLE, and a title cannot tell "who wins the
2028 Democratic nomination" from "who will announce a presidential run before
2028". Its catch-all arm — 2028 + president — admits both. The prices can tell
them apart with no ground truth at all: a field partitions one contest and sums
to ~100%, a rack of independent binaries sums to many times that.

On production 2026-09-12 the Polymarket slot was held by the rack:

    58335992  "Who will announce Presidential run before 2028?"   73 legs  2274.6%
    112895    "Democratic Presidential Nominee 2028"              46 legs    90.0%

The rack won the outcome-count tiebreak 73-46, because 82 of 112895's 128 rows
are `Person XX` placeholders that `clean_outcomes` strips. Every symptom on the
issue followed from that single substitution, which is why these tests are all
about WHICH MARKET IS CHOSEN rather than about any number downstream of it.

⚠️  SHAPE OF EVERY TEST HERE. A test that only asserts "the rack is not the
headline" passes just as well when NO headline was chosen at all — the
`_is_headline_market` regex is easy to miss by accident in a fixture, and a
`None` headline satisfies the negative. So every case below asserts the
POSITIVE too: the market that should have won, won. Removing
`_is_single_winner_field` from the call site must turn each of these red.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _MAX_FIELD_SUM_PCT,
    _build_presidential,
    _is_headline_market,
    _is_single_winner_field,
)

_NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

_RACK_ID = 58335992
_REAL_POLY_ID = 112895
_REAL_KALSHI_ID = 108445


def _outcome(name: str, prob: float, oid: int):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        probability_change_24h=None, rank=None,
    )


def _market(name, outcomes, *, source, market_id, external_id="kxpres2028"):
    return SimpleNamespace(
        id=market_id, name=name, source=source,
        external_id=external_id, outcomes=outcomes,
    )


def _announce_rack(*, source="polymarket", market_id=_RACK_ID, legs=12, oid0=900):
    """A rack of independent binaries titled like a race.

    Deliberately given MORE legs than the real market in every fixture: the
    rack must be winning the outcome-count tiebreak, or the gate under test is
    never the thing that decided the case and the test proves nothing.
    """
    names = [
        "J.D. Vance", "Ted Cruz", "Ron DeSantis", "Pete Buttigieg",
        "Gavin Newsom", "Kamala Harris", "Jon Ossoff", "Josh Shapiro",
        "Andy Beshear", "Mark Kelly", "Wes Moore", "Rahm Emanuel",
    ][:legs]
    # ~0.85 each, the real shape: every leg is near-certain to ANNOUNCE.
    return _market(
        "Who will announce Presidential run before 2028?",
        [_outcome(n, 0.85, oid0 + i) for i, n in enumerate(names)],
        source=source, market_id=market_id, external_id="798125",
    )


def _real_nomination_market(*, source="polymarket", market_id=_REAL_POLY_ID, oid0=100):
    """The genuine field: mutually exclusive legs summing to 90.0%."""
    legs = [
        ("Alexandria Ocasio-Cortez", 0.1755), ("Jon Ossoff", 0.1615),
        ("Gavin Newsom", 0.1385), ("Kamala Harris", 0.0775),
        ("Josh Shapiro", 0.0635), ("Pete Buttigieg", 0.0565),
        ("Mark Kelly", 0.0290), ("Andy Beshear", 0.0265),
    ]
    return _market(
        "Democratic Presidential Nominee 2028",
        [_outcome(n, p, oid0 + i) for i, (n, p) in enumerate(legs)],
        source=source, market_id=market_id, external_id="30829",
    )


class TestTheRackNeverTakesTheHeadlineSlot:
    """The production substitution, with the tiebreak stacked against us."""

    def test_the_real_nomination_market_wins_against_a_bigger_rack(self):
        rack = _announce_rack(legs=12)          # 12 legs, 1020%
        real = _real_nomination_market()        # 8 legs, 90.0%
        assert len(rack.outcomes) > len(real.outcomes), (
            "fixture must stack the tiebreak against the real market, "
            "or the gate is not what decides this case"
        )

        response, _ = _build_presidential([rack, real], now=_NOW)

        # POSITIVE: a headline was chosen, and it is the right one.
        assert response["poly_market_id"] == _REAL_POLY_ID
        assert response["headline_q"] == "Democratic Presidential Nominee 2028"
        # NEGATIVE: and it is not the rack.
        assert response["poly_market_id"] != _RACK_ID

    def test_a_rack_cannot_put_republicans_in_a_democratic_race(self):
        """#5541's "second, separate defect" is the same defect."""
        response, _ = _build_presidential(
            [_announce_rack(legs=12), _real_nomination_market()], now=_NOW
        )
        names = {c["name"] for c in response["candidates"]}

        # POSITIVE: the real field's candidates are all there.
        assert {"Jon Ossoff", "Alexandria Ocasio-Cortez", "Pete Buttigieg"} <= names
        # NEGATIVE: the rack-only names never entered.
        assert names.isdisjoint({"J.D. Vance", "Ted Cruz", "Ron DeSantis"})

    def test_no_rack_outcome_id_reaches_the_history_map(self):
        """The exact channel that poisoned the sparkline and the chip.

        `outcome_id_map` is what `/api/politics` replays 30 days of
        `FuturesOddsSnapshot` rows through. A rack id in this map is an
        announce-a-run price series drawn on a nomination chart — and
        `change_7d` subtracting across the two is the "+80.7pp at 5%" the
        reader saw.
        """
        rack = _announce_rack(legs=12)
        real = _real_nomination_market()
        _, outcome_id_map = _build_presidential([rack, real], now=_NOW)

        rack_ids = {o.id for o in rack.outcomes}
        real_ids = {o.id for o in real.outcomes}

        # POSITIVE: the real series is mapped, so history is not merely empty.
        assert real_ids <= set(outcome_id_map)
        # NEGATIVE: not one rack id rides along.
        assert not (rack_ids & set(outcome_id_map))

    def test_the_served_probability_is_the_real_price_not_a_rescaled_one(self):
        """A rack trips the >105% normalisation and rescales EVERY candidate.

        With the rack admitted, Ossoff's 16.15% was served as 9.7%. The served
        number is only trustworthy once the rack cannot enter the average.
        """
        response, _ = _build_presidential(
            [_announce_rack(legs=12), _real_nomination_market()], now=_NOW
        )
        by_name = {c["name"]: c for c in response["candidates"]}
        # The field sums to 90.0%, under the 105% trigger, so nothing is
        # rescaled: each served number is the venue's own price back.
        assert by_name["Jon Ossoff"]["merged"] == pytest.approx(16.15, abs=0.06)
        assert by_name["Alexandria Ocasio-Cortez"]["merged"] == pytest.approx(17.55, abs=0.06)
        # And emphatically not the ~9.7 / ~9.1 the rack's 1020% produced.
        assert by_name["Jon Ossoff"]["merged"] > 15.0

    def test_the_kalshi_slot_is_defended_by_the_same_gate(self):
        """Kalshi ships its own rack: "Who will RUN for the ... nomination?"."""
        rack = _announce_rack(
            source="kalshi", market_id=108502, legs=12, oid0=800
        )
        rack.name = "Who will run for the Democratic presidential nomination in 2028?"
        real = _real_nomination_market(
            source="kalshi", market_id=_REAL_KALSHI_ID, oid0=200
        )
        real.name = "2028 Democratic presidential nominee"
        assert len(rack.outcomes) > len(real.outcomes)

        response, _ = _build_presidential([rack, real], now=_NOW)

        assert response["kalshi_market_id"] == _REAL_KALSHI_ID
        assert response["kalshi_market_id"] != 108502

    def test_a_refused_rack_is_still_shown_as_a_side_market(self):
        """Refusing the headline slot must not silently delete the market."""
        rack = _announce_rack(legs=12)
        response, _ = _build_presidential(
            [rack, _real_nomination_market()], now=_NOW
        )
        side_ids = {r["market_id"] for r in response["side_markets"]}
        assert _RACK_ID in side_ids


class TestGenuineFieldsAreNotCollateral:
    """The must-SURVIVE half, always beside a must-be-CUT row."""

    def test_the_noisiest_real_field_measured_on_production_still_headlines(self):
        """"Navajo Nation presidential election winner?" sums to 118.0%.

        It is the highest-summing genuine single-winner field in the whole
        186-market population, and it must keep its slot — paired here with a
        rack that must lose one, so a gate that refused everything (or nothing)
        cannot pass this test.
        """
        noisy = _market(
            "2028 U.S. Presidential Election winner?",
            [
                _outcome("A", 0.40, 300), _outcome("B", 0.33, 301),
                _outcome("C", 0.25, 302), _outcome("D", 0.20, 303),
            ],  # 118.0%
            source="polymarket", market_id=555,
        )
        assert sum(float(o.current_probability) for o in noisy.outcomes) * 100 == pytest.approx(118.0)

        response, _ = _build_presidential(
            [noisy, _announce_rack(legs=12, market_id=_RACK_ID)], now=_NOW
        )
        assert response["poly_market_id"] == 555
        assert response["poly_market_id"] != _RACK_ID

    def test_the_existing_over_105_normalisation_still_has_work_to_do(self):
        """The gate must not make the BR36 normaliser unreachable.

        A field at 118% is admitted (above) and then normalised down to ~100%.
        If the bound were tightened to 105% this assertion would still pass but
        the normaliser would be dead code — so assert the live band directly.
        """
        assert _MAX_FIELD_SUM_PCT > 105.0


class TestTheBoundItself:
    """Anchored on measured production values, not on invented ones."""

    @pytest.mark.parametrize(
        "label,sum_pct,is_field",
        [
            # Genuine single-winner fields, measured 2026-09-12.
            ("Republican Presidential Nominee 2028", 87.1, True),
            ("Democratic Presidential Nominee 2028", 90.0, True),
            ("2028 Democratic presidential nominee", 96.6, True),
            ("US Presidential Elections Winner", 108.7, True),
            ("Navajo Nation presidential election winner?", 118.0, True),
            ("GA-13 Democratic nominee?", 124.1, True),  # highest real field
            # Racks of independent binaries, measured the same day.
            ("Who will Trump endorse first...?", 301.4, False),
            ("Who will run for the 2028 Republican...nomination?", 954.2, False),
            ("Who will run for the Democratic...nomination in 2028?", 1584.8, False),
            ("Who will announce Presidential run before 2028?", 2274.6, False),
        ],
    )
    def test_the_measured_population_lands_on_the_right_side(self, label, sum_pct, is_field):
        outcomes = [_outcome(label, sum_pct / 100.0, 1)]
        assert _is_single_winner_field(outcomes) is is_field, label

    def test_the_bound_separates_rather_than_grazes(self):
        """124.1% is the noisiest real field; 301.4% the mildest rack.

        Both measured on production 2026-09-12 over the full 186-market
        headline-eligible population. The bound must stay inside that empty
        gap: move it below 124.1 and real races lose their headline, above
        301.4 and the racks come back.
        """
        assert 124.1 < _MAX_FIELD_SUM_PCT < 301.4

    def test_the_boundary_is_inclusive(self):
        assert _is_single_winner_field([_outcome("x", 1.50, 1)]) is True
        assert _is_single_winner_field([_outcome("x", 1.51, 1)]) is False

    def test_unpriced_legs_do_not_crash_the_bound(self):
        """`Person XX` placeholders carry NULL probabilities."""
        assert _is_single_winner_field(
            [_outcome("Person AJ", None, 1), _outcome("Jon Ossoff", 0.16, 2)]
        ) is True

    def test_the_title_predicate_still_admits_the_rack_on_its_own(self):
        """Proof the gate is load-bearing and not shadowed by the regex.

        If `_is_headline_market` ever started refusing this title by itself,
        every test above would pass for the wrong reason.
        """
        assert _is_headline_market("who will announce presidential run before 2028?") is True
        assert _is_headline_market(
            "who will run for the democratic presidential nomination in 2028?"
        ) is True
