"""The golf winner-field classifier — UX-P070 (#1546).

WHAT WENT WRONG, IN ONE SENTENCE
--------------------------------
`_NON_WINNER_MARKET_RE` decides which golf markets are outright-winner fields, it was
written by reading Kalshi's market titles, and it therefore mis-classified Polymarket's
titles in BOTH directions at once — dropping Polymarket's real winner market and
admitting its round-leader market in its place.

MEASURED ON PRODUCTION, 2026-08-13, during the FedExCup Playoffs opener
-----------------------------------------------------------------------
`GET /api/event/event:golf:fedex-st-jude-championship` (a `live` build, not the mirror)
ranked **Hideki Matsuyama the tournament favourite at 0.278** — nearly double Scottie
Scheffler — and the 69-golfer field summed to **1.223**.

The arithmetic was exact: ``(0.5 + 0.056) / 2 == 0.278``.

* `0.056` is DataGolf's model price for Matsuyama.
* `0.5` came from market 58689039, **"PGA Tour: FedEx St. Jude Championship Second
  Round Leader"**, whose single outcome carried ``bid=0.01 / ask=1.00`` — an empty
  order book, whose midpoint is 0.5 because nobody is quoting, not because anyone
  thinks it is a coin flip (gotcha #19).

Three failures had to line up, and all three are pinned below:

1. **UNDER-exclusion.** The round-leader arm enumerated Kalshi's digit phrasing
   (``Round \\d+ Leader``) plus exactly one hand-patched word (``first round leader``).
   Polymarket writes ordinal WORDS, so "Second/Third/Final Round Leader" classified as
   an outright winner market. Census: 13 such markets, 8 open, 5 priced.
2. **OVER-exclusion.** ``\\btour\\b.*\\bwinner\\b`` — meant for the Kalshi prop "Tour of
   Winner" — swallowed every tour-PREFIXED title: "PGA Tour: … Winner", "DP World
   Tour: … Winner", "Korn Ferry Tour: … Winner". Census: 23 golf markets dropped
   (20 resolved holding 1,957 priced outcomes), and **zero** golf true positives.
3. **The amplifier.** `_dedup_winner_markets` elects, per source, the surviving
   candidate with the most golfer outcomes. With (2) deleting the real winner market
   and (1) admitting the round-leader market, Polymarket's elected "winner market" for
   the tournament BECAME its Second Round Leader market.

THE PART WORTH REMEMBERING: the correct pattern already existed in this repo. #955 hit
the same over-breadth, derived the right prop phrasing, and wrote it into
`app.utils.golf_evolution_market.NON_CONTENDER_WINNER_RE` — with a comment naming this
exact trap and a test asserting "PGA Tour: U.S. Open Winner" survives. It was applied to
the CHART consumer only. Two copies of one rule disagreed for months and the aggregation
kept the broken half; `test_the_two_copies_of_this_rule_now_agree` is the ratchet.
"""

import re

import pytest

from app.routes.golf import (
    _NON_WINNER_MARKET_RE,
    _ORDINAL_WORD,
    _golf_winner_renorm_factor,
    _is_placeholder_price,
    _kalshi_untraded_mid,
)
from app.utils.golf_evolution_market import NON_CONTENDER_WINNER_RE


# --------------------------------------------------------------------------
# Real production market names, transcribed from the census run 2026-08-13.
# Held as data rather than prose so the suite grades the actual corpus that
# broke, not a paraphrase of it.
# --------------------------------------------------------------------------

# Every ordinal-word round-leader market in futures_markets (the 13 that leaked).
LEAKING_ROUND_LEADERS = [
    "The Masters 2026: Second Round Leader",
    "The Masters 2026: Third Round Leader",
    "2026 U.S. Open: Third Round Leader",
    "2026 U.S. Open: Second Round Leader",
    "PGA Tour: Wyndham Championship Third Round Leader",
    "LPGA: Portland Classic Third Round Leader",
    "DP World Tour: Danish Golf Championship Third Round Leader",
    "LPGA: Portland Classic Second Round Leader",
    "PGA Tour: FedEx St. Jude Championship Second Round Leader",
    "DP World Tour: Danish Golf Championship Second Round Leader",
    "PGA Tour: FedEx St. Jude Championship Third Round Leader",
    "Korn Ferry Tour: Albertsons Boise Open Second Round Leader",
    "Korn Ferry Tour: Albertsons Boise Open Third Round Leader",
]

# Kalshi's digit phrasing — these were ALREADY excluded and must stay excluded.
DIGIT_ROUND_LEADERS = [
    "FedEx St. Jude Championship End of Round 1 Leader",
    "FedEx St. Jude Championship End of Round 2 Leader",
    "FedEx St. Jude Championship End of Round 3 Leader",
]

