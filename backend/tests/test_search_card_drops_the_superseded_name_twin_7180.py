"""ONE QUESTION, ONE ROW — ON THE SEARCH CARD TOO. #7180.

═══ WHAT THE READER SAW ═══

`GET /api/events/search`, production rows of 2026-09-19, market 113039
(*Israel x Hamas ceasefire cancelled by...?*), ladder as served:

    December 31   16%
    March 31      0.2%
    June 30       0.1%
    October 31     -
    December 31    -      <- the same label again, and no number beside it

Market 61404610 (*Korea Open, Qualification: Mai Hontama vs Eun-Hye Lee*) prints
the same shape one row further up: `… Set Handicap +/-1.5  12.5%` directly above
`… Set Handicap +/-1.5  -`.

Detail has not printed this since #6508. The search card did, because the two
surfaces refuse different things.

═══ THE MECHANISM ═══

A candidate can be stored twice — a live leg and a prior cycle's leg the venue
has already graded a LOSS — under two DIFFERENT Polymarket condition ids. The
search path's dedup (`_drop_duplicate_legs`, keyed on `external_id`) folds rows
that share an id and therefore cannot see this pair at all. `_format_market_detail`
has run `drop_superseded_name_twins` beside it since #6508; `_search_surviving_legs`
did not, which is #993's drift (the click-through must match what search showed)
arriving on a second function.

The fix is the same helper, in the same chain position, in `_search_surviving_legs`
— so the card's ladder, the typeahead dropdown and the count badge all move
together, because #5516 made them read one list and #6585 made the badge count it.

═══ THE POPULATION, MEASURED BEFORE THE FIX ═══

Not the boards the issue named — every open market. One query over
`futures_outcomes` × open `futures_markets` (2026-09-19) returns **7 rows on 6
boards**, every one priced `0.000000`:

    112914    Will Russia capture Lyman by...?            December 31
    112938    Who will Trump nominate as Fed Chair?       James Bullard, Rick Rieder
    113039    Israel x Hamas ceasefire cancelled by...?   December 31
    113040    Israel x Hamas Ceasefire Phase II by...?    December 31
    113486    Will Zelenskyy talk to Putin by...?         December 31
    61404610  Korea Open … Mai Hontama vs Eun-Hye Lee     … Set Handicap +/-1.5

Driving the real `_search_surviving_legs` and `_build_search_top_outcomes` on
those boards' production rows, before and after:

    board      badge before -> after    board serves    ladder moves?
    112914          10    ->   9              9         no
    112938          27    ->  25             25         no  (#7180's headline)
    113039           7    ->   6              6         YES
    113040           8    ->   7              7         no
    113486           6    ->   5              5         no
    61404610         4    ->   3              3         YES

Six of six now equal the number `/api/futures/{id}` serves. Two move the ladder,
which is the half #7180 was filed to measure rather than assume, and both are
the defect above disappearing.

═══ WHY THE DROP IS PRE-SLICE ═══

On 113039 the freed fifth slot is taken by `November 30` — an honest rung that
was truncated away by a row the reader could not read. A post-slice drop would
have left a four-row ladder and buried the rung anyway. On the four-leg Korea
Open board the ladder simply ends at three, because there is no sixth rung to
promote; that is the honest answer and the test asserts we do not invent one.

═══ WHAT THIS FILE PINS THAT THE FIX ALONE DOES NOT ═══

The helper's three guards are tested on the helper. What is tested HERE is that
this call site passes them through intact — above all `is_winner_of=lambda o:
o.is_winner` and not `bool(o.is_winner)`, which would turn an UNGRADED row into
a graded loss and delete it. That spelling has no live population today (a
production query for settled-but-ungraded twins on open markets returns 0 rows),
so `test_a_settled_but_ungraded_twin_survives` is a control protecting a rule,
not a reproduction of a live defect — and it is the test that fails the moment
someone "simplifies" the accessor to match the `_drop_unbacked_legs` line
directly beneath it, which does spell it `bool(...)` and is correct to.

═══ NOT VACUOUS ═══

Every fixture below carries the duplicate label in its raw rows and each test
asserts that BEFORE state explicitly, so a fixture that lost its twin in a later
edit fails loudly instead of passing on nothing.

Mutation check (run, not asserted — applied, measured, reverted), counted across
this file and #6585's together, 29 tests:

* remove the `drop_superseded_name_twins` call from `_search_surviving_legs`
  -> **9 fail** (7 here, 2 in #6585's file). The 20 survivors are the guards and
  the controls, which are true either way and are here to say so.
* spell the grade accessor `bool(o.is_winner)` instead of `o.is_winner`
  -> **1 fails**, `test_a_settled_but_ungraded_twin_survives`, which is the only
  test that can see that mutant and the reason it is written.
"""

