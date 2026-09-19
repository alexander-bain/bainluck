"""AN EXCLUSIVE BOARD WHOSE SERVED LADDER SUMS FAR UNDER 100% STOPS TAKING A CARD. #5516 arm 1.

═══ WHAT THE READER SAW ═══

`/search?q=cubs`, production, 2026-09-19, phone width 390px:

    BASEBALL  [Game Props]                                         2
    Chicago Cubs vs. Cincinnati Reds - 2nd Inning Winner
        Chicago Cubs      24%
        Cincinnati Reds   18%

Both numbers are honest. The SET is not. An inning is a three-way market — team,
team, tie — and the tie leg is missing, so 58% of the board is absent and the
card reads as a two-horse race. The sibling "5th Inning Winner" card on the same
query carries its `Draw 57%` and sums to 103%, which is what makes the defect
per-row rather than per-family, and is why the reader has no way to tell.

═══ THE MECHANISM, AND THE ONE-LINE FIX THAT WOULD HAVE BEEN WRONG ═══

The missing legs are not dropped on the read side. They were never stored.
Gamma event 1046284 (*Red Sox v Rays 9th*) lists three `active:true` sub-markets
and we hold ONE:

    leg                        price   bestBid  bestAsk  spread   stored?
    Red Sox to win the 9th     0.165   0.06     0.27     0.21     no
    Rays to win the 9th        0.08    0.01     0.15     0.14     yes
    9th inning tied?           0.52    0.28     0.76     0.48     no

The two dropped legs are exactly the two whose spread clears #1578's
untradeable-book bar, with `lastTradePrice` null so there is no fallback price.
**That writer is correct**: its cohort's stored midpoints mean 0.5003 against an
actual win rate of 0.0013 over 1,580 outcomes, and its header says in terms "do
not turn it into a knob". Widening it re-admits the phantom cohort and un-ships
#1578, #5247 and #6676 in one line.

So the defect is one layer up, and it generalises past its own cause: *a refusal
that is correct for its own question is still wrong when the caller renders the
survivors as a complete ladder.*

═══ THE PRECONDITIONS, AND THE TWO REGRESSIONS THAT NEARLY SHIPPED ═══

The first cut of this guard was "exclusive board, sum < 0.50". Replayed against
the 30 most-frequent real reader queries it would have withdrawn:

    Will the Fed do a rate cut greater than 25bps this year?    Yes  4.1%
    Mike Vrabel out as Patriots Head Coach by Dec 31, 2026?     Yes  3.6%
    Canadian Team to Win the Stanley Cup® Before 2030-31        Yes 41.5%

Honest cards, every one. A binary question's complement is IMPLICIT, and
`mutually_exclusive` does not fence them because that column DEFAULTS True — 5
of 23 sampled one-leg exclusive markets were Kalshi YES questions wearing it.

The SECOND regression is the one that shaped the final rule, and it was caught
by other ships' controls rather than by measurement. #6676's coin-flip-band
controls are single legs that must survive — `Dodgers 100+ wins 41%`, `Boston
Red Sox (First 5) 48.5%` — and #6327's stored-zero control is a two-rung card
at `0% / 0%`. A LONE NUMBER IS A PROPOSITION, NOT A BOARD, and nothing available
at serve time separates "Dodgers 100+ wins 41%" from a one-leg fragment of a
three-way inning market: not the name, not `market_type` (both spell
`unshaped`), not `mutually_exclusive`. So the guard requires **two or more
served rungs stating some mass**, and the entire one-leg population — 243
markets, including the vivid `9th Inning Winner` rows at 8% — is left served and
named as this ship's remainder. Judging it needs the venue's own board size,
which is an ingest-side signal this surface does not have.

Two consequences worth stating plainly: this file does not edit a single
existing control, and `TestTheOneLegPopulationIsParkedNotFixed` exists so nobody
reads the remainder as an oversight.

The last precondition is the one the issue's own diagnosis did not have: a top-5
cut of a 32-team field sums far under 1.0 and is PERFECTLY HONEST. Only a board
whose every surviving leg fits on the card can be read as complete. Without it
this guard would have swallowed most of the futures catalogue.

═══ MEASURED BEFORE IT WAS BUILT ═══

#6327's note stands: an unmeasured suppression must never ride a measured one.
Production, 2026-09-19, all 19,622 open exclusive markets whose whole surviving
board fits on a card:

    sum >= 0.97   18,289   93.2%, the healthy mass, tightly clustered
    0.90 - 0.97      420
    0.70 - 0.90      172
    0.50 - 0.70      155
    0.30 - 0.50      186
    sum <  0.30      400

Bimodal, which is what makes 0.50 a threshold rather than a preference: 93% of
boards sum to ~1.0 and the defective tail sits far away from them. 0.50 is the
CONSERVATIVE end of the gap, leaving the ambiguous 0.50–0.97 band (747 markets)
served and re-measurable on its own account.

**Withdrawn, all preconditions applied: 326 markets** — 238 tier 5, 56 tier 2,
29 tier 1; 209 `championship`, 75 `game_prop`, 19 politics. (Before the two-rung
precondition the same measurement read 569; the difference is the parked one-leg
population.)

**Reader reach**: of 271 served futures cards, 17 carried an under-half ladder;
6 survive exclusivity and the binary test, and 3 survive the two-rung rule —
on the queries `chicago`, `yankees`/`yank` and `galatasaray`:

    Chicago Cubs vs. Cincinnati Reds - 7th Inning Winner    0.395, 2 rungs
    New York Yankees vs. Arizona Diamondbacks - 7th Inning  0.355, 2 rungs
    Trabzonspor vs. Galatasaray SK - Exact Score            0.165, 2 rungs

Specimens from the wider 326 the replay did not surface: `OBOS-ligaen (Norway)
2026 Winner` (five teams summing 0.5%), `LA-06 Republican nominee?` (four
candidates summing 13.9%), `AFC Asian Cup 2027: Group B Winner` (two, 32.5%).

**No marquee fixture's own market is in it** (notice 27): the tier-1 rows are
inning PROPS of marquee games, and each game's own market is a separate row this
predicate never sees.

═══ THE BOUNDARY THAT MATTERS MOST ═══

**The predicate must judge the legs the BUILDER draws, not the rows the market
owns**, and that is why `_search_surviving_legs` was extracted. Market 57574860
(*Which company has the best AI model on LiveBench (Coding)?*) owns 22 priced
legs summing to **10.95**, 21 of them the identical ~0.50 phantom on an empty
book. #6676 refuses every one and the card draws `Anthropic 45%` alone. A
predicate reading raw rows sees 22 rungs summing 10.95 and waves it through; the
shipped one sees a single rung and parks it under precondition 2. Same verdict,
opposite reasoning, and `TestItJudgesTheServedLadderNotTheStoredRows` pins the
reasoning — it is the class that fails first if anyone "simplifies" the
predicate back onto `market.outcomes`.
"""