# Real outright-winner fields that the broad `tour .* winner` was deleting.
TOUR_PREFIXED_WINNER_FIELDS = [
    "PGA Tour: FedEx St. Jude Championship Winner",
    "DP World Tour: Danish Golf Championship Winner",
    "Korn Ferry Tour: Albertsons Boise Open Winner",
    "PGA Tour: Wyndham Championship Winner",
    "PGA Tour: U.S. Open Winner",
]

# Real winner fields that were never affected — the control group. If a change to the
# pattern moves any of these, it has done something other than what it claims.
UNAFFECTED_WINNER_FIELDS = [
    "FedEx St. Jude Championship - Winner",
    "FedEx St. Jude Championship Winner",
    "The Masters 2026 Winner",
    "2026 U.S. Open: Winner",
    "LPGA: Portland Classic Winner",
]

# Genuine winner-ATTRIBUTE props. These must STAY excluded — narrowing the pattern
# must not be achieved by simply deleting its job.
WINNER_ATTRIBUTE_PROPS = [
    "Tour of Winner",
    "Tour of the Winner",
    "Country of Winner",
    "Region of the Winner",
    "2026 U.S. Open: Winner Nationality",
    "Winner's Tour",
    "Winning Score",
    "Margin of Victory",
]


class TestRoundLeaderExclusionIsOrdinalComplete:
    """(1) — the under-exclusion that put a round-2 price in a winner field."""

    @pytest.mark.parametrize("name", LEAKING_ROUND_LEADERS)
    def test_every_ordinal_word_round_leader_is_excluded(self, name):
        assert _NON_WINNER_MARKET_RE.search(name), name

    @pytest.mark.parametrize("name", DIGIT_ROUND_LEADERS)
    def test_kalshi_digit_phrasing_still_excluded(self, name):
        assert _NON_WINNER_MARKET_RE.search(name), name

    @pytest.mark.parametrize("word", _ORDINAL_WORD.split("|"))
    def test_ordinal_matrix_both_phrasings(self, word):
        """Mechanical rather than remembered.

        The bug was an enumeration that was complete for one source and silently
        partial for another, so the guard has to be a LOOP over the enumeration —
        not another hand-written list that can go partial the same way.
        """
        assert _NON_WINNER_MARKET_RE.search(f"Tournament {word.title()} Round Leader")
        assert _NON_WINNER_MARKET_RE.search(f"Tournament Round {word.title()} Leader")

    @pytest.mark.parametrize("n", [1, 2, 3, 4])
    def test_digit_and_numeral_matrix_both_phrasings(self, n):
        suffix = {1: "st", 2: "nd", 3: "rd", 4: "th"}[n]
        assert _NON_WINNER_MARKET_RE.search(f"Tournament Round {n} Leader")
        assert _NON_WINNER_MARKET_RE.search(f"Tournament {n}{suffix} Round Leader")

    def test_the_specimen(self):
        """The exact row that made Matsuyama the favourite."""
        assert _NON_WINNER_MARKET_RE.search(
            "PGA Tour: FedEx St. Jude Championship Second Round Leader"
        )


class TestTourPrefixedWinnerFieldsSurvive:
    """(2) — the over-exclusion that deleted the market that should have won."""

    @pytest.mark.parametrize("name", TOUR_PREFIXED_WINNER_FIELDS)
    def test_tour_prefixed_winner_field_is_kept(self, name):
        assert not _NON_WINNER_MARKET_RE.search(name), name

    @pytest.mark.parametrize("name", UNAFFECTED_WINNER_FIELDS)
    def test_control_group_unmoved(self, name):
        assert not _NON_WINNER_MARKET_RE.search(name), name

    @pytest.mark.parametrize("name", WINNER_ATTRIBUTE_PROPS)
    def test_winner_attribute_props_still_excluded(self, name):
        assert _NON_WINNER_MARKET_RE.search(name), name

    def test_the_pattern_is_not_broad_again(self):
        """A ratchet on the SHAPE, not just the outcomes.

        `tour .* winner` is a natural thing to write and it reads as correct. The
        instant it comes back, every tour-prefixed Polymarket field silently vanishes
        from the blend again — and nothing else in the suite would notice, because the
        symptom is a market that is ABSENT.
        """
        assert r"\btour\b.*\bwinner\b" not in _NON_WINNER_MARKET_RE.pattern
        assert r"\bcountry\b.*\bwinner\b" not in _NON_WINNER_MARKET_RE.pattern