from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _format_futures_for_search,
    _search_surviving_legs,
)


class _Outcome:
    """The attributes the search survivor chain reads off an ORM outcome row."""

    def __init__(self, oid, name="Leg", prob=None, bid=None, ask=None, ext=None,
                 winner=False, resolution_source=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = bid
        self.current_yes_ask = ask
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}" if ext is None else ext
        self.is_winner = winner
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 113039)
        self.name = kw.get("name", "Israel x Hamas ceasefire cancelled by...?")
        self.sport = None
        self.category = kw.get("category", "politics")
        self.llm_sport_category = "politics"
        self.market_tier = kw.get("market_tier", 5)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "polymarket")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", False)


def _names(market):
    return [o.name for o in _search_surviving_legs(market)]


def _ladder(market, lean=False):
    rows = _build_search_top_outcomes(
        market, limit=_SEARCH_LADDER_LIMIT, lean=lean, withheld=None
    )
    return [r.get("name") for r in rows]


def _badge(market):
    return _format_futures_for_search(market, None)["outcome_count"]


def _stored_label_count(market, label):
    """The BEFORE every test states: the twin really is in the fixture's rows."""
    return len([o for o in market.outcomes if o.name == label])


# ---------------------------------------------------------------------------
# Production-valued fixtures. Ten rows and four rows, verbatim — including the
# full condition ids, because two of this file's refusals key on them and an
# abbreviated id quietly builds a board production does not serve.
# ---------------------------------------------------------------------------


_NOV_COND = "0x1161a32141bb18119d627d6747f1cec4f7de6aeed15abad0e6b1aa8af3b1a844"


def _ceasefire_board():
    """Market 113039, all ten stored rows as of 2026-09-19.

    `December 31` twice: `187270804` live at 0.16 on 0.15/0.17, and `69760067`
    graded a loss at 0.000000 on an ask of 0.0010.
    """
    return _Market(
        [
            _Outcome(1627090, "June 30", 0.001, bid=None, ask=0.001,
                     ext="0x26ebe9f65bd68ddedda46fd178b35f849aae4607e1265df3ef7243f99829f195", resolution_source="api_settlement"),
            _Outcome(1627091, "March 31", 0.002, bid=None, ask=0.001,
                     ext="0x22cb289f07f3da4d3525f1c3944010a05c77d21ecf451719959ae54d24edcdb3", resolution_source="api_settlement"),
            _Outcome(69760066, "October 31", 0.0, bid=None, ask=0.002,
                     ext="0x962c76d11abf9d8ef448281d25f3b8678d54866234a960f0f6e8879c7ae12f2b", resolution_source="api_settlement"),
            _Outcome(69760067, "December 31", 0.0, bid=None, ask=0.001,
                     ext="0xbc19cb5c84d57f2fed2b089a1634d63d7ad608da3100f5006c00782db44453d1", resolution_source="api_settlement"),
            _Outcome(69760068, "November 30", 0.0, bid=None, ask=0.001,
                     ext=_NOV_COND, resolution_source="api_settlement"),
            _Outcome(69760069, "November 7", 0.0, bid=None, ask=0.001,
                     ext="0xfb9bb7bbab546a435381651637260adab3563943a37b6d47e0de437ec4877d3f", resolution_source="api_settlement"),
            _Outcome(69760070, "January 31", 1.0, bid=0.0, ask=1.0, ext=""),
            # Q480, verbatim: the `November 30` condition also stores its own
            # `_yes`/`_no` legs. The SUFFIX is the whole mechanism — abbreviate
            # these ids and `_drop_duplicate_legs` stops folding them, which is a
            # fixture drawing a board production does not serve.
            _Outcome(84286572, "Yes", 1.0, bid=None, ask=0.001,
                     ext=_NOV_COND + "_yes"),
            _Outcome(84286573, "No", 1.0, bid=None, ask=None,
                     ext=_NOV_COND + "_no"),
            _Outcome(187270804, "December 31", 0.16, bid=0.15, ask=0.17,
                     ext="0x12bd7c63ea356a688c47c5227ef490c63b04354bf2ec8cb7e2aed84968c4c648"),
        ],
        id=113039,
        name="Israel x Hamas ceasefire cancelled by...?",
    )


