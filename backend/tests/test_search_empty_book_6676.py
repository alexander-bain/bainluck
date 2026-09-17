"""A SEARCH CARD STOPS PRINTING A PRICE NO BOOK STANDS BEHIND. #6676, search half.

═══ WHAT A READER SAW ═══

`GET /api/events/search?q=lakers`, production, 2026-09-17. The card for market
**57777176** *NBA: Steph Curry Next Team* (polymarket, open) served five rungs:

    Golden State Warriors   0.74   on 0.52/0.96      <- real
    Brooklyn Nets           0.48   on 0.01/0.95      <- phantom
    Atlanta Hawks           0.48   on 0.01/0.95      <- phantom
    Phoenix Suns            0.48   on 0.01/0.95      <- phantom
    Chicago Bulls           0.48   on 0.01/0.95      <- phantom

Four mutually exclusive teams at the identical manufactured number. Each 0.48 is
the midpoint of a quote that bounds nothing — a penny bid against a 95c ask — and
the payload carries no bid/ask, so the reader has no way to tell those four from
the 0.74 above them. Fifteen of that market's thirty legs carry honest prices and
none of them reached the card: a phantom sits at ~0.50 by construction, which
outranks every real longshot in the `[:limit]` slice.

═══ THE POPULATION, MEASURED BEFORE THE FIX WAS WRITTEN ═══

Replaying 29 real queries against production `/api/events/search` and joining
every served leg back to its stored book columns by id
(`artifacts-417/size_6676_search.py`, read-only):

    served legs, distinct                        690   across 217 markets
      of which carry a two-sided book            656
      of which are an empty book's midpoint       29   ← 4.2%, this ship
    served legs in the 0.40-0.60 band ON A REAL
      book — the control that must SURVIVE       124

and the table behind it: **3,081 class legs on 1,803 open markets**, all
categories. A bare "0 of N served" would prove nothing on its own — the issue's
own author measured 0/20 three times before any fix existed — so the ratio and
the surviving control are both stated.

Card level, of the 217 served markets:

    lose SOME rungs, real ones promoted            4   e.g. 57777176, 61174927
    every priced leg is class -> card withdraws   15   e.g. 61193385, 61214687

Table-wide, of 25,376 open markets holding outcome rows: **1,198** are priced
only by empty books (1,193 polymarket, 1,117 tier 5), against the 612 that
#6327's withdrawal already takes today.

═══ THE RULE IS NOT NEW, AND SEARCH WAS THE HOLDOUT ═══

`is_empty_book_midpoint` is #5247's shipped predicate with its own measured
constants. `routes/events.py` has run it at the `game-markets` call site since
then; `routes/futures.py` got it for the grouped feed in `24660582f`. Three
reader surfaces draw these same rows, and the search serializer was the one that
still disagreed about whether they have a price — the same sentence
`_futures_market_has_no_outcome_rows` writes about #3412, and the same class
("a shipped fix's guard pins ONE component, sibling surfaces keep the bug").

═══ WHAT THIS SHIP DELIBERATELY DOES NOT DO ═══

✅ **The promoted rung was #5333's, and #5333 landed.** On *Lions vs. Bills -
Player Props* the four legs dropped here were replaced by `0.505 on 0.03/0.97`
rows — the identical shape one cent outside the then-0.02 `EMPTY_BOOK_MAX_BID`.
The bound is 0.05 on its own measurement now, so those are dropped too and
`TestTheBounds` records the flip. No constant moves in THIS file either way; it
pins that the shared one has not been moved here by accident.

* **Read-side only** (gotcha #21). Nothing rewrites a stored price; the WRITER
  half is #6676's other end in `tasks/polymarket.py`.
* **A leg, not a market**, at the filter — a props market carries real lines
  beside its unpriced ones. The market-level withdrawal is a separate predicate
  over a separately measured population.
* **The typeahead keeps name-reachability.** `_futures_card_has_no_answer` is
  deliberately never asked on that path (#4723's control row); the dropdown
  simply stops carrying phantom rungs, exactly as #6327 left it.

═══ WHY THESE TESTS ARE RED-FIRSTED BY MUTATION ═══

Every unit test below builds its own outcome, so all of them would pass against
a route that never called the guard. The guard's placement — before the sort,
the slice and the normalization — is the property that makes it a fix, and only
a mutation can pin it. MEASURED, six mutants, six killed — this file alone, and
in brackets with its two siblings (`..._3412.py`, `..._6327.py`):

    M1  call site deleted from the builder       -> 10 fail
    M2  drop moved AFTER the [:limit] slice      ->  3 fail   the promotion class
    M3  `is_fabricated_midpoint` substituted     -> 10 fail   0.0005 misses the skew 10x
    M4  withdrawal predicate `all()` -> `any()`  ->  1 fail   a real leg would withdraw
    M5  withdrawal dropped from the union        ->  1 [2] fail
    M6  `bool(priced)` guard removed             ->  1 fail   adopts #3412's population

M4, M5 and M6 are killed by ONE test each, and each of those tests exists for
that mutant by name — thin, and reported rather than padded. The route-level
half is `tests/integration/test_route_search_withholds_empty_book_6676.py`,
red-firsted against master's own source at 4 failed / 5 passed.
"""