import ast
import inspect

import app.routes.events as _events_module
from app.routes.events import (
    _BOARD_MIN_SERVED_LEGS,
    _BOARD_MIN_SERVED_SUM,
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _format_futures_for_search,
    _futures_board_is_mostly_unserved,
    _futures_card_has_no_answer,
    _futures_market_has_no_outcome_rows,
    _futures_market_is_wholly_unpriced,
    _futures_market_prices_only_empty_books,
    _search_surviving_legs,
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
        self.id = kw.get("id", 61417444)
        self.name = kw.get("name", "Chicago Cubs vs. Cincinnati Reds - 2nd Inning Winner")
        self.sport = None
        self.category = kw.get("category", "game_prop")
        self.llm_sport_category = "baseball"
        self.market_tier = kw.get("market_tier", 5)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "polymarket")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", True)


def _specimen():
    """Market 61417444, exactly as production served it: 24% + 18% = 42%."""
    return _Market(
        [
            _Outcome(1, "Chicago Cubs", 0.24, bid=0.20, ask=0.28),
            _Outcome(2, "Cincinnati Reds", 0.18, bid=0.14, ask=0.22),
        ]
    )


def _healthy_sibling():
    """The 5th-Inning card on the SAME query, which carries its tie leg."""
    return _Market(
        [
            _Outcome(1, "Chicago Cubs", 0.24, bid=0.20, ask=0.28),
            _Outcome(2, "Cincinnati Reds", 0.18, bid=0.14, ask=0.22),
            _Outcome(3, "Draw", 0.57, bid=0.53, ask=0.61),
        ],
        name="Chicago Cubs vs. Cincinnati Reds - 5th Inning Winner",
    )


