"""#10279 — a row recalled through an outcome name LEADS with that outcome.

Production 2026-10-03 03:58Z, `judge` at 390px: the dropdown showed *MLB The Show
27: Cover Athlete* (24014885) as "Matt Olson 21% · Bryan Woo 16%". Aaron Judge, the
leg the row was recalled through, is seventh on the board at 9%. #8842 pinned him,
but into row 3 of 3, and the dropdown prints two rows
(`searchSuggestionDisplay.ts::futuresAnswer`) while the iPhone search row prints one
(`topOutcomes.first`). The web results card sorts leader-first on the client, so it
is unchanged whichever row the server puts him in.

Id, name and Judge's place and price come from the production row. The other legs'
prices are illustrative.
"""

from __future__ import annotations

from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _format_futures_for_search,
)

JUDGE = [("judge", None)]


class _Outcome:
    def __init__(self, oid, name, prob, winner=None, resolution_source=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None if prob is None else max(prob - 0.01, 0.0)
        self.current_yes_ask = None if prob is None else min(prob + 0.01, 1.0)
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}"
        self.is_winner = winner
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, id, name, legs, mutually_exclusive=True, status="open",
                 category="sports"):
        self.id = id
        self.name = name
        self.outcomes = [_Outcome(i + 1, *leg) for i, leg in enumerate(legs)]
        self.sport = None
        self.category = category
        self.llm_sport_category = "baseball_mlb"
        self.market_tier = 5
        self.market_type = None
        self.status = status
        self.source = "kalshi"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = mutually_exclusive
        self.external_id = None


def _show_cover():
    return _Market(24014885, "MLB The Show 27: Cover Athlete", [
        ("Matt Olson", 0.21), ("Bryan Woo", 0.16), ("Cal Raleigh", 0.14),
        ("Elly De La Cruz", 0.12), ("Bobby Witt Jr.", 0.11), ("Paul Skenes", 0.10),
        ("Aaron Judge", 0.09), ("Shohei Ohtani", 0.07),
    ])


def _dropdown(market, terms, withheld=None):
    # The typeahead futures branch's exact arguments.
    return _build_search_top_outcomes(
        market, limit=3, lean=True, withheld=withheld, query_terms=terms
    )


def _names(rows):
    return [r["name"] for r in rows]


def test_precondition_judge_is_seventh_and_off_the_dropdown_without_the_query():
    assert _names(_dropdown(_show_cover(), None)) == ["Matt Olson", "Bryan Woo", "Cal Raleigh"]


def test_judge_dropdown_row_leads_with_aaron_judge():
    rows = _dropdown(_show_cover(), JUDGE)
    assert rows[0] == {"name": "Aaron Judge", "probability": 0.09, "movement": None}
    assert _names(rows) == ["Aaron Judge", "Matt Olson", "Bryan Woo"]


def test_the_search_card_leads_with_him_too_and_keeps_his_board_rank():
    card = _format_futures_for_search(_show_cover(), None, query_terms=JUDGE)
    first = card["top_outcomes"][0]
    assert first["name"] == "Aaron Judge"
    assert first["query_match"] is True and first["matched_rank"] == 7
    assert len(card["top_outcomes"]) == _SEARCH_LADDER_LIMIT


def test_a_matched_leg_already_inside_the_cut_moves_to_the_front():
    rows = _dropdown(_show_cover(), [("woo", None)])
    assert _names(rows) == ["Bryan Woo", "Matt Olson", "Cal Raleigh"]


def test_a_matched_leg_already_first_is_the_old_row_exactly():
    assert _dropdown(_show_cover(), [("olson", None)]) == _dropdown(_show_cover(), None)
    card = _build_search_top_outcomes(
        _show_cover(), limit=_SEARCH_LADDER_LIMIT, lean=False, withheld=None,
        query_terms=[("olson", None)],
    )
    assert not any(r.get("query_match") for r in card)


def test_a_withheld_matched_leg_inside_the_cut_does_not_lead():
    # Woo is row 2; refused, he would lead as a dash. The row stays as it was.
    assert _dropdown(_show_cover(), [("woo", None)], withheld={2}) == _dropdown(
        _show_cover(), None, withheld={2}
    )


def test_a_live_match_leads_ahead_of_a_graded_one_on_an_open_multi_winner_board():
    m = _Market(8861163, "MLB: Team to make postseason", [
        ("Houston Astros", 0.9), ("Philadelphia Phillies", 0.88),
        ("New York Mets", 0.6), ("Texas Rangers", 0.55),
        ("New York Yankees", 1.0, True, "kalshi"),
    ], mutually_exclusive=False)
    rows = _build_search_top_outcomes(
        m, limit=_SEARCH_LADDER_LIMIT, lean=False, withheld=None,
        query_terms=[("new", None), ("york", None)],
    )
    assert rows[0]["name"] == "New York Mets"
    assert "New York Yankees" in _names(rows)  # #9675's winner is still on the card


# Name-match controls: the market NAME answers the query, so nothing moves. `fed`
# and `trump` are both all-name-match result sets on production.

def _fed():
    return _Market(113427, "What will Fed Rate hit before 2027", [
        ("Jerome Powell out", 0.40), ("Fed hikes", 0.20), ("Fed cuts to 3%", 0.15),
        ("No change", 0.10),
    ], category="economics")


def _trump():
    return _Market(112938, "Who will Trump nominate as Fed Chair?", [
        ("Kevin Hassett", 0.45), ("Kevin Warsh", 0.30), ("Christopher Waller", 0.12),
        ("Donald Trump Jr.", 0.05),
    ], category="politics")


def test_name_match_controls_are_byte_identical():
    for market, terms in ((_fed, [("fed", None)]), (_trump, [("trump", None)])):
        for lean, limit in ((True, 3), (False, _SEARCH_LADDER_LIMIT)):
            with_terms = _build_search_top_outcomes(
                market(), limit=limit, lean=lean, withheld=None, query_terms=terms
            )
            without = _build_search_top_outcomes(
                market(), limit=limit, lean=lean, withheld=None
            )
            assert with_terms == without
