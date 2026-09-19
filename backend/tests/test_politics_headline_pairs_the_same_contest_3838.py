"""#3838 — the two /politics headline legs must settle the SAME race.

#5541 taught the headline slot to refuse a rack of independent binaries by
reading the prices: a field partitions one contest and sums to ~100%, a rack
sums to many times that. That gate works and is not touched here. What it
cannot do is ask **which** contest a coherent field partitions, and that is
this issue.

Measured on production 2026-09-19, the markets reaching the poly slot for the
`presidential` theme, after `clean_outcomes` strips the `Person XX` rows:

    112897  "Presidential Election Winner 2028"       53 legs  90.2%   general
    112895  "Democratic Presidential Nominee 2028"    52 legs  95.2%   dem_primary
    108445  "2028 Democratic presidential nominee"    48 legs  96.5%   dem_primary (kalshi)

Both poly fields clear the 150% bound, so `_is_single_winner_field` passes both
and the slot fell to `len(outcomes)` — **the general election won 53 to 52**.
The card kept Kalshi's Democratic-primary title and was filled with the
general-election field, so the reader was told JD Vance led the 2028
*Democratic* nomination at 21.1%, with Rubio 5th and Donald Trump on the same
ladder.

⚠️  THE MARGIN IS ONE OUTCOME, AND IT MOVES. Both counts change whenever
Polymarket fills in a placeholder name, so the slot flips between two different
questions on its own: #3838 was filed against partner `58335992` (the
announce-a-run rack), and by the time it was re-shopped the partner was
`112897`. That is why the tests below pin the pairing RULE and not a winner —
a test that only says "112897 did not win" passes again the moment the counts
cross back.

⚠️  SHAPE OF EVERY TEST HERE, inherited from
`test_politics_headline_is_a_single_winner_field_5541.py`: a test that only
asserts the wrong market lost also passes when NO headline was chosen at all,
and a `None` headline satisfies every negative. So each case asserts the
POSITIVE — the market that should have won, won — alongside the negative.
Reverting `_contest_key` out of the call site must turn these red.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _build_presidential,
    _contest_key,
    _is_headline_market,
    _is_single_winner_field,
)

_NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)

_KALSHI_DEM_ID = 108445      # "2028 Democratic presidential nominee"
_POLY_DEM_ID = 112895        # "Democratic Presidential Nominee 2028"
_POLY_GENERAL_ID = 112897    # "Presidential Election Winner 2028"


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


# The three real fields, at production's shape. Leg counts are deliberately
# ordered general > poly-dem > kalshi-dem so the size tiebreak is always
# pointing at the WRONG market; if a fixture ever stops doing that the gate
# under test is not what decided the case.
_DEM_LEGS = [
    ("Alexandria Ocasio-Cortez", 0.155), ("Jon Ossoff", 0.165),
    ("Gavin Newsom", 0.135), ("Kamala Harris", 0.081),
    ("Josh Shapiro", 0.047), ("Pete Buttigieg", 0.052),
    ("Mark Kelly", 0.042), ("Andy Beshear", 0.030),
]

# The general election: BOTH parties on one ladder. These Republican names are
# the reader-visible symptom — they are real prices, on a real, coherent
# market, that simply answers a different question.
_GENERAL_LEGS = [
    ("JD Vance", 0.211), ("Alexandria Ocasio-Cortez", 0.132),
    ("Jon Ossoff", 0.116), ("Marco Rubio", 0.097),
    ("Gavin Newsom", 0.076), ("Kamala Harris", 0.048),
    ("Ron DeSantis", 0.018), ("Donald Trump", 0.009),
    ("Tucker Carlson", 0.016), ("Josh Shapiro", 0.031),
]

_REPUBLICAN_ONLY = {"JD Vance", "Marco Rubio", "Ron DeSantis", "Donald Trump",
                    "Tucker Carlson"}


def _kalshi_dem(*, market_id=_KALSHI_DEM_ID):
    return _market(
        "2028 Democratic presidential nominee",
        [_outcome(n, p, 100 + i) for i, (n, p) in enumerate(_DEM_LEGS[:6])],
        source="kalshi", market_id=market_id, external_id="KXPRESNOMD-28",
    )


def _poly_dem(*, market_id=_POLY_DEM_ID):
    return _market(
        "Democratic Presidential Nominee 2028",
        [_outcome(n, p, 200 + i) for i, (n, p) in enumerate(_DEM_LEGS)],
        source="polymarket", market_id=market_id, external_id="30829",
    )


def _poly_general(*, market_id=_POLY_GENERAL_ID):
    return _market(
        "Presidential Election Winner 2028",
        [_outcome(n, p, 300 + i) for i, (n, p) in enumerate(_GENERAL_LEGS)],
        source="polymarket", market_id=market_id, external_id="31552",
    )


class TestTheFixtureIsTheProductionCase:
    """If these drift, every test below is testing something else."""

    def test_all_three_fields_are_coherent_so_5541_cannot_separate_them(self):
        for m in (_kalshi_dem(), _poly_dem(), _poly_general()):
            assert _is_single_winner_field(m.outcomes), (
                f"{m.name} must PASS the #5541 bound — this issue only exists "
                "for fields that gate cannot tell apart"
            )

    def test_all_three_titles_reach_the_headline_slot(self):
        for m in (_kalshi_dem(), _poly_dem(), _poly_general()):
            assert _is_headline_market(m.name.lower()), m.name

    def test_the_size_tiebreak_points_at_the_wrong_market(self):
        assert len(_poly_general().outcomes) > len(_poly_dem().outcomes), (
            "the general election must be the LARGER field, or the old "
            "`len(outcomes)` rule would have picked correctly by accident"
        )


class TestContestKey:
    @pytest.mark.parametrize("title,expected", [
        ("2028 democratic presidential nominee", "dem_primary"),
        ("democratic presidential nominee 2028", "dem_primary"),
        ("2028 republican presidential nominee", "gop_primary"),
        ("republican presidential nominee 2028", "gop_primary"),
        ("presidential election winner 2028", "general"),
        ("who will win the 2028 us presidential election?", "general"),
        ("next president of the united states", "general"),
    ])
    def test_titles_classify(self, title, expected):
        assert _contest_key(title) == expected

    def test_a_primary_is_never_the_general(self):
        assert _contest_key("democratic presidential nominee 2028") != _contest_key(
            "presidential election winner 2028"
        )

    def test_the_two_primaries_are_not_each_other(self):
        assert _contest_key("2028 democratic presidential nominee") != _contest_key(
            "2028 republican presidential nominee"
        )


class TestThePairingRequiresTheSameContest:
    """The production case: all three markets in, as the route sees them."""

    def test_the_poly_partner_is_the_democratic_market_not_the_general(self):
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general(), _poly_dem()], now=_NOW
        )
        # POSITIVE: a partner was chosen, and it settles the same race.
        assert response["poly_market_id"] == _POLY_DEM_ID
        assert response["kalshi_market_id"] == _KALSHI_DEM_ID
        assert response["headline_q"] == "2028 Democratic presidential nominee"
        # NEGATIVE: the general election did not take the slot.
        assert response["poly_market_id"] != _POLY_GENERAL_ID

    def test_no_republican_enters_the_democratic_nomination_ladder(self):
        """The sentence a reader was being told, as an assertion."""
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general(), _poly_dem()], now=_NOW
        )
        names = {c["name"] for c in response["candidates"]}

        # POSITIVE: the Democratic field is actually on the card.
        assert {"Jon Ossoff", "Alexandria Ocasio-Cortez", "Gavin Newsom"} <= names
        # NEGATIVE: and nobody arrived from the general election.
        assert names.isdisjoint(_REPUBLICAN_ONLY)

    def test_vance_is_not_the_leading_democrat(self):
        """The headline symptom, pinned as its own case.

        `candidates` is sorted by `merged` descending, so element 0 IS the name
        the card leads with — the 21.1% that outranked every real Democrat.
        """
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general(), _poly_dem()], now=_NOW
        )
        assert response["candidates"], "the card must still have a ladder"
        assert response["candidates"][0]["name"] not in _REPUBLICAN_ONLY
        assert response["candidates"][0]["party"] == "D"

    def test_the_blend_is_preserved_not_refused(self):
        """Fail-closed would have been the cheap fix; it is not the right one.

        A correct partner exists, so the card keeps two sources. If this ever
        reads False the fix has degraded into 'refuse to blend' and the reader
        quietly lost the Polymarket leg.
        """
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general(), _poly_dem()], now=_NOW
        )
        assert response["has_dual_source"] is True
        blended = [c for c in response["candidates"]
                   if c["kalshi"] is not None and c["poly"] is not None]
        assert blended, "at least one candidate must carry both legs"

    def test_no_general_election_outcome_id_reaches_the_history_map(self):
        """The channel that draws the sparkline and computes `change_7d`.

        `outcome_id_map` is what `/api/politics` replays snapshot rows through.
        A general-election id in this map is a 'wins the presidency' price
        series drawn on a nomination chart.
        """
        general = _poly_general()
        _, outcome_id_map = _build_presidential(
            [_kalshi_dem(), general, _poly_dem()], now=_NOW
        )
        general_ids = {o.id for o in general.outcomes}
        assert not (general_ids & set(outcome_id_map)), (
            "a general-election outcome id reached the nomination history map"
        )


class TestTheRejectedContenderIsDemotedNotDropped:
    """A contender that loses the slot used to be dropped on the floor.

    That is why 112895 — the CORRECT Democratic market — was not merely
    unpaired on production, it was absent from the page altogether. Whichever
    market loses, it is still a real presidential market and still belongs
    somewhere the reader can reach.
    """

    def test_the_general_election_survives_as_a_side_market(self):
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general(), _poly_dem()], now=_NOW
        )
        side_ids = {r.get("market_id") or r.get("id") for r in response["side_markets"]}
        assert _POLY_GENERAL_ID in side_ids, (
            f"the rejected contender vanished; side markets were {side_ids}"
        )

    def test_the_chosen_headlines_are_not_also_side_markets(self):
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general(), _poly_dem()], now=_NOW
        )
        side_ids = {r.get("market_id") or r.get("id") for r in response["side_markets"]}
        assert _POLY_DEM_ID not in side_ids
        assert _KALSHI_DEM_ID not in side_ids


class TestWhenNoPartnerSettlesTheSameRace:
    """The general election alone must not be pressed into service."""

    def test_an_unmatched_poly_headline_does_not_take_the_slot(self):
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general()], now=_NOW
        )
        # POSITIVE: the Kalshi card still renders, titled honestly.
        assert response["kalshi_market_id"] == _KALSHI_DEM_ID
        assert response["headline_q"] == "2028 Democratic presidential nominee"
        assert response["candidates"], "the Kalshi ladder must still be served"
        # NEGATIVE: no cross-race blend, and it says so.
        assert response["poly_market_id"] is None
        assert response["has_dual_source"] is False

    def test_the_unmatched_market_still_reaches_the_reader(self):
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general()], now=_NOW
        )
        side_ids = {r.get("market_id") or r.get("id") for r in response["side_markets"]}
        assert _POLY_GENERAL_ID in side_ids

    def test_still_no_republicans_when_there_is_no_partner(self):
        response, _ = _build_presidential(
            [_kalshi_dem(), _poly_general()], now=_NOW
        )
        names = {c["name"] for c in response["candidates"]}
        assert names.isdisjoint(_REPUBLICAN_ONLY)
        assert {"Jon Ossoff", "Alexandria Ocasio-Cortez"} <= names


class TestBehaviourThatMustNotChange:
    def test_a_poly_only_theme_still_headlines_from_polymarket(self):
        """With no Kalshi market the poly headline sets the contest, as before."""
        response, _ = _build_presidential([_poly_general()], now=_NOW)
        assert response["poly_market_id"] == _POLY_GENERAL_ID
        assert response["headline_q"] == "Presidential Election Winner 2028"
        assert response["kalshi_market_id"] is None
        assert response["has_dual_source"] is False

    def test_a_poly_only_theme_picks_the_largest_within_one_contest(self):
        """The size rule is not deleted — it is scoped to a single race."""
        response, _ = _build_presidential([_poly_dem(), _poly_general()], now=_NOW)
        # Both are poly; the larger (general, 10 legs) sets and wins the contest.
        assert response["poly_market_id"] == _POLY_GENERAL_ID
        side_ids = {r.get("market_id") or r.get("id") for r in response["side_markets"]}
        assert _POLY_DEM_ID in side_ids

    def test_two_kalshi_markets_in_one_contest_still_take_the_largest(self):
        small = _kalshi_dem(market_id=999001)
        big = _market(
            "2028 Democratic presidential nominee",
            [_outcome(n, p, 400 + i) for i, (n, p) in enumerate(_DEM_LEGS)],
            source="kalshi", market_id=999002, external_id="KXPRESNOMD-28",
        )
        assert len(big.outcomes) > len(small.outcomes)
        response, _ = _build_presidential([small, big], now=_NOW)
        assert response["kalshi_market_id"] == 999002

    def test_a_republican_primary_pairs_with_the_republican_primary(self):
        """The rule is symmetric — it is not a special case for Democrats."""
        k_gop = _market(
            "2028 Republican presidential nominee",
            [_outcome(n, p, 500 + i) for i, (n, p) in enumerate(
                [("JD Vance", 0.45), ("Marco Rubio", 0.20), ("Ron DeSantis", 0.12)]
            )],
            source="kalshi", market_id=108444, external_id="KXPRESNOMR-28",
        )
        p_gop = _market(
            "Republican Presidential Nominee 2028",
            [_outcome(n, p, 600 + i) for i, (n, p) in enumerate(
                [("JD Vance", 0.47), ("Marco Rubio", 0.18),
                 ("Ron DeSantis", 0.10), ("Tucker Carlson", 0.04)]
            )],
            source="polymarket", market_id=112900, external_id="31875",
        )
        response, _ = _build_presidential([k_gop, _poly_general(), p_gop], now=_NOW)
        assert response["kalshi_market_id"] == 108444
        assert response["poly_market_id"] == 112900
        assert response["has_dual_source"] is True


class TestTheProductionMarginExactly:
    """53 to 52. The real numbers, because the real margin is one outcome."""

    @staticmethod
    def _field(title, n_legs, *, source, market_id, oid0):
        # n legs summing to ~0.90 — coherent, so #5541's bound passes it.
        #
        # NOT "Candidate NNN": that matches `GARBAGE_OUTCOME_RE`, so
        # `clean_outcomes` strips every leg, the field drops under the 3-outcome
        # floor and NO headline is chosen — which passes every negative
        # assertion in this file while proving nothing. It cost a red run here,
        # and it is the same stripping that makes the real 53-52 margin move.
        per = 0.90 / n_legs
        return _market(
            title,
            [_outcome(f"Contender {i:03d}", per, oid0 + i) for i in range(n_legs)],
            source=source, market_id=market_id,
        )

    def test_the_democratic_partner_wins_despite_losing_53_to_52(self):
        general = self._field(
            "Presidential Election Winner 2028", 53,
            source="polymarket", market_id=_POLY_GENERAL_ID, oid0=10000,
        )
        dem = self._field(
            "Democratic Presidential Nominee 2028", 52,
            source="polymarket", market_id=_POLY_DEM_ID, oid0=20000,
        )
        assert len(general.outcomes) - len(dem.outcomes) == 1

        response, _ = _build_presidential([_kalshi_dem(), general, dem], now=_NOW)

        assert response["poly_market_id"] == _POLY_DEM_ID
        assert response["poly_market_id"] != _POLY_GENERAL_ID
