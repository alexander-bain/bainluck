"""A MARKET THAT HOLDS NO OUTCOME ROW AT ALL STOPS TAKING A CARD SLOT ON /search. #3412.

═══ WHAT THE READER SAW ═══

`/search?q=pats`, production, 2026-09-15, phone width 390px
(`artifacts-latency-423/pats-390-futures.png`). Between "Pro Football: Patriots
vs. Jets Season Series Winner" (three priced rungs) and "Steelers vs. Patriots"
(fourteen), a full-height card:

    FOOTBALL  [Championship]                                        🏆
    Patriots vs. Bears

                        No outcomes available

Same purple border, same trophy chrome, same height as its priced siblings, and
no count badge where they carry one. It spends a card slot to say nothing.

═══ WHY IT IS A SHIP AND NOT A SHRUG ═══

#6327 (yesterday, this same function) withdrew the cards that draw a LADDER OF
DASHES, and deliberately fenced this population out as unmeasured. The desk made
that fence the next row. It is measured now:

**Population** (production, 2026-09-15): 10,771 open markets hold zero
`futures_outcomes` rows. 10,763 are Polymarket — Kalshi has fallen 480 → 8 since
the issue was filed, so the marquee-axiom half of #3412 has largely self-closed.

**Not emptied — never populated.** 10,730 of the 10,763 were touched again after
creation and still carry nothing, across six months of `created_at`. The poller
keeps visiting and keeps writing no outcome (gotcha #18's decomposition gap is
the standing suspicion; the INGEST half stays open on #3412 and is not this
ship).

**Reach — the number the row turned on.** Replaying the 30 most-frequent real
reader queries of the last 14 days (`search_query_logs`, robot-tagged rows
excluded per notice 39) against production search:

    futures rows served                 342
    of those, zero outcome rows          52   ← 15%, on 13 of the 30 queries

and they are not a tail: `pats`, `niners`, `red sox`, `chiefs`, `lakers`.
Specimens include "Patriots vs. Bills", "Jets vs. Patriots", "49ers vs.
Seahawks" and a **market_tier 1** "Boston Red Sox vs. Texas Rangers - 9th Inning
Winner". Alex's 2026-09-14 directive makes top-tier unknown state a defect
class; this is that class, on the most-searched queries we have.

**The withdrawal costs the reader nothing.** 26 of the 40 unique such rows name
a fixture the SAME response already answers, priced, in its `results` section —
the "Patriots vs. Bears" card sits below a games row reading *Chicago Bears 52%
/ New England Patriots 48%*. The remainder is tier-5 noise (juniors doubles,
esports, a darts leg). There is no number being taken away, because there is no
number.

**Search was the holdout, not the pioneer.** `/api/leagues/{key}` closed this at
the serving layer (`42aaf067`, declaring the drop under its own name,
`no_outcomes`); the hubs closed it at the render layer (PR #3409). Re-verified
today against the full 10,771-id set: the Discover feed, `/api/politics`,
`/api/economics` and `/api/entertainment` serve ZERO of them. Only search did.

═══ THE BOUNDARY THAT MATTERS MOST ═══

**Two populations, two predicates, never one.** They are composed at the call
site and nowhere else:

    no outcome rows whatsoever   #3412   `_futures_market_has_no_outcome_rows`
    rows, none of them priced    #6327   `_futures_market_is_wholly_unpriced`
    the union the page asks              `_futures_card_has_no_answer`

Collapsing them into one "is it empty" test is the tempting simplification and
it destroys the ability to re-measure or revert either half. `TestTheTwoHalves`
holds that line.

**THE SHIP STOPS AT /search, and the typeahead keeps the same population.** A
card and a dropdown row are different objects: the card is a full-height slot
printing prose where a number belongs (notice 34 / D102); a dropdown row without
an answer is just a title, which is honest navigation. Filtering the dropdown
was tried and reverted on evidence — it reddened four suites, one of which
(#4723's Korpatsch control) exists precisely to catch a pool key that becomes a
filter. `TestTheTypeaheadIsDeliberatelyNotInScope` records that, with the live
population so the exclusion is a decision and not an observation of nothing.

═══ WHAT MUST NOT CHANGE ═══

* A market with one priced rung keeps its card. Withdrawal on a search surface
  is a suppression; the reverse direction is asserted as hard as the forward one.
* `deduped_futures` stays whole for event-CONCEPT derivation. An unpriced winner
  field is still a real tournament and its page link must survive the card's
  withdrawal.
* Families withdraw with the flat bucket. A family composes from the wider
  deduped set and is exactly the back door a half-applied withdrawal leaves open.
* `_deduped_page` keeps feeding the headline-contender gate and the
  `bucket_collapse` verdict. Both ask questions about the page as COMPOSED, not
  as suppressed (see #6327's notes at the call site).
"""

