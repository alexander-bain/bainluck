"""A SEARCH CARD SHOWS ONLY THE ROWS IT HAS A NUMBER FOR. #9904.

`/search?q=ohtani`, production, 2026-09-30 18:1xZ, 390px: *MLB Championship
Series MVP Winner* (kalshi 62952889, exclusive, 98 legs, 1 priced) drew

    1  Aaron Judge       18%
    2  Shohei Ohtani     –
    3  Freddie Freeman   –
    4  Blake Snell       –
    5  Gerrit Cole       –

The builder's probability sort reads NULL as 0, so the four-row tail filled with
unpriced legs, each with a rank implying an order nobody priced. At 20:1xZ the
same card read `Ohtani 17% · Judge 9%` and three dashes: two priced legs, same
defect.

A board with at least one priced leg now draws only priced legs. Graded results
stay, and #6993's withheld legs stay nulled.

WHAT THIS DOES NOT DO: withdraw a card left holding ONE priced leg. The issue
proposed it; #6327's shipped control
(`test_one_priced_rung_among_fifteen_nulls_keeps_the_card`, Sonmez 31% over 15
unpriced legs) and #5516's precondition 2 ("a lone number is a proposition")
both rule that card stays, and `?q=sonmez` would lose the one answer to its own
query. So `Judge 18%` is served alone. `TestALoneLegIsServedNotWithdrawn` pins
that from this side.

Controls: a fully priced board and a wholly unpriced one (#6327) serve exactly
what they served before.
"""

from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _futures_board_is_mostly_unserved,
    _futures_card_has_no_answer,
    _futures_market_is_wholly_unpriced,
    _search_surviving_legs,
)


class _Outcome:
    """The attributes the search builder reads off an ORM outcome row."""

    def __init__(self, oid, name, prob=None, *, is_winner=False, resolution_source=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}"
        self.is_winner = is_winner
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 62952889)
        self.name = kw.get("name", "MLB Championship Series MVP Winner")
        self.sport = None
        self.category = kw.get("category", "championship")
        self.llm_sport_category = "baseball"
        self.market_tier = 3
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = "kalshi"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", True)


_FIELD = ["Shohei Ohtani", "Freddie Freeman", "Blake Snell", "Gerrit Cole",
          "Kyle Teel", "Jackson Chourio", "Christian Yelich", "Mookie Betts"]


def _board(priced: list[tuple[str, float]], unpriced: int, **kw) -> _Market:
    legs = [_Outcome(i + 1, n, p) for i, (n, p) in enumerate(priced)]
    for j in range(unpriced):
        oid = len(legs) + 1
        legs.append(_Outcome(oid, _FIELD[j] if j < len(_FIELD) else f"Player {oid}"))
    return _Market(legs, **kw)


def _specimen_1813z():
    """62952889 as the issue measured it: Judge 0.175, 97 unpriced legs."""
    return _board([("Aaron Judge", 0.175)], 97)


def _specimen_2014z():
    """The same market two hours later: Ohtani 0.1675, Judge 0.0905, 96 unpriced."""
    return _board([("Shohei Ohtani", 0.1675), ("Aaron Judge", 0.0905)], 96)


def _names(rows):
    return [r["name"] for r in rows]


class TestTheSpecimenReachesTheDefect:
    """The strawman: the fixture draws production's dashes under the old sort."""

    def test_the_old_sort_fills_the_tail_with_unpriced_legs(self):
        for m, dashes in [(_specimen_1813z(), 4), (_specimen_2014z(), 3)]:
            legs = _search_surviving_legs(m)
            old_top = sorted(legs, key=lambda o: o.current_probability or 0, reverse=True)
            old_top = old_top[:_SEARCH_LADDER_LIMIT]
            assert sum(o.current_probability is None for o in old_top) == dashes

    def test_neither_older_arm_answers_the_specimen(self):
        """So the defect was reachable: #6327 and #5516 both pass it through."""
        m = _specimen_1813z()
        assert _futures_market_is_wholly_unpriced(m) is False
        assert _futures_board_is_mostly_unserved(m) is False