import pytest

from app.routes.events import (
    _build_search_top_outcomes,
    _format_futures_for_search,
    _futures_card_has_no_answer,
    _futures_market_is_wholly_unpriced,
    _futures_market_prices_only_empty_books,
    _leg_prices_an_empty_book,
)


class _Outcome:
    """The attributes the search builder reads off an ORM outcome row."""

    def __init__(self, oid, name="Leg", prob=None, bid=None, ask=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = bid
        self.current_yes_ask = ask
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}"
        self.is_winner = False


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 57777176)
        self.name = kw.get("name", "NBA: Steph Curry Next Team")
        self.sport = None
        self.category = "basketball"
        self.llm_sport_category = "basketball_nba"
        self.market_tier = kw.get("market_tier", 1)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "polymarket")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", True)


#: Market 57777176 as production served it, stored values, 2026-09-17. The four
#: phantoms and the one real rung that shared the card with them, plus the honest
#: legs underneath that the slice never reached.
def _curry_market():
    return _Market(
        [
            _Outcome(214465500, "Golden State Warriors", 0.74, 0.52, 0.96),
            _Outcome(214465539, "Brooklyn Nets", 0.48, 0.01, 0.95),
            _Outcome(214465537, "Atlanta Hawks", 0.48, 0.01, 0.95),
            _Outcome(214465560, "Phoenix Suns", 0.48, 0.01, 0.95),
            _Outcome(214465541, "Chicago Bulls", 0.48, 0.01, 0.95),
            _Outcome(214465570, "San Antonio Spurs", 0.25, 0.01, 0.49),
            _Outcome(214465571, "Charlotte Hornets", 0.205, 0.01, 0.40),
            _Outcome(214465572, "Cleveland Cavaliers", 0.205, 0.01, 0.40),
        ]
    )