import ast
import inspect

import pytest

import app.routes.events as _events_module
from app.routes.events import (
    _build_search_top_outcomes,
    _format_futures_for_search,
    _futures_card_has_no_answer,
    _futures_market_has_no_outcome_rows,
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
        self.id = kw.get("id", 60748139)
        self.name = kw.get("name", "Patriots vs. Bears")
        self.sport = None
        self.category = "football"
        self.llm_sport_category = "football"
        self.market_tier = kw.get("market_tier", 5)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "polymarket")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = True


def _specimen():
    """Market 60748139, "Patriots vs. Bears" — exactly as production served it."""
    return _Market([])


# ---------------------------------------------------------------------------
# 1. The specimen, in the direction it actually failed.
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_the_card_on_the_pats_page_holds_no_outcome_row(self):
        """NOT VACUOUS: the emptiness is the fixture's whole content, stated."""
        market = _specimen()
        assert market.outcomes == []
        assert market.name == "Patriots vs. Bears"

    def test_the_page_predicate_withdraws_it(self):
        """What `/search` now asks, and the answer that removes the card."""
        assert _futures_card_has_no_answer(_specimen()) is True

    def test_it_is_withdrawn_for_having_no_rows_not_for_being_unpriced(self):
        """The two halves must not be able to claim each other's specimen."""
        assert _futures_market_has_no_outcome_rows(_specimen()) is True
        assert _futures_market_is_wholly_unpriced(_specimen()) is False

    def test_the_card_it_would_have_drawn_really_is_answerless(self):
        """The formatter's own output — what the reader's card was built from.

        `outcome_count` 0 and an empty ladder is the whole card. There is no
        third thing on it that withdrawal would be throwing away.
        """
        card = _format_futures_for_search(_specimen())
        assert card["top_outcomes"] == []
        assert card["outcome_count"] == 0
        assert card["name"] == "Patriots vs. Bears"


# ---------------------------------------------------------------------------
# 2. The reverse direction. Suppression on a search surface is the risk.
# ---------------------------------------------------------------------------


class TestAMarketWithSomethingToSaySurvives:
    def test_one_priced_rung_keeps_the_card(self):
        market = _Market([_Outcome(1, "Patriots", 0.58), _Outcome(2, "Bears", 0.42)])

        assert _futures_market_has_no_outcome_rows(market) is False
        assert _futures_card_has_no_answer(market) is False
        assert _build_search_top_outcomes(market, limit=5) != []

    def test_the_thinnest_possible_real_market_keeps_its_card(self):
        """One row, one number. Still an answer."""
        market = _Market([_Outcome(1, "Yes", 0.05)])
        assert _futures_card_has_no_answer(market) is False

    @pytest.mark.parametrize("prob", [0.0, 0.5, 1.0])
    def test_any_single_real_number_anywhere_saves_the_market(self, prob):
        """Including a stored `0`, which is a price (#6327's boundary)."""
        outcomes = [_Outcome(i, f"Leg {i}") for i in range(1, 9)]
        outcomes[7].current_probability = prob
        assert _futures_card_has_no_answer(_Market(outcomes)) is False


# ---------------------------------------------------------------------------
# 3. THE BOUNDARY. Two measured populations, kept separable forever.
# ---------------------------------------------------------------------------