# ---------------------------------------------------------------------------
# 1. The specimen, in the direction it actually failed.
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_the_card_really_does_serve_a_board_that_does_not_add_up(self):
        """NOT VACUOUS: the fixture's incoherence is stated, not assumed."""
        legs = _search_surviving_legs(_specimen())
        assert len(legs) == 2
        assert round(sum(float(o.current_probability) for o in legs), 2) == 0.42

    def test_the_predicate_fires_on_it(self):
        assert _futures_board_is_mostly_unserved(_specimen()) is True

    def test_the_page_predicate_withdraws_the_card(self):
        """THE APPLICATION, not the computation.

        Severing the fourth arm of the union — computing the predicate and never
        reaching it — leaves every other test in this file green. This is the one
        that reddens.
        """
        assert _futures_card_has_no_answer(_specimen()) is True

    def test_the_builder_empties_the_ladder(self):
        """The second application point, and it is separately severable.

        The card is withdrawn by the union above; this is what stops the TYPEAHEAD
        dropdown printing `Cubs 24% · Reds 18%` one tap above it.
        """
        assert _build_search_top_outcomes(_specimen(), limit=5) == []
        assert _build_search_top_outcomes(_specimen(), limit=3, lean=True) == []

    def test_the_card_the_reader_would_have_got_is_the_one_in_the_issue(self):
        card = _format_futures_for_search(_specimen())
        assert card["top_outcomes"] == []
        assert card["name"] == "Chicago Cubs vs. Cincinnati Reds - 2nd Inning Winner"

    def test_it_is_withdrawn_for_its_own_reason_and_not_another_arms(self):
        """The four arms must not be able to claim each other's specimen."""
        m = _specimen()
        assert _futures_market_has_no_outcome_rows(m) is False
        assert _futures_market_is_wholly_unpriced(m) is False
        assert _futures_market_prices_only_empty_books(m) is False
        assert _futures_board_is_mostly_unserved(m) is True


# ---------------------------------------------------------------------------
# 2. The reverse direction. Suppression on a search surface is the risk, and
#    every class below was a card this guard would have deleted at some point
#    while it was being built.
# ---------------------------------------------------------------------------