# ---------------------------------------------------------------------------
# 1. The specimen, in the direction it actually failed.
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_four_teams_stop_sharing_one_manufactured_number(self):
        top = _build_search_top_outcomes(_curry_market(), limit=5, lean=False)
        names = [o["name"] for o in top]

        for phantom in ("Brooklyn Nets", "Atlanta Hawks", "Phoenix Suns", "Chicago Bulls"):
            assert phantom not in names, f"{phantom} priced 0.48 on a 0.01/0.95 book"

    def test_the_honest_rungs_underneath_are_PROMOTED_not_truncated(self):
        """The placement claim, and the one a post-slice drop would fail.

        Dropped before `[:limit]`, the card refills from the market's own real
        legs. Dropped after, it would serve one rung and NEVER-EMPTIES would hand
        the four phantoms straight back.
        """
        top = _build_search_top_outcomes(_curry_market(), limit=5, lean=False)

        assert [o["name"] for o in top] == [
            "Golden State Warriors",
            "San Antonio Spurs",
            "Charlotte Hornets",
            "Cleveland Cavaliers",
        ], "the slice must refill from the legs the phantoms were displacing"

    def test_the_one_real_rung_KEEPS_THE_CARD_and_its_number_is_renormalized(self):
        """0.74 on a 0.52/0.96 book — a wide quote, but a real one. It leads.

        🔴 ITS PRINTED NUMBER MOVES, AND THAT IS A CONSEQUENCE WORTH STATING.
        Production serves this card RAW (0.74 · 0.48 · 0.48 · 0.48 · 0.48, summing
        to 2.66) because #1200's overround guard reads a field summing far past
        100% as a set of independent binaries and declines to squeeze it. Fifteen
        phantoms at 0.48 are what put it there. With them gone the field is
        coherent again (sum 1.40) and gets the #23 squeeze it should always have
        had: 0.529 · 0.179 · 0.146 · 0.146.

        So the fix does not only remove four rows — it hands a mutually exclusive
        field back to the normalizer that had given up on it. Pinned rather than
        left to be discovered, and `test_the_phantoms_are_what_defeated_the_squeeze`
        below is the control that says which direction that ran in.

        (#1201's placeholder strip cannot reach this: it keys on EXACTLY 0.5 and
        these sit at 0.48.)
        """
        top = _build_search_top_outcomes(_curry_market(), limit=5, lean=False)

        assert top[0]["name"] == "Golden State Warriors"
        assert top[0]["probability"] == pytest.approx(0.529, abs=0.005)
        assert sum(o["probability"] for o in top) == pytest.approx(1.0, abs=0.02)

    def test_the_phantoms_are_what_defeated_the_squeeze(self):
        """The BEFORE control, and it reproduces production byte for byte.

        Same rows, books stripped to NULL so the guard passes every leg through —
        which is exactly the code path master runs. If this ever stops printing
        the four 0.48s, the fixture has drifted away from the defect and every
        assertion above it is measuring nothing.
        """
        market = _curry_market()
        before = _Market(
            [
                _Outcome(o.id, o.name, o.current_probability, None, None)
                for o in market.outcomes
            ]
        )

        top = _build_search_top_outcomes(before, limit=5, lean=False)

        assert [(o["name"], o["probability"]) for o in top] == [
            ("Golden State Warriors", 0.74),
            ("Brooklyn Nets", 0.48),
            ("Atlanta Hawks", 0.48),
            ("Phoenix Suns", 0.48),
            ("Chicago Bulls", 0.48),
        ], "production served exactly this on 2026-09-17"

    def test_the_typeahead_dropdown_is_served_by_the_same_guard(self):
        """One builder, both surfaces — the reason the guard goes here."""
        top = _build_search_top_outcomes(_curry_market(), limit=3, lean=True)

        assert [o["name"] for o in top] == [
            "Golden State Warriors",
            "San Antonio Spurs",
            "Charlotte Hornets",
        ]

    def test_the_card_the_reader_gets_no_longer_carries_them(self):
        card = _format_futures_for_search(_curry_market())

        assert "Atlanta Hawks" not in [o["name"] for o in card["top_outcomes"]]
        # The rest of the card is untouched: the ship withholds rungs, it does not
        # hollow out the payload's other keys.
        assert card["id"] == 57777176
        assert card["outcome_count"] == 8

    def test_a_phantom_never_sits_in_the_normalization_divisor(self):
        """The second, quieter lie: four phantoms deflate every real number.

        `_normalize_search_outcome_probs` divides a mutually-exclusive board by
        its own sum. Four fabricated 0.48s in that divisor either squash the real
        leader or — as here — push the field past #1200's overround bound so the
        squeeze never runs at all. Either way the number a reader reads is a
        function of rows no book stands behind. Dropped upstream of the
        normalizer, the divisor holds only prices the market actually quoted.
        """
        top = _build_search_top_outcomes(_curry_market(), limit=5, lean=False)
        leader = next(o for o in top if o["name"] == "Golden State Warriors")

        assert leader["probability"] > 0.5, (
            "a phantom inside the divisor would have moved the one real answer"
        )
        assert all(
            o["name"] not in ("Brooklyn Nets", "Atlanta Hawks", "Phoenix Suns", "Chicago Bulls")
            for o in top
        )


# ---------------------------------------------------------------------------
# 2. THE REVERSE DIRECTION. Withholding on a search surface is a suppression,
#    and it is asserted at least as hard as the forward direction.
# ---------------------------------------------------------------------------