class TestTheTwoHalves:
    def test_6327s_predicate_is_unchanged_by_this_ship(self):
        """🔴 If this reddens, the two populations have been merged.

        #6327 measured 477 markets that hold rows and no price; #3412 measured
        10,771 that hold no rows. Each was withdrawn on its own evidence. A
        later "simplification" of `_futures_market_is_wholly_unpriced` to cover
        both makes either one impossible to re-measure or revert alone.
        """
        assert _futures_market_is_wholly_unpriced(_Market([])) is False
        assert _futures_market_has_no_outcome_rows(_Market([])) is True

    def test_the_6327_population_is_still_withdrawn_through_the_union(self):
        """A ladder of dashes must not be resurrected by this ship's rewrite."""
        dashes = _Market([_Outcome(1, "A"), _Outcome(2, "B"), _Outcome(3, "C")])

        assert _futures_market_has_no_outcome_rows(dashes) is False
        assert _futures_market_is_wholly_unpriced(dashes) is True
        assert _futures_card_has_no_answer(dashes) is True

    def test_the_union_is_exactly_the_or_of_the_two_and_nothing_more(self):
        """No third rule hiding in the composed predicate."""
        for market in (
            _Market([]),
            _Market([_Outcome(1, "A")]),
            _Market([_Outcome(1, "A", 0.0)]),
            _Market([_Outcome(1, "A", 0.5)]),
            _Market([_Outcome(1, "A"), _Outcome(2, "B", 0.5)]),
        ):
            assert _futures_card_has_no_answer(market) is (
                _futures_market_has_no_outcome_rows(market)
                or _futures_market_is_wholly_unpriced(market)
            )


# ---------------------------------------------------------------------------
# 4. THE SURFACE BOUNDARY. This ship stops at /search, and that is a decision.
# ---------------------------------------------------------------------------


class TestTheTypeaheadIsDeliberatelyNotInScope:
    """🔴 Tried, reverted on evidence, and recorded here so it is not retried blind.

    The dropdown serves the same population — measured 2026-09-15, 2 of 19
    futures rows across `pats` / `niners` / `red sox` / `chiefs` / `lakers`.
    Filtering it looked obviously right and is not:

    **A /search card and a dropdown row are different objects.** The card is a
    full-height slot printing "No outcomes available" — prose where a number
    belongs (notice 34 / D102). A dropdown row without an answer is just a
    title, which is honest navigation to a page the reader asked for.

    And the gate said so first. Filtering the pool reddened FOUR suites, one of
    which exists precisely to catch this: `_typeahead_pool_seeds`' Korpatsch row
    (#4723) is reachable by `pats` by INTERIOR SUBSTRING ONLY and is documented
    as "exactly the row that vanishes if the #4723 keys ever become a filter".
    It vanished. Also red: `test_route_typeahead_intent_5060`, and two more
    pool-ordering cases in the recall contract.

    Reopening this means arguing with #4723's control row, with a measurement of
    what a dropdown row is FOR — not with a one-line change.
    """

    def test_the_typeahead_does_not_ask_either_withdrawal_predicate(self):
        calls = _calls_inside("typeahead_search")

        assert "_futures_card_has_no_answer" not in calls
        assert "_futures_market_has_no_outcome_rows" not in calls

    def test_the_dropdown_population_is_real_and_is_being_left_alone(self):
        """NOT VACUOUS: the rows the dropdown keeps really are answer-less.

        `61062725` / `60959118`, served by the live typeahead today. The test
        above is a decision about these rows, not an observation that there are
        none.
        """
        esports = _Market([], id=61062725, name="Rainbow Six Siege: ENTERPRISE vs Chiefs")
        hockey = _Market([], id=60959118, name="NL: Rapperswil-Jona Lakers vs. Fribourg")

        assert _futures_market_has_no_outcome_rows(esports) is True
        assert _futures_market_has_no_outcome_rows(hockey) is True

    def test_an_empty_dropdown_ladder_does_not_imply_an_empty_market(self):
        """🔴 The mixed-cause trap, manufactured — still live for whoever retries this.

        Market `60768956`, "TX-04 House election: Pat Fallon vote percent",
        serves `top_outcomes: []` in the live dropdown while HOLDING outcome
        rows. Anyone reaching for "just drop the rows with no `top_outcomes`"
        would delete this one too, on no evidence and for a different cause.
        Any future typeahead rule must key on the ROWS, never on the rendered
        list.
        """
        pat_fallon = _Market(
            [_Outcome(1, "Pat Fallon"), _Outcome(2, "Other")],
            id=60768956,
            name="TX-04 House election: Pat Fallon vote percent",
        )

        assert _build_search_top_outcomes(pat_fallon, limit=3, lean=True) == []
        assert _futures_market_has_no_outcome_rows(pat_fallon) is False