class TestTheHealthyBoardsThatMustSurvive:
    def test_the_sibling_card_that_carries_its_tie_leg_is_untouched(self):
        m = _healthy_sibling()
        assert _futures_board_is_mostly_unserved(m) is False
        assert _futures_card_has_no_answer(m) is False
        assert len(_build_search_top_outcomes(m, limit=5)) == 3

    def test_a_non_exclusive_family_is_never_this_population(self):
        """#199's golf make-cut/top-N families sum to multiples of 100%.

        🪤 THIS IS NOT THE GUARD ON PRECONDITION 1, despite its name. The
        fixture is ONE leg, so precondition 2 returns first and the exclusivity
        arm is never reached — severing that arm leaves this test green. The
        verdict is right and the reason is not. `TestPrecondition1Holds…` at the
        foot of this file is the class that actually kills the mutant.
        """
        m = _Market(
            [_Outcome(1, "Scheffler to make the cut", 0.31, bid=0.29, ask=0.33)],
            mutually_exclusive=False,
        )
        assert _futures_board_is_mostly_unserved(m) is False
        assert _futures_card_has_no_answer(m) is False

    def test_a_truncated_ladder_sums_under_one_honestly(self):
        """A top-5 cut of a big field. The reader knows a ladder is a ladder."""
        m = _Market(
            [_Outcome(i, f"Team {i}", 0.05, bid=0.03, ask=0.07) for i in range(1, 9)],
            name="2027 Pro Football Champion",
        )
        legs = _search_surviving_legs(m)
        assert len(legs) == 8 > _SEARCH_LADDER_LIMIT
        assert round(sum(float(o.current_probability) for o in legs), 2) == 0.40
        assert _futures_board_is_mostly_unserved(m) is False
        assert len(_build_search_top_outcomes(m, limit=5)) == 5

    def test_the_exact_threshold_is_served_not_withdrawn(self):
        """0.50 is `< _BOARD_MIN_SERVED_SUM`'s open end, deliberately.

        🪤 The leg names here are REAL ones. `"A"` / `"B"` / `"Team A"` are
        placeholder names, so a fixture using them empties in
        `_search_surviving_legs` and this test passes for the wrong reason —
        the predicate returns False on `not priced`, which is #6327's arm, not
        a judgement about the threshold at all. The survivor assertions below
        are what stop that recurring.
        """
        at = _Market([_Outcome(1, "Chicago Cubs", 0.30, bid=0.28, ask=0.32),
                      _Outcome(2, "Cincinnati Reds", 0.20, bid=0.18, ask=0.22)])
        assert len(_search_surviving_legs(at)) == 2
        assert sum(float(o.current_probability) for o in at.outcomes) == _BOARD_MIN_SERVED_SUM
        assert _futures_board_is_mostly_unserved(at) is False

        under = _Market([_Outcome(1, "Chicago Cubs", 0.30, bid=0.28, ask=0.32),
                         _Outcome(2, "Cincinnati Reds", 0.19, bid=0.17, ask=0.21)])
        assert len(_search_surviving_legs(under)) == 2
        assert _futures_board_is_mostly_unserved(under) is True

    def test_the_ambiguous_band_above_the_threshold_is_left_alone(self):
        """747 markets sit in 0.50-0.97 and are NOT this ship's population."""
        for total in (0.55, 0.72, 0.88, 0.95):
            m = _Market([_Outcome(1, "Chicago Cubs", round(total - 0.10, 2),
                                  bid=0.01, ask=0.10),
                         _Outcome(2, "Cincinnati Reds", 0.10, bid=0.08, ask=0.12)])
            assert len(_search_surviving_legs(m)) == 2, total
            assert _futures_board_is_mostly_unserved(m) is False, total


class TestTheOneLegPopulationIsParkedNotFixed:
    """Precondition 2, stated as a deliberate remainder rather than an oversight.

    These are the OTHER ships' controls, reproduced here so that anyone who
    relaxes `_BOARD_MIN_SERVED_LEGS` to 1 sees exactly whose guards they are
    about to redden — #6676's coin-flip band and #6327's stored zeros — before
    they do it, rather than after CI tells them.
    """

    def test_6676s_coin_flip_band_controls_are_out_of_reach(self):
        for name, prob, bid, ask in [
            ("Boston Red Sox (First 5)", 0.485, 0.46, 0.51),
            ("Dodgers 100+ wins", 0.41, 0.38, 0.44),
        ]:
            m = _Market([_Outcome(1, name, prob, bid=bid, ask=ask)])
            assert len(_search_surviving_legs(m)) == 1
            assert prob < _BOARD_MIN_SERVED_SUM, "it IS under the threshold"
            assert _futures_board_is_mostly_unserved(m) is False, name
            assert _futures_card_has_no_answer(m) is False, name

    def test_6327s_stored_zero_card_survives_on_the_mass_test(self):
        """Two rungs, so precondition 2 passes — the `0 < sum` arm is what saves it."""
        m = _Market([_Outcome(1, "Longshot A", 0.0, ask=0.02),
                     _Outcome(2, "Longshot B", 0.0, ask=0.01)])
        assert len(_search_surviving_legs(m)) == _BOARD_MIN_SERVED_LEGS
        assert _futures_board_is_mostly_unserved(m) is False
        assert _build_search_top_outcomes(m, limit=5) != []

    def test_a_single_rung_fragment_is_knowingly_left_served(self):
        """The `9th Inning Winner` rows. REAL, and not fixed by this ship.

        Named so the remainder cannot be mistaken for a passing guard: this card
        is a defect, it is 243 markets, and it is indistinguishable at serve time
        from the two propositions above.
        """
        m = _Market([_Outcome(1, "Tampa Bay Rays", 0.08, bid=0.01, ask=0.15)],
                    name="Boston Red Sox vs. Tampa Bay Rays - 9th Inning Winner")
        assert _futures_board_is_mostly_unserved(m) is False
        assert len(_build_search_top_outcomes(m, limit=5)) == 1


