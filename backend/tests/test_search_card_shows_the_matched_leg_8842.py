"""#8842 — a card recalled through an outcome name shows that outcome.

`bainluck.com/search?q=ohtani` (390px, 2026-09-26 ~15:15Z) served seven market
cards and on four of them Ohtani appeared nowhere: `MLB: Home Runs Leader`
(12516244) showed Schwarber, Crow-Armstrong, Alonso, Caminero, Goodman. Search
recalled the market through its Ohtani outcome, then `_build_search_top_outcomes`
cut the card to the top five by probability without looking at the query.
`?q=yankees` did the same to `MLB: Team to make postseason` (8861163), whose
Yankees leg is a settled winner.

Names and ids are the production specimens'; the prices are illustrative, and
each test states the only property it depends on (the matched leg ranks below
the fifth row).
"""

from __future__ import annotations

from pathlib import Path

from app.routes import events as events_route
from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _format_futures_for_search,
)

OHTANI = [("ohtani", None)]
YANKEES = [("yankees", None)]


class _Outcome:
    def __init__(self, oid, name, prob, winner=None, resolution_source=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = max(prob - 0.01, 0.0)
        self.current_yes_ask = min(prob + 0.01, 1.0)
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}"
        self.is_winner = winner
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, id, name, outcomes, mutually_exclusive=True, status="open"):
        self.id = id
        self.name = name
        self.outcomes = outcomes
        self.sport = None
        self.category = "sports"
        self.llm_sport_category = "baseball_mlb"
        self.market_tier = 2
        self.market_type = None
        self.status = status
        self.source = "kalshi"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = mutually_exclusive
        self.external_id = None


def _hr_leaders():
    names = ["Kyle Schwarber", "Pete Crow-Armstrong", "Pete Alonso",
             "Junior Caminero", "Nick Goodman", "Cal Raleigh", "Shohei Ohtani",
             "Aaron Judge"]
    probs = [0.30, 0.20, 0.15, 0.12, 0.08, 0.05, 0.03, 0.02]
    return _Market(12516244, "MLB: Home Runs Leader",
                   [_Outcome(i + 1, n, p) for i, (n, p) in enumerate(zip(names, probs))])


def _postseason():
    rows = [("Los Angeles Dodgers", 1.0, True), ("Houston Astros", 0.9, None),
            ("Philadelphia Phillies", 0.88, None), ("Arizona Diamondbacks", 0.6, None),
            ("Texas Rangers", 0.55, None), ("Seattle Mariners", 0.5, None),
            ("New York Yankees", 1.0, True)]
    return _Market(8861163, "MLB: Team to make postseason", [
        _Outcome(i + 1, n, p, winner=w, resolution_source="kalshi" if w else None)
        for i, (n, p, w) in enumerate(rows)
    ], mutually_exclusive=False)


def _card(market, terms, lean=False, limit=_SEARCH_LADDER_LIMIT, withheld=None):
    return _build_search_top_outcomes(
        market, limit=limit, lean=lean, withheld=withheld, query_terms=terms
    )


def test_precondition_ohtani_is_below_the_cut_without_the_query():
    names = [r["name"] for r in _card(_hr_leaders(), None)]
    assert "Shohei Ohtani" not in names and len(names) == 5


def test_ohtani_is_on_the_home_runs_card():
    rows = _card(_hr_leaders(), OHTANI)
    assert [r["name"] for r in rows] == [
        "Kyle Schwarber", "Pete Crow-Armstrong", "Pete Alonso", "Junior Caminero",
        "Shohei Ohtani",
    ]
    pinned = rows[-1]
    assert pinned["query_match"] is True
    assert pinned["matched_rank"] == 7  # its place on the board, not row 5
    assert pinned["probability"] == 0.03
    assert not any(r.get("query_match") for r in rows[:-1])


def test_the_card_does_not_grow():
    assert len(_card(_hr_leaders(), OHTANI)) == _SEARCH_LADDER_LIMIT


def test_precondition_the_yankees_are_below_the_cut_without_the_query():
    assert "New York Yankees" not in [r["name"] for r in _card(_postseason(), None)]


def test_a_settled_team_leg_is_pinned_with_its_result():
    rows = _card(_postseason(), YANKEES)
    pinned = [r for r in rows if r["name"] == "New York Yankees"]
    assert len(pinned) == 1
    assert pinned[0]["is_winner"] is True and pinned[0]["resolution_source"] == "kalshi"


def test_already_inside_the_cut_is_not_duplicated():
    rows = _card(_hr_leaders(), [("schwarber", None)])
    names = [r["name"] for r in rows]
    assert names.count("Kyle Schwarber") == 1
    assert not any(r.get("query_match") for r in rows)
    assert names == [r["name"] for r in _card(_hr_leaders(), None)]


def test_a_title_matched_card_is_untouched():
    # `home runs` is in the market name: the card is ABOUT the query already.
    m = _hr_leaders()
    m.outcomes[6].name = "Home Runs Hitter X"
    assert [r["name"] for r in _card(m, [("home", None), ("runs", None)])] == [
        r["name"] for r in _card(_hr_leaders(), None)
    ]


def test_a_withheld_matched_leg_is_not_pinned():
    rows = _card(_hr_leaders(), OHTANI, withheld={7})
    assert "Shohei Ohtani" not in [r["name"] for r in rows]


def test_an_unpriced_matched_leg_is_not_pinned():
    m = _hr_leaders()
    m.outcomes[6].current_probability = None
    assert "Shohei Ohtani" not in [r["name"] for r in _card(m, OHTANI)]


def test_the_expansion_counts_like_the_term():
    rows = _card(_hr_leaders(), [("sho", "shohei")])
    assert rows[-1]["name"] == "Shohei Ohtani"


def test_the_typeahead_dropdown_carries_it_too():
    rows = _card(_hr_leaders(), OHTANI, lean=True, limit=3)
    assert [r["name"] for r in rows] == ["Kyle Schwarber", "Pete Crow-Armstrong", "Shohei Ohtani"]
    assert "query_match" not in rows[-1]  # lean rows stay lean


def test_the_search_formatter_passes_the_terms_through():
    card = _format_futures_for_search(_hr_leaders(), None, query_terms=OHTANI)
    assert card["top_outcomes"][-1]["name"] == "Shohei Ohtani"


def test_no_terms_is_the_old_card_exactly():
    assert _card(_hr_leaders(), None) == _build_search_top_outcomes(
        _hr_leaders(), limit=_SEARCH_LADDER_LIMIT, lean=False, withheld=None
    )


def test_both_handlers_hand_over_their_terms():
    src = Path(events_route.__file__).read_text()
    assert "m, _withheld_by_market.get(m.id), query_terms=expanded  # #8842" in src
    assert "query_terms=ta_expanded,  # #8842" in src