class TestARealPriceSurvives:
    def test_a_genuine_coin_flip_on_a_tight_book_keeps_its_number(self):
        """The whole constraint on this ship: no blanket suppression of 50%.

        Production control found in the wild the same day — a 0.500 served on a
        real `0.4800/0.5200` book passed straight through the grouped feed's
        twin of this guard.
        """
        market = _Market([_Outcome(1, "Over 2.5", 0.50, 0.48, 0.52)])
        top = _build_search_top_outcomes(market, limit=5, lean=False)

        assert [o["name"] for o in top] == ["Over 2.5"]
        assert _futures_card_has_no_answer(market) is False

    @pytest.mark.parametrize(
        "name,prob,bid,ask",
        [
            # Live production controls, read 2026-09-17 in the same sweep. Every
            # one sits in the 0.40-0.60 band and every one must survive.
            ("Draw (2nd Inning Winner)", 0.51, 0.44, 0.58),
            ("Boston Red Sox (First 5)", 0.485, 0.46, 0.51),
            ("Draw (1st Inning Winner)", 0.51, 0.42, 0.60),
            ("Dodgers 100+ wins", 0.41, 0.38, 0.44),
        ],
    )
    def test_the_measured_coin_flip_band_controls_all_survive(self, name, prob, bid, ask):
        market = _Market([_Outcome(1, name, prob, bid, ask)])

        assert [o["name"] for o in _build_search_top_outcomes(market)] == [name]

    def test_a_wide_book_whose_price_is_NOT_the_midpoint_survives(self):
        """A both-extremes book priced far from its midpoint got there by a trade.

        #5247's condition 3, and the class the predicate would destroy without it.
        """
        market = _Market([_Outcome(1, "Longshot", 0.78, 0.01, 0.99)])

        assert [o["name"] for o in _build_search_top_outcomes(market)] == ["Longshot"]

    def test_a_one_sided_book_survives(self):
        """An ask at 36c says nobody will sell below 36c — that is information."""
        market = _Market([_Outcome(1, "Ask only", 0.50, None, 0.36)])

        assert [o["name"] for o in _build_search_top_outcomes(market)] == ["Ask only"]

    def test_a_model_price_with_no_book_at_all_survives(self):
        """DataGolf, odds_api, a derived complement: both columns NULL."""
        market = _Market([_Outcome(1, "Model 50", 0.50, None, None)])

        assert [o["name"] for o in _build_search_top_outcomes(market)] == ["Model 50"]
        assert _futures_market_prices_only_empty_books(market) is False


# ---------------------------------------------------------------------------
# 3. THE BOUNDS, each asserted on the side that matters. These are #5247's
#    measured constants and this file does not move them — it pins that they
#    have not been moved here by accident.
# ---------------------------------------------------------------------------


class TestTheBounds:
    def test_a_three_cent_bid_was_5333s_and_IS_taken_here_now(self):
        """FLIPPED by #5333 (bid bound 0.02 -> 0.05, 2026-09-17).

        The literal shape this ship promoted onto the Lions/Bills card: a 0.505 leg
        on 0.03/0.97 replacing the 0.01/0.95 legs it dropped. It is dropped too now,
        so the slice reaches further down the honest ladder instead of stopping on
        the next phantom.
        """
        market = _Market([_Outcome(1, "Team First TD", 0.505, 0.03, 0.97)])

        assert _build_search_top_outcomes(market) == []

    def test_the_bid_bound_is_inclusive_at_two_cents(self):
        market = _Market([_Outcome(1, "Total Corners O/U 12.5", 0.50, 0.02, 0.98)])

        assert _build_search_top_outcomes(market) == []

    def test_a_six_cent_bid_is_past_the_5333_bound_and_is_kept(self):
        """The new edge, on the side the bid decides: the price sits exactly on the
        book's own midpoint, so only the bound can be what keeps it."""
        market = _Market([_Outcome(1, "Team First TD", (0.06 + 0.97) / 2, 0.06, 0.97)])

        assert [o["name"] for o in _build_search_top_outcomes(market)] == ["Team First TD"]

    def test_an_ask_below_the_bound_is_a_book_that_bounds_something(self):
        market = _Market([_Outcome(1, "Half ask", 0.475, 0.01, 0.94)])

        assert [o["name"] for o in _build_search_top_outcomes(market)] == ["Half ask"]

    def test_the_half_cent_skew_is_INSIDE_the_tolerance(self):
        """0.505 on 0.01/0.99 — the specimen shape, midpoint 0.50, skew 0.005.

        This is what separates the rule from `is_fabricated_midpoint`, whose
        0.0005 tolerance misses it by a factor of ten. Substituting that
        predicate is one of the mutants this file kills.
        """
        market = _Market([_Outcome(1, "Yes", 0.505, 0.01, 0.99)])

        assert _leg_prices_an_empty_book(market.outcomes[0]) is True
        assert _build_search_top_outcomes(market) == []


