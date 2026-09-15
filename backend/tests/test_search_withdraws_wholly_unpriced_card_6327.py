"""A MARKET WITH NO PRICE AT ALL STOPS DRAWING A LADDER OF DASHES ON /search. #6327.

═══ WHAT WAS MEASURED ═══

`GET /api/events/search?q=Sonmez`, production, 2026-09-15. The result list drew
market **61106176** "WTA Guadalajara Winner" (kalshi, `market_tier` 1, status
`open`) as a full card: **sixteen ranked rungs, a dash on every one**, under a
"2h ago" price stamp.

Read against the rows the same minute, all sixteen legs:

    current_probability   NULL      current_yes_bid   NULL
    current_yes_ask       NULL      opening_probability NULL

So the card was not stale and not mispriced — it had never held a number, and
the ranking implied by sixteen ordered rungs was information we did not have.

Population, production the same minute, over the 13,397 open tier-1/2 markets:

    has a priced outcome                    12,919
    NO priced outcome, every leg NULL          478   ← this ship
    NO priced outcome, some leg a stored 0       0

and of those 478, **459 have never held a single `futures_odds_snapshots` row**
— there is no price to recover and none is being hidden, so withdrawing the card
deletes no alarm (the same evidence `routes/politics.py` records for #6235).
The remaining **19 once held a price and now serve none**; that is a genuine
ingest hole, recorded on #6327 rather than left on a reader's screen to report
itself as sixteen dashes.

═══ THE MECHANISM, AND WHY IT IS A SIBLING-SURFACE BUG ═══

**#6235 closed exactly this class eight hours earlier** — `routes/politics.py:247`
and its twin in `entertainment.py` grew
`if not any(o.current_probability is not None for o in outcomes): return None`.
The search serializer shares the defect and never got the guard: the
"a shipped fix's guard pins ONE component, sibling surfaces keep the bug" class.
The predicate here is the sibling's, deliberately unchanged.

═══ THE BOUNDARY THAT MATTERS MOST ═══

`is not None`, NOT truthiness — and this file's third class is the one that
keeps it honest.

`_build_search_top_outcomes` serves a probability as
`float(o.current_probability) if o.current_probability else None`, so a stored
`0` ALSO renders as a dash. It is tempting to read "all dashes" as one
population and withdraw on the truthy test. That is wrong: measured live,
**4,761 of 5,216 zero legs (91%) carry a live `current_yes_ask`** — a market a
reader can still buy — and withdrawing those would delete a real answer. That
render is #6327's SECOND finding (a real `0` should read `<1%`, not `—`), it is
display semantics for the ladder's owner, and it was withdrawn from this ship by
its own filer after measurement.

The two findings cannot collide on one row — zero of the 478 are the stored-zero
kind — and `test_a_zero_priced_rung_is_a_price_and_its_card_survives` is what
holds that line if anyone later "simplifies" the predicate to `if not any(...)`.

═══ WHAT MUST NOT CHANGE ═══

* A market with ONE priced rung keeps its card. Withdrawal on a search surface
  is a suppression; the reverse direction is asserted as hard as the forward one.
* `deduped_futures` stays whole for the event-CONCEPT derivation. The specimen is
  a tennis winner field, which is exactly the shape that resolves to a tournament
  page — the market is unpriced, the tournament is real, and the page link must
  survive the card's withdrawal.
* The `bucket_collapse` verdict keeps measuring DEDUP, not this withdrawal
  (`tests/evals/test_search_bucket_stability.py`). A deliberate suppression is
  not a merge, and conflating them reddens the recall gate on the fix itself.
"""

import pytest

from app.routes.events import (
    _build_search_top_outcomes,
    _format_futures_for_search,
    _futures_market_is_wholly_unpriced,
)


class _Outcome:
    """The attributes the search builder reads off an ORM outcome row."""

    def __init__(self, oid, name="Leg", prob=None, ask=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
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
        self.id = kw.get("id", 61106176)
        self.name = kw.get("name", "WTA Guadalajara Winner")
        self.sport = None
        self.category = "tennis"
        self.llm_sport_category = "tennis"
        self.market_tier = kw.get("market_tier", 1)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "kalshi")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = True


#: The specimen's own sixteen, by name, all NULL — as production served them.
_SPECIMEN_NAMES = [
    "Marta Kostyuk", "Iva Jovic", "Sara Bejlek", "Diane Parry",
    "Cristina Bucsa", "Liudmila Samsonova", "Zeynep Sonmez", "Emiliana Arango",
    "Solana Sierra", "Katarzyna Kawa", "Panna Udvardy", "Anna Blinkova",
    "Julia Riera", "Maria Carle", "Francesca Jones", "Renata Zarazua",
]


def _specimen():
    return _Market([_Outcome(229645386 + i, n) for i, n in enumerate(_SPECIMEN_NAMES)])