class TestAPricedBoardDrawsOnlyPricedRows:
    def test_two_priced_legs_draw_two_rows_and_no_dash(self):
        m = _specimen_2014z()
        out = _build_search_top_outcomes(m, limit=_SEARCH_LADDER_LIMIT)
        assert _names(out) == ["Shohei Ohtani", "Aaron Judge"]
        assert all(r["probability"] is not None for r in out)
        assert _futures_card_has_no_answer(m) is False

    def test_the_dropdown_draws_the_same_rows(self):
        m = _specimen_2014z()
        out = _build_search_top_outcomes(m, limit=3, lean=True)
        assert _names(out) == ["Shohei Ohtani", "Aaron Judge"]

    def test_a_stored_zero_is_a_price_and_stays(self):
        """#6195: `0.0` prints `0%`; only NULL is dropped."""
        m = _board([("Aaron Judge", 0.6), ("Cal Raleigh", 0.0)], 5)
        out = _build_search_top_outcomes(m, limit=5)
        assert _names(out) == ["Aaron Judge", "Cal Raleigh"]
        assert out[1]["probability"] == 0.0

    def test_a_graded_leg_stays_whatever_its_price(self):
        """Settled means settled: a graded result prints a result, not a dash."""
        m = _Market(
            [
                _Outcome(1, "Milwaukee Brewers", 0.6),
                _Outcome(2, "Los Angeles Dodgers", None, is_winner=True,
                         resolution_source="api_settlement"),
                _Outcome(3, "Colorado Rockies", None),
            ],
            name="Team to advance to NLDS",
            mutually_exclusive=False,
        )
        out = _build_search_top_outcomes(m, limit=5)
        assert _names(out) == ["Milwaukee Brewers", "Los Angeles Dodgers"]

    def test_a_withheld_leg_on_a_short_ladder_stays_nulled(self):
        """#6993's ruling is unchanged: a refused price is nulled, not dropped."""
        m = _board([("Aaron Judge", 0.6), ("Cal Raleigh", 0.3)], 3)
        out = _build_search_top_outcomes(m, limit=5, withheld={2})
        assert _names(out) == ["Aaron Judge", "Cal Raleigh"]
        assert out[1]["probability"] is None


class TestALoneLegIsServedNotWithdrawn:
    def test_the_1813z_specimen_draws_judge_alone_on_both_surfaces(self):
        m = _specimen_1813z()
        assert _futures_card_has_no_answer(m) is False
        out = _build_search_top_outcomes(m, limit=5)
        assert _names(out) == ["Aaron Judge"]
        assert out[0]["probability"] == 0.175
        assert _names(_build_search_top_outcomes(m, limit=3, lean=True)) == ["Aaron Judge"]

    def test_6327s_control_shape_keeps_its_card(self):
        """Sonmez 31% over 15 unpriced legs: the queried player's own number."""
        m = _board([("Zeynep Sonmez", 0.31)], 15, name="WTA Guadalajara Winner")
        assert _futures_card_has_no_answer(m) is False
        assert _names(_build_search_top_outcomes(m, limit=5)) == ["Zeynep Sonmez"]

    def test_a_non_exclusive_board_draws_its_priced_leg_alone(self):
        m = _board([("Aaron Judge", 0.175)], 97, mutually_exclusive=False)
        assert _names(_build_search_top_outcomes(m, limit=5)) == ["Aaron Judge"]


class TestControlsKeepTodaysOutput:
    def test_a_fully_priced_board_is_unchanged(self):
        priced = [("Aaron Judge", 0.30), ("Cal Raleigh", 0.25), ("Juan Soto", 0.20),
                  ("Bobby Witt Jr.", 0.12), ("Jose Ramirez", 0.08), ("Julio Rodriguez", 0.05)]
        m = _board(priced, 0)
        out = _build_search_top_outcomes(m, limit=5)
        assert all(r["probability"] is not None for r in out)
        assert _names(out) == [n for n, _ in priced[:5]]
        assert _futures_card_has_no_answer(m) is False

    def test_a_wholly_unpriced_board_is_still_6327s(self):
        m = _board([], 16)
        assert _futures_market_is_wholly_unpriced(m) is True
        assert _build_search_top_outcomes(m, limit=5) == []
        assert _futures_card_has_no_answer(m) is True