class TestTheTwoCopiesOfThisRuleAgree:
    """#1620, the drift this lane keeps filing — here it had already caused the bug."""

    @pytest.mark.parametrize(
        "name", TOUR_PREFIXED_WINNER_FIELDS + UNAFFECTED_WINNER_FIELDS
    )
    def test_a_real_winner_field_is_kept_by_BOTH_consumers(self, name):
        """The chart path got this right in #955; the aggregation path did not.

        A real field must survive both, or the page and its chart disagree about what
        the tournament's winner market even is.
        """
        assert not _NON_WINNER_MARKET_RE.search(name), f"aggregation drops {name}"
        assert not NON_CONTENDER_WINNER_RE.search(name), f"chart drops {name}"

    @pytest.mark.parametrize("name", ["Tour of Winner", "Country of Winner", "Winner's Tour"])
    def test_a_winner_attribute_prop_is_dropped_by_BOTH_consumers(self, name):
        assert _NON_WINNER_MARKET_RE.search(name), f"aggregation keeps {name}"
        assert NON_CONTENDER_WINNER_RE.search(name), f"chart keeps {name}"


class TestRenormFactorContract:
    """(3b) — the docstring that read as a second line of defence that did not exist."""

    def test_a_one_outcome_round_leader_is_NOT_stopped_here(self):
        """Pinning the REAL behaviour, deliberately.

        The old docstring said round-leader markets "return None". They do not — the
        name-blind `prob_sum <= 1.5` early return fires first. This test exists so the
        next reader learns the true contract from the suite instead of re-deriving it
        after a production incident: exclusion is the CALLER's job.
        """
        assert (
            _golf_winner_renorm_factor(
                "PGA Tour: FedEx St. Jude Championship Second Round Leader", 1, 0.5
            )
            == 1.0
        )

    def test_it_still_renormalizes_a_real_independent_binary_field(self):
        factor = _golf_winner_renorm_factor("The Masters 2026 Winner", 90, 2.5)
        assert factor is not None and abs(factor - 0.4) < 1e-9

    def test_it_still_declines_a_high_summing_participation_market(self):
        assert _golf_winner_renorm_factor("Masters: Make the Cut", 90, 45.0) is None


class _Outcome:
    def __init__(self, prob, bid=None, ask=None):
        self.current_probability = prob
        self.current_yes_bid = bid
        self.current_yes_ask = ask


class TestPlaceholderPrice:
    """The safety half of the tour-prefix fix — see `_is_placeholder_price`."""

    def test_kalshi_untraded_mid_unchanged(self):
        assert _is_placeholder_price(_Outcome(0.5), "kalshi") is True

    def test_kalshi_untraded_mid_unchanged_even_with_a_book(self):
        """Bit-for-bit: the Kalshi arm never consults the book, and must not start."""
        assert _is_placeholder_price(_Outcome(0.5, 0.49, 0.51), "kalshi") is True

    def test_kalshi_real_price_kept(self):
        assert _is_placeholder_price(_Outcome(0.30, 0.29, 0.31), "kalshi") is False

    def test_the_fedex_row_empty_book_is_skipped(self):
        """bid=0.01 / ask=1.00 — the actual stored values on outcome 58689039."""
        assert _is_placeholder_price(_Outcome(0.5, 0.01, 1.00), "polymarket") is True

    def test_polymarket_real_book_kept(self):
        assert _is_placeholder_price(_Outcome(0.11, 0.01, 0.21), "polymarket") is False

    def test_missing_book_FAILS_OPEN(self):
        """Absence is not a reading (gotcha #53).

        A NULL bid/ask means we were never told, which is a different fact from
        "nobody is quoting". Skipping on absence would silently delete every source
        that does not publish a book.
        """
        assert _is_placeholder_price(_Outcome(0.5), "polymarket") is False

    def test_datagolf_model_untouched(self):
        assert _is_placeholder_price(_Outcome(0.056), "datagolf") is False

    def test_unpriced_outcome(self):
        assert _is_placeholder_price(_Outcome(None, 0.01, 1.0), "polymarket") is False

    def test_the_rule_is_monotone_over_the_old_one(self):
        """Over-suppression is the direction that costs a reader real information.

        Everything the old Kalshi-only rule skipped is still skipped, so the new arm
        can only ADD — never restore a skip into a price, and never remove one.
        """
        for prob in (0.0, 0.03, 0.5, 0.97, 1.0):
            for bid, ask in ((None, None), (0.01, 1.0), (0.4, 0.6)):
                old = _kalshi_untraded_mid("kalshi", prob)
                new = _is_placeholder_price(_Outcome(prob, bid, ask), "kalshi")
                assert new or not old, f"regressed a skip at {prob} {bid}/{ask}"


class TestOrdinalSourceIsSharedNotRetyped:
    def test_the_ordinal_list_is_one_definition(self):
        """The fix must not be a second hand-written list beside the first."""
        assert _ORDINAL_WORD in _NON_WINNER_MARKET_RE.pattern
        assert re.compile(_ORDINAL_WORD)  # compiles standalone
