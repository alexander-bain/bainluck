"""#10024 — `chiefs super bowl` shows the Super Bowl board WITH the Chiefs on it.

#10030 made the query reach `NFL Super Bowl Winner` (the split arms: `super bowl`
in the market name, `chiefs` in one leg). Production's card at 390px
(2026-10-01 ~10:00Z) then showed Bills, Rams, 49ers, Ravens, Seahawks: the team
the reader typed was nowhere. #8842's pin asked the leg to spell EVERY query
term, and "Kansas City Chiefs" does not spell `super bowl`. The leg now names
the terms the market name does not carry.

Prices are illustrative; each test states the property it depends on (the
Chiefs rank below the fifth row).
"""

from __future__ import annotations

from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _search_query_matched_leg,
)

CHIEFS_SUPER_BOWL = [("chiefs", None), ("super", None), ("bowl", None)]


class _Outcome:
    def __init__(self, oid, name, prob):
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
        self.is_winner = None
        self.resolution_source = None


class _Market:
    def __init__(self, id, name, outcomes):
        self.id = id
        self.name = name
        self.outcomes = outcomes
        self.sport = None
        self.category = "sports"
        self.llm_sport_category = "football"
        self.market_tier = 1
        self.market_type = None
        self.status = "open"
        self.source = "polymarket"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = True
        self.external_id = None


def _super_bowl():
    names = ["Buffalo Bills", "Los Angeles Rams", "San Francisco 49ers",
             "Baltimore Ravens", "Seattle Seahawks", "Philadelphia Eagles",
             "Detroit Lions", "Kansas City Chiefs", "Green Bay Packers"]
    probs = [0.11, 0.105, 0.08, 0.079, 0.07, 0.065, 0.06, 0.055, 0.05]
    return _Market(86832, "NFL Super Bowl Winner",
                   [_Outcome(i + 1, n, p) for i, (n, p) in enumerate(zip(names, probs))])


def _card(market, terms, lean=False, limit=_SEARCH_LADDER_LIMIT):
    return _build_search_top_outcomes(
        market, limit=limit, lean=lean, withheld=None, query_terms=terms
    )


def test_precondition_the_chiefs_are_below_the_cut_without_the_query():
    names = [r["name"] for r in _card(_super_bowl(), None)]
    assert "Kansas City Chiefs" not in names and len(names) == 5


def test_the_chiefs_are_on_the_super_bowl_card_at_their_real_place():
    rows = _card(_super_bowl(), CHIEFS_SUPER_BOWL)
    assert len(rows) == _SEARCH_LADDER_LIMIT
    pinned = rows[-1]
    assert pinned["name"] == "Kansas City Chiefs"
    assert pinned["query_match"] is True
    assert pinned["matched_rank"] == 8  # eighth on the board, not row 5


def test_the_typeahead_dropdown_carries_it_too():
    rows = _card(_super_bowl(), CHIEFS_SUPER_BOWL, lean=True, limit=3)
    assert rows[-1]["name"] == "Kansas City Chiefs"


def test_a_query_the_name_carries_in_full_is_untouched():
    assert _search_query_matched_leg(
        _super_bowl(), _super_bowl().outcomes, [], [("super", None), ("bowl", None)], set()
    ) is None


def test_the_leg_must_name_the_whole_remainder():
    """`kansas chiefs super bowl`: the remainder is `kansas` AND `chiefs`, so a
    leg spelling only one of them is not pinned."""
    m = _super_bowl()
    m.outcomes[7].name = "Kansas State"
    terms = [("kansas", None), ("chiefs", None), ("super", None), ("bowl", None)]
    assert "Kansas State" not in [r["name"] for r in _card(m, terms)]


def test_a_team_already_on_the_card_is_not_pinned_again():
    """`bills super bowl`: the Bills lead the card, so the card is unchanged."""
    rows = _card(_super_bowl(), [("bills", None), ("super", None), ("bowl", None)])
    assert not any(r.get("query_match") for r in rows)
    assert [r["name"] for r in rows] == [r["name"] for r in _card(_super_bowl(), None)]