class TestTheBinaryQuestionsThatMustSurvive:
    """The regression the reach measurement caught before it shipped."""

    def test_a_kalshi_yes_question_keeps_its_card(self):
        m = _Market(
            [_Outcome(1, "Yes", 0.041, bid=0.03, ask=0.05)],
            name="Will the Fed do a rate cut greater than 25bps this year?",
            source="kalshi",
        )
        assert _futures_board_is_mostly_unserved(m) is False
        assert _futures_card_has_no_answer(m) is False
        assert len(_build_search_top_outcomes(m, limit=5)) == 1

    def test_a_no_leg_is_the_same_question_from_the_other_side(self):
        m = _Market([_Outcome(1, "No", 0.036, bid=0.02, ask=0.05)])
        assert _futures_board_is_mostly_unserved(m) is False

    def test_mutually_exclusive_alone_would_not_have_saved_them(self):
        """Why precondition 2 is its own test and not folded into the flag.

        The column defaults True, so the honest binary above arrives wearing it
        and IS under the threshold. Only the two-rung rule saves it — relax
        `_BOARD_MIN_SERVED_LEGS` to 1 and this card is withdrawn.
        """
        m = _Market(
            [_Outcome(1, "Yes", 0.041, bid=0.03, ask=0.05)],
            name="Will the Fed do a rate cut greater than 25bps this year?",
        )
        assert m.mutually_exclusive is True
        assert sum(float(o.current_probability) for o in m.outcomes) < _BOARD_MIN_SERVED_SUM
        assert _futures_board_is_mostly_unserved(m) is False

    def test_surviving_is_not_the_same_set_as_priced(self):
        """Market 61307407 — the distinction the two `len()` tests turn on.

        "Will Canada become a European Union Association Member by December
        2027?" owns `Yes` and `No` rows, but only its `December 31, 2027` leg
        carries a price. `_search_surviving_legs` keeps all THREE (an unpriced
        leg is not a refused leg), while the predicate's two-rung test counts
        only the PRICED ones and finds a single rung.

        That is load-bearing in both directions: the truncation test reads the
        survivor count, so an unpriced row still consumes ladder depth, and the
        two-rung test reads the priced count, so unpriced rows can never pad a
        board into looking complete. Conflating them silently changes which
        markets this guard reaches.
        """
        m = _Market(
            [
                _Outcome(1, "December 31, 2027", 0.10, bid=0.11, ask=0.61),
                _Outcome(2, "Yes", None, bid=0.10, ask=0.66),
                _Outcome(3, "No", None, bid=0.34, ask=0.90),
            ],
            name="Will Canada become a European Union Association Member by Dec 2027?",
        )
        legs = _search_surviving_legs(m)
        assert [o.name for o in legs] == ["December 31, 2027", "Yes", "No"]
        assert len([o for o in legs if o.current_probability is not None]) == 1
        assert _futures_board_is_mostly_unserved(m) is False, (
            "parked by precondition 2: it SERVES one rung, whatever it owns"
        )