# ---------------------------------------------------------------------------
# 5. WIRING. Everything above tests the predicates; none of it tests that the
#    ROUTES ASK THEM.
# ---------------------------------------------------------------------------


def _calls_inside(func_name: str) -> set[str]:
    """Names called anywhere inside the named module-level function."""
    tree = ast.parse(inspect.getsource(_events_module))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            return {
                getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                for c in ast.walk(node)
                if isinstance(c, ast.Call)
            }
    raise AssertionError(f"{func_name} not found in app/routes/events.py")


class TestTheRoutesActuallyAskTheQuestion:
    """🔴 THE CLASS THAT ALMOST SHIPPED VACUOUS.

    Mutation-tested on 2026-09-15: with only the predicate assertions above,
    deleting the filter from `search_events` — both the flat bucket AND the
    families composer — or the `continue` from `typeahead_search` left **all 26
    tests green**. The predicates were provably correct and provably unused: the
    card walks straight back onto the reader's page and nothing says a word.

    A withdrawal ship is exactly the shape where this happens, because the unit
    under test is a pure `bool` and the behaviour under test is a call site in a
    900-line route handler that needs a populated database to exercise. The AST
    is the cheap half of that proof and it kills all three mutants.

    If a later refactor renames the predicate or moves the filter into a helper,
    this test SHOULD go red — then reproduce the three mutants against whatever
    replaced it, and re-aim this at the new name. Do not delete it.
    """

    def test_the_search_page_filters_on_the_union_predicate(self):
        """Kills: the flat-bucket filter deleted, and the families one too.

        Both live in `search_events` and both must ask the WIDE predicate — a
        family composes from the wider deduped set and is the back door a
        half-applied withdrawal leaves open.
        """
        calls = _calls_inside("search_events")

        assert "_futures_card_has_no_answer" in calls, (
            "/search must withdraw the answerless card — see #3412/#6327"
        )
        assert "_compose_futures_families" in calls, (
            "NOT VACUOUS: the families composer is still called from this "
            "handler, so the filter on its argument is still load-bearing"
        )

    def test_the_search_page_asks_it_at_both_call_sites_not_one(self):
        """The flat bucket and the families argument are two separate filters.

        Counted, because a single `in` check passes with either one deleted.
        """
        tree = ast.parse(inspect.getsource(_events_module))
        handler = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "search_events"
        )
        uses = [
            c
            for c in ast.walk(handler)
            if isinstance(c, ast.Call)
            and getattr(c.func, "id", None) == "_futures_card_has_no_answer"
        ]
        assert len(uses) == 2, (
            f"expected the flat bucket AND the families composer to filter "
            f"(2 call sites), found {len(uses)}"
        )

    def test_the_withdrawal_is_confined_to_the_search_handler(self):
        """The scope of the ship, asserted as wiring and not just as prose.

        `search_events` is the ONLY function that may ask
        `_futures_card_has_no_answer`. The typeahead's exclusion has its own
        class below and its own reasons; this asserts nothing else in the module
        has quietly grown the filter.
        """
        tree = ast.parse(inspect.getsource(_events_module))
        askers = {
            fn.name
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            for c in ast.walk(fn)
            if isinstance(c, ast.Call)
            and getattr(c.func, "id", None) == "_futures_card_has_no_answer"
        }
        assert askers == {"search_events"}, (
            f"the withdrawal reached a surface it was not measured on: {askers}"
        )