# ---------------------------------------------------------------------------
# 4. THE CARD-LEVEL WITHDRAWAL. Its own predicate over its own measured
#    population, and the union must keep all three separable.
# ---------------------------------------------------------------------------


class TestTheWithdrawal:
    def _corners(self):
        """Market 61214687, as served: one leg, 0.505 on a 0.02/0.98 book."""
        return _Market(
            [_Outcome(230321149, "Team to Take First Corner", 0.505, 0.02, 0.98)],
            id=61214687,
            name="Barrow AFC vs. Scunthorpe United FC - Total Corners",
        )

    def test_a_market_whose_every_price_is_a_phantom_withdraws_its_card(self):
        market = self._corners()

        assert _futures_market_prices_only_empty_books(market) is True
        assert _futures_card_has_no_answer(market) is True
        assert _build_search_top_outcomes(market) == []

    def test_the_new_population_is_DISJOINT_from_6327s(self):
        """A class leg must carry a price, so it can never be 'wholly unpriced'.

        The two predicates stay separately measurable — the thing #6327's own
        docstring asks for in as many words.
        """
        market = self._corners()

        assert _futures_market_is_wholly_unpriced(market) is False
        assert _futures_market_prices_only_empty_books(market) is True

    def test_a_market_with_ONE_real_leg_beside_its_phantoms_keeps_its_card(self):
        """The suppression bound. A props market carries real lines beside junk."""
        market = _Market(
            [
                _Outcome(1, "Goalscorer: Haaland", 0.495, 0.01, 0.99),  # phantom
                _Outcome(2, "Goalscorer: Doku", 0.495, 0.01, 0.99),  # phantom
                _Outcome(3, "Over 2.5 Goals", 0.62, 0.61, 0.63),  # real
            ]
        )

        assert _futures_market_prices_only_empty_books(market) is False
        assert _futures_card_has_no_answer(market) is False
        assert [o["name"] for o in _build_search_top_outcomes(market)] == ["Over 2.5 Goals"]

    def test_an_unpriced_leg_beside_a_phantom_still_withdraws(self):
        """`priced` is the population; a NULL leg is #6327's, not a reprieve."""
        market = _Market(
            [
                _Outcome(1, "Yes", 0.505, 0.01, 0.99),
                _Outcome(2, "No", None, None, None),
            ]
        )

        assert _futures_market_prices_only_empty_books(market) is True

    def test_a_market_with_no_rows_at_all_is_still_3412s_and_not_this_one(self):
        """`bool(priced)` is the guard against adopting an unmeasured population."""
        market = _Market([])

        assert _futures_market_prices_only_empty_books(market) is False
        assert _futures_card_has_no_answer(market) is True  # via #3412

    def test_an_ordinary_priced_market_is_in_none_of_the_three_populations(self):
        market = _Market(
            [_Outcome(1, "Arsenal", 0.55, 0.54, 0.56), _Outcome(2, "Spurs", 0.45, 0.44, 0.46)]
        )

        assert _futures_market_is_wholly_unpriced(market) is False
        assert _futures_market_prices_only_empty_books(market) is False
        assert _futures_card_has_no_answer(market) is False
        assert [o["name"] for o in _build_search_top_outcomes(market)] == [
            "Arsenal",
            "Spurs",
        ]