# ---------------------------------------------------------------------------
# 3. The boundary that matters most: served legs, not stored rows.
# ---------------------------------------------------------------------------


class TestItJudgesTheServedLadderNotTheStoredRows:
    def _livebench(self):
        """Market 57574860 as production holds it: 1 honest leg, 21 phantoms."""
        legs = [_Outcome(1, "Anthropic", 0.45, bid=0.43, ask=0.47)]
        legs += [
            _Outcome(i, f"Vendor {i}", 0.50, bid=0.01, ask=0.99)
            for i in range(2, 23)
        ]
        return _Market(legs, name="Which company has the best AI model on LiveBench?")

    def test_the_stored_rows_sum_to_eleven_and_look_perfectly_healthy(self):
        """The number a naive predicate would read. Stated so the test is not vacuous."""
        m = self._livebench()
        assert len(m.outcomes) == 22
        assert round(sum(float(o.current_probability) for o in m.outcomes), 2) == 10.95

    def test_but_the_card_draws_one_leg_at_45_percent(self):
        m = self._livebench()
        legs = _search_surviving_legs(m)
        assert [o.name for o in legs] == ["Anthropic"]

    def test_the_survivor_count_is_what_precondition_2_judges(self):
        """Reading `market.outcomes` would see 22 rungs; the card draws ONE.

        The predicate parks it for serving a lone rung — but it parks it on the
        SERVED count, not the stored one, and that is the distinction this class
        exists to pin. A predicate reading `market.outcomes` would compute 22
        legs summing 10.95 and wave the card through for the wrong reason.
        """
        m = self._livebench()
        assert len(_search_surviving_legs(m)) < _BOARD_MIN_SERVED_LEGS
        assert _futures_board_is_mostly_unserved(m) is False

    def test_the_empty_book_arm_cannot_claim_it_because_one_leg_is_honest(self):
        """#6676 stops one leg short; this guard is its complement, not its copy."""
        assert _futures_market_prices_only_empty_books(self._livebench()) is False


# ---------------------------------------------------------------------------
# 4. Structural guards: the two things that make the withdrawal true on the PAGE
#    rather than merely true in this file.
# ---------------------------------------------------------------------------


class TestTheWithdrawalReachesThePage:
    def test_ladder_limit_is_the_one_the_search_call_site_passes(self):
        """If these drift the guard silently changes population.

        `_futures_board_is_mostly_unserved` exempts a ladder longer than
        `_SEARCH_LADDER_LIMIT` as truncated. Should the card start drawing six
        rungs while the predicate still exempts at five, a six-rung broken board
        would be both drawn AND exempt.
        """
        src = inspect.getsource(_format_futures_for_search)
        assert "limit=_SEARCH_LADDER_LIMIT" in src
        assert _SEARCH_LADDER_LIMIT == 5

    def test_the_predicate_filters_both_the_flat_list_and_the_families(self):
        """A family is the back door a half-applied withdrawal leaves open.

        #3412's own comment says so. The union is asked twice in `search_events`
        — once for the flat `futures` list, once for the set the families
        compose from — and a card withdrawn from only the first walks straight
        back onto the page inside a family card.
        """
        tree = ast.parse(inspect.getsource(_events_module))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_futures_card_has_no_answer"
        ]
        assert len(calls) == 2, f"expected both filters, found {len(calls)}"

    def test_the_count_moves_with_the_card_it_withdraws(self):
        """🪤 Withholding on a LIST surface deletes the card; the count must follow.

        `more_count` renders as "+N more markets below" and is a promise about
        the page. It counts only ids in `serialized_ids`, and `search_events`
        builds that set from `futures_markets` — the list this predicate has
        already filtered — so a withdrawn board is uncounted by construction
        rather than by a second rule that could fall out of step.
        """
        composer = inspect.getsource(_events_module._compose_futures_families)
        assert "if m.id in serialized_ids" in composer
        route = inspect.getsource(_events_module.search_events)
        assert "{m.id for m in futures_markets}" in route
        assert "m for m in deduped_futures if not _futures_card_has_no_answer(m)" in route