# ---------------------------------------------------------------------------
# 1. The specimen, in the direction it actually failed.
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_sixteen_null_rungs_draw_no_ladder_at_all(self):
        """Market 61106176: sixteen legs, not one number. It drew all sixteen."""
        market = _specimen()
        # NOT VACUOUS: the rungs are really there and really reach the builder —
        # an empty result must come from the guard, not from an empty fixture.
        assert len(market.outcomes) == 16
        assert all(o.current_probability is None for o in market.outcomes)

        assert _build_search_top_outcomes(market, limit=5, lean=False) == []

    def test_the_typeahead_dropdown_is_served_by_the_same_guard(self):
        """`lean=True` carried three `probability: None` rungs for the same row.

        One predicate, both surfaces — the point of fixing the shared builder
        rather than the card formatter.
        """
        assert _build_search_top_outcomes(_specimen(), limit=3, lean=True) == []

    def test_the_card_the_reader_would_have_seen_has_an_empty_ladder(self):
        """The formatter's own output, which is what the page renders."""
        card = _format_futures_for_search(_specimen())
        assert card["top_outcomes"] == []
        # The rest of the card is untouched: this ship withdraws it at the page,
        # it does not quietly hollow out the payload's other keys.
        assert card["id"] == 61106176
        assert card["name"] == "WTA Guadalajara Winner"
        assert card["outcome_count"] == 16

    def test_the_page_predicate_withdraws_it(self):
        assert _futures_market_is_wholly_unpriced(_specimen()) is True


# ---------------------------------------------------------------------------
# 2. The reverse direction. Suppression on a search surface is the risk.
# ---------------------------------------------------------------------------


class TestAPricedMarketSurvives:
    def test_one_priced_rung_among_fifteen_nulls_keeps_the_card(self):
        """The thinnest possible real market still answers the question."""
        outcomes = [_Outcome(229645386 + i, n) for i, n in enumerate(_SPECIMEN_NAMES)]
        outcomes[6].current_probability = 0.31  # Zeynep Sonmez, the queried name

        market = _Market(outcomes)
        top = _build_search_top_outcomes(market, limit=5, lean=False)

        assert top, "a market with a real price must keep its ladder"
        assert top[0]["name"] == "Zeynep Sonmez"
        assert _futures_market_is_wholly_unpriced(market) is False

    def test_an_ordinary_fully_priced_ladder_is_untouched(self):
        market = _Market(
            [
                _Outcome(1, "Kostyuk", 0.40),
                _Outcome(2, "Jovic", 0.35),
                _Outcome(3, "Bejlek", 0.25),
            ]
        )
        top = _build_search_top_outcomes(market, limit=5, lean=False)

        assert [o["name"] for o in top] == ["Kostyuk", "Jovic", "Bejlek"]
        assert _futures_market_is_wholly_unpriced(market) is False


# ---------------------------------------------------------------------------
# 3. THE BOUNDARY. A stored 0 is a PRICE, and 91% of them have a live ask.
#    This is the class that fails if the predicate is ever "simplified" to a
#    truthiness test — the exact edit #6327's filer measured and withdrew.
# ---------------------------------------------------------------------------


class TestAZeroIsAPriceNotAnAbsence:
    def test_a_zero_priced_rung_is_a_price_and_its_card_survives(self):
        """Every rung stored `0`, asks live: a market a reader can still buy.

        `if not any(o.current_probability ...)` — the truthy form — withdraws
        this card. It must not: the defect on these rows is that `0` renders as
        a dash instead of `<1%`, and that is a RENDER decision for the ladder's
        owner, not a reason to delete the market from search.
        """
        market = _Market(
            [
                _Outcome(1, "Longshot A", 0.0, ask=0.02),
                _Outcome(2, "Longshot B", 0.0, ask=0.01),
            ]
        )

        assert _futures_market_is_wholly_unpriced(market) is False, (
            "a stored 0 is a price — 91% of zero legs carry a live ask"
        )
        assert _build_search_top_outcomes(market, limit=5, lean=False) != []

    def test_the_predicate_reads_is_not_none_and_not_truthiness(self):
        """States the distinction directly, so the reason survives a refactor."""
        zero = _Market([_Outcome(1, "Longshot", 0.0)])
        null = _Market([_Outcome(1, "Longshot", None)])

        assert _futures_market_is_wholly_unpriced(zero) is False
        assert _futures_market_is_wholly_unpriced(null) is True


# ---------------------------------------------------------------------------
# 4. Degenerate shapes the route can hand the predicate.
# ---------------------------------------------------------------------------


class TestDegenerateShapes:
    def test_a_market_with_no_outcome_rows_is_left_alone(self):
        """🔴 NOT this ship's population, and the first draft got it wrong.

        Production, 2026-09-15, of 14,189 open tier-1/2 markets: **477** have
        outcomes and no price (this ship), **1,043** have no outcome rows at all.
        The second group draws no ladder to be dishonest with — it is #3412, with
        a different remedy — and it is more than TWICE the size of the population
        that was measured. Withdrawing it here would have been an unmeasured
        suppression riding a measured one, on 1,043 cards, invisibly.

        The card still ships; its ladder is empty either way.
        """
        assert _futures_market_is_wholly_unpriced(_Market([])) is False
        assert _build_search_top_outcomes(_Market([]), limit=5) == []

    @pytest.mark.parametrize("prob", [0.0, 0.5, 1.0])
    def test_any_single_real_number_anywhere_saves_the_market(self, prob):
        outcomes = [_Outcome(i, f"Leg {i}") for i in range(1, 9)]
        outcomes[7].current_probability = prob
        assert _futures_market_is_wholly_unpriced(_Market(outcomes)) is False