_HANDICAP = "Korea Open, Qualification: Mai Hontama vs Eun-Hye Lee Set Handicap +/-1.5"


def _korea_open_board():
    """Market 61404610, all four stored rows. The twin sits at rank 4 of 4.

    Note the live rows carry `is_winner = None` (ungraded), which is the normal
    state of an open tennis prop — the graded twin is the exception.
    """
    return _Market(
        [
            _Outcome(231176649, "Mai Hontama", 0.785, bid=0.78, ask=0.79,
                     ext="0xf6e5694a903d", winner=None),
            _Outcome(231283831, _HANDICAP, 0.0, bid=0.55, ask=0.58,
                     ext="0xfa30bf6648cc", resolution_source="api_settlement"),
            _Outcome(231283832,
                     "Korea Open, Qualification: Mai Hontama vs Eun-Hye Lee "
                     "Total Sets: O/U 2.5",
                     0.32, bid=None, ask=1.0, ext="0x3f62fe19e825", winner=None),
            _Outcome(231283833, _HANDICAP, 0.125, bid=0.11, ask=0.14,
                     ext="0x873d58a90e85", winner=None),
        ],
        id=61404610,
        name="Korea Open, Qualification: Mai Hontama vs Eun-Hye Lee",
        category="tennis",
    )


# ---------------------------------------------------------------------------
# 1. The reader-visible half: the label stops appearing twice.
# ---------------------------------------------------------------------------


class TestTheLadderStopsPrintingOneLabelTwice:
    def test_the_repeated_date_inside_the_slice_is_gone(self):
        m = _ceasefire_board()
        assert _stored_label_count(m, "December 31") == 2, "fixture lost its twin"

        ladder = _ladder(m)
        assert ladder.count("December 31") == 1, (
            "the graded-loss leg was drawn at rank 5 with no number beside it"
        )
        assert "December 31" in ladder, "the LIVE leg is the one that stays"

    def test_the_freed_slot_goes_to_an_honest_rung_not_to_a_shorter_ladder(self):
        """The whole argument for dropping BEFORE the `[:limit]` slice."""
        m = _ceasefire_board()
        ladder = _ladder(m)
        assert len(ladder) == _SEARCH_LADDER_LIMIT
        assert ladder[-1] == "November 30", (
            "a rung that existed all along and was truncated away by the twin"
        )

    def test_a_short_board_ends_honestly_instead_of_inventing_a_filler(self):
        m = _korea_open_board()
        assert _stored_label_count(m, _HANDICAP) == 2, "fixture lost its twin"

        ladder = _ladder(m)
        assert ladder.count(_HANDICAP) == 1
        assert len(ladder) == 3, (
            "four legs, one of them superseded, and no fifth rung to promote"
        )

    def test_the_typeahead_dropdown_gets_the_same_ladder(self):
        """#993: the two surfaces read one list, so they cannot disagree."""
        m = _ceasefire_board()
        assert _ladder(m, lean=True).count("December 31") == 1


# ---------------------------------------------------------------------------
# 2. The count half: the badge lands on the board's number.
# ---------------------------------------------------------------------------


class TestTheBadgeNamesTheBoard:
    def test_the_ceasefire_card_badges_six(self):
        m = _ceasefire_board()
        assert _badge(m) == 6, "the number `/api/futures/113039` serves"

    def test_the_korea_open_card_badges_three(self):
        m = _korea_open_board()
        assert _badge(m) == 3, "the number `/api/futures/61404610` serves"

    def test_the_badge_still_counts_exactly_what_the_ladder_draws_from(self):
        """#6585's contract, re-asserted on this issue's fixtures."""
        for m in (_ceasefire_board(), _korea_open_board()):
            assert _badge(m) == len(_search_surviving_legs(m))