# ---------------------------------------------------------------------------
# 6. Precondition 1 is load-bearing, and until #7144 measured the population
#    nothing in this suite could tell.
# ---------------------------------------------------------------------------


class TestPrecondition1HoldsTheHonestNonExclusiveBoards:
    """An honestly non-exclusive board that sums LOW — the case the docstring
    did not have and the suite could not see.

    🔴 MEASURED VACUOUS, 2026-09-19: severing `mutually_exclusive` out of
    `_futures_board_is_mostly_unserved` left **147 tests across 7 files green**,
    this file's 25 included. The one test that names the precondition,
    `test_a_non_exclusive_family_is_never_this_population`, hands it a ONE-LEG
    fixture — so precondition 2 returns first and the exclusivity arm is never
    reached. It asserts the right verdict for the wrong reason.

    The gap is not academic, because the docstring's stated justification does
    not survive either: #199's golf make-cut/top-N families sum to *several
    multiples of 100%*, and precondition 5 (`served < 0.50`) already excludes
    every one of them. Read together, a later reader is entitled to conclude
    precondition 1 is redundant and delete it.

    IT IS NOT REDUNDANT. #7144 enumerated all 273 open markets carrying
    `mutually_exclusive = False` with 2–5 priced legs summing under half, and
    they are honest cards of four shapes — independent player props, cumulative
    date and threshold ladders, multi-select boards, and nested boards. Every
    one sums low *and* is correctly non-exclusive, so precondition 5 cannot
    save them and precondition 1 is the only thing standing between them and
    withdrawal. The fixtures below are three of those rows, at their production
    values, and each one kills the mutant.
    """

    def test_a_player_props_bundle_is_not_a_board_to_be_incoherent_about(self):
        """Market 61285020, as production serves it: four props summing 32.5%.

        Independent propositions — several can hit — so the low sum asserts
        nothing false. #7144 filed this as a specimen of a mis-flagged
        exclusive board; the measurement showed the flag is correct, and it is
        one of EIGHT near-identical `- Player Props` bundles in the population.
        """
        m = _Market(
            [
                _Outcome(1, "Lamine Yamal to score", 0.115, bid=0.10, ask=0.13),
                _Outcome(2, "Robert Lewandowski to score", 0.09, bid=0.08, ask=0.10),
                _Outcome(3, "Raphinha to score", 0.07, bid=0.06, ask=0.08),
                _Outcome(4, "Pedri to score", 0.05, bid=0.04, ask=0.06),
            ],
            id=61285020,
            name="Sevilla FC vs. FC Barcelona - Player Props",
            mutually_exclusive=False,
        )
        legs = _search_surviving_legs(m)
        assert len(legs) == 4 <= _SEARCH_LADDER_LIMIT
        assert round(sum(float(o.current_probability) for o in legs), 3) == 0.325
        assert 0.325 < _BOARD_MIN_SERVED_SUM
        assert len(legs) >= _BOARD_MIN_SERVED_LEGS
        # Every other precondition is satisfied. Exclusivity is the only one
        # refusing it, which is precisely why severing that arm is not safe.
        assert _futures_board_is_mostly_unserved(m) is False
        assert _futures_card_has_no_answer(m) is False
        assert len(_build_search_top_outcomes(m, limit=5)) == 4

    def test_a_nested_board_is_not_a_fragment(self):
        """Market 60481869 — the leg names are why the flag is right.

        `American man or woman to win US Open` is the UNION of the two legs
        beside it. #7144 read its shape (3 legs, 3%) and called it an exclusive
        board serving a fragment; reading its legs shows a deliberately
        overlapping Kalshi board whose mass is honestly small.
        """
        m = _Market(
            [
                _Outcome(1, "American man or woman to win US Open", 0.01, bid=0.005, ask=0.02),
                _Outcome(2, "American woman to win US Open", 0.01, bid=0.005, ask=0.02),
                _Outcome(3, "American man to win US Open", 0.01, bid=0.005, ask=0.02),
            ],
            id=60481869,
            name="American to win the 2026 US Open?",
            source="kalshi",
            mutually_exclusive=False,
        )
        assert _futures_board_is_mostly_unserved(m) is False
        assert _futures_card_has_no_answer(m) is False

    def test_a_cumulative_date_ladder_keeps_its_card(self):
        """The largest shape in the population: 104 of the 273 are these.

        `When will X…?` rungs are cumulative windows, not alternatives, so a
        sum under half is the market saying the thing is unlikely — the single
        most common honest card this guard could have eaten.
        """
        m = _Market(
            [
                _Outcome(1, "by March 31", 0.02, bid=0.01, ask=0.03),
                _Outcome(2, "by June 30", 0.012, bid=0.008, ask=0.02),
                _Outcome(3, "by September 30", 0.012, bid=0.008, ask=0.02),
            ],
            id=113017,
            name="Will Tesla release Optimus by...?",
            mutually_exclusive=False,
        )
        assert _futures_board_is_mostly_unserved(m) is False
        assert _futures_card_has_no_answer(m) is False

    def test_the_precondition_is_reached_before_any_other_arm_can_answer(self):
        """The anti-vacuity assertion, and the reason this class exists.

        Each fixture above must fail EVERY other precondition's escape hatch,
        or it would pass for a reason that has nothing to do with exclusivity
        and the mutant would survive again. Asserted on the exclusive twin: the
        same rows with the flag flipped ARE withdrawn, so the flag — and
        nothing else — is what separates the two verdicts.
        """
        rows = [
            _Outcome(1, "Lamine Yamal to score", 0.115, bid=0.10, ask=0.13),
            _Outcome(2, "Robert Lewandowski to score", 0.09, bid=0.08, ask=0.10),
            _Outcome(3, "Raphinha to score", 0.07, bid=0.06, ask=0.08),
            _Outcome(4, "Pedri to score", 0.05, bid=0.04, ask=0.06),
        ]
        served = _Market(list(rows), mutually_exclusive=False)
        withdrawn = _Market(list(rows), mutually_exclusive=True)
        assert _futures_board_is_mostly_unserved(served) is False
        assert _futures_board_is_mostly_unserved(withdrawn) is True

    def test_a_truncated_field_is_why_the_flag_is_not_safe_to_rewrite(self):
        """Market 61151381, `Green Bay vs New York J: 1st Touchdown`.

        The one row in the 273 that IS exclusive in fact — one player scores
        first — flagged `False`. It is still not this guard's population: only
        4 of ~40 possible scorers are stored, so it is precondition 4's honest
        truncated ladder, and with 4 rows the truncation is INVISIBLE to a
        `> _SEARCH_LADDER_LIMIT` test.

        So "repair the flag to True" would make this guard withdraw an honest
        card. Kept as the standing counterexample to that repair.
        """
        rows = [
            _Outcome(1, "GB Packers D/ST", 0.05, bid=0.04, ask=0.06),
            _Outcome(2, "NY Jets D/ST", 0.05, bid=0.04, ask=0.06),
            _Outcome(3, "Adonai Mitchell", 0.025, bid=0.02, ask=0.03),
            _Outcome(4, "No Touchdown", 0.01, bid=0.005, ask=0.02),
        ]
        as_stored = _Market(list(rows), id=61151381, source="kalshi",
                            name="Green Bay vs New York J: 1st Touchdown",
                            mutually_exclusive=False)
        assert _futures_board_is_mostly_unserved(as_stored) is False
        # The harm the counterexample names, made explicit rather than asserted
        # in prose: flip the flag and the honest truncated field is withdrawn.
        as_repaired = _Market(list(rows), id=61151381, source="kalshi",
                              name="Green Bay vs New York J: 1st Touchdown",
                              mutually_exclusive=True)
        assert _futures_board_is_mostly_unserved(as_repaired) is True