# ---------------------------------------------------------------------------
# 3. The guards, as this CALL SITE passes them. Each one is a population the
#    drop must not touch, and each test names what a wrong accessor deletes.
# ---------------------------------------------------------------------------


class TestTheCallSitePassesTheGuardsIntact:
    def test_a_settled_but_ungraded_twin_survives(self):
        """`is_winner is False`, never `bool(o.is_winner)`.

        `None` means the venue settled the market and this leg has no verdict
        recorded. Under a `bool(...)` accessor it reads as a loss and the row is
        deleted — a real answer removed on a missing grade. No live population
        today (measured 0); this is the control that keeps it that way.
        """
        m = _Market([
            _Outcome(1, "December 31", 0.16, bid=0.15, ask=0.17, ext="0xlive"),
            _Outcome(2, "December 31", 0.04, bid=0.03, ask=0.05, ext="0xungraded",
                     winner=None, resolution_source="api_settlement"),
        ])
        assert _stored_label_count(m, "December 31") == 2
        assert _names(m).count("December 31") == 2, (
            "an ungraded row is not a superseded one"
        )

    def test_a_settled_winner_is_never_dropped(self):
        """Settled means settled — a graded WIN is a result, not a duplicate."""
        m = _Market([
            _Outcome(1, "December 31", 0.16, bid=0.15, ask=0.17, ext="0xlive"),
            _Outcome(2, "December 31", 1.0, bid=0.99, ask=1.0, ext="0xwon",
                     winner=True, resolution_source="api_settlement"),
        ])
        assert _names(m).count("December 31") == 2

    def test_an_all_settled_group_is_left_alone(self):
        """No unsettled anchor means we cannot tell which result belongs where.

        Two graded rungs under two tickers: dropping either attaches a real
        result to the wrong question.
        """
        m = _Market([
            _Outcome(1, "Josh Hoover", 0.0, bid=None, ask=0.01, ext="0xa",
                     resolution_source="api_settlement"),
            _Outcome(2, "Josh Hoover", 0.0, bid=None, ask=0.01, ext="0xb",
                     resolution_source="api_settlement"),
        ])
        assert _stored_label_count(m, "Josh Hoover") == 2
        assert _names(m).count("Josh Hoover") == 2

    def test_an_anchor_with_no_venue_id_cannot_supersede_anything(self):
        """An unbacked row is not a quote, so it is not what a row is superseded BY.

        Without this guard the priced-and-graded row goes and the reader is left
        looking at the fabricated `1.0` alone — strictly worse than the duplicate
        (#6524's boards 113545 and 114237).
        """
        m = _Market([
            _Outcome(1, "May 31", 1.0, bid=None, ask=None, ext=""),
            _Outcome(2, "May 31", 0.02, bid=0.01, ask=0.03, ext="0xreal",
                     resolution_source="api_settlement"),
        ])
        assert _names(m).count("May 31") == 1, (
            "the unbacked row is dropped by #6524, and it never superseded the "
            "priced one"
        )
        assert _search_surviving_legs(m)[0].external_id == "0xreal"


# ---------------------------------------------------------------------------
# 4. The fix is the shared helper, at the seam, and not a copy of it.
# ---------------------------------------------------------------------------


class TestTheFixIsTheSharedHelperAtTheSeam:
    def test_the_survivor_chain_calls_the_shared_drop(self):
        """A re-derivation here would pass today and drift from detail tomorrow.

        That drift IS #7180: the detail route grew the rule in #6508 and this
        path did not inherit it for eleven days.
        """
        import inspect

        src = inspect.getsource(_search_surviving_legs)
        body = src.split('"""', 2)[-1]
        assert "_drop_superseded_name_twins(" in body
        assert "resolution_source" not in body.replace(
            "resolution_source_of=lambda o: o.resolution_source", ""
        ), "the correspondence rule belongs to the helper, not to this call site"

    def test_the_detail_route_and_search_share_one_implementation(self):
        from app.utils.superseded_name_twins import drop_superseded_name_twins

        from app.routes.events import (
            _drop_superseded_name_twins as search_side,
        )

        assert search_side is drop_superseded_name_twins
