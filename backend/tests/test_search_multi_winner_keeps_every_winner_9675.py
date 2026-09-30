"""#9675 — a multi-winner board keeps every settled winner on the search card.

WHAT A READER SAW, production 2026-09-29 ~19:05Z, ``/search?q=braves`` at 390px:
the card *MLB Playoffs: Team to advance to NLDS* showed ``Milwaukee Brewers ✓ Won``
and four open teams. The Dodgers are graded a winner on the same board and were
missing, so the card read as if only the Brewers were through; at 14:13Z the same
card had shown the Dodgers and no Brewers.

THE FIXTURE IS THE SPECIMEN'S STORED ROWS — market 60087232 (``status=open``,
``mutually_exclusive=false``), all ten outcomes, read off production via
``db-query`` 2026-09-29 ~21:30Z. Both winners are 1.0 AND rank 1, so nothing in
the sort separates them.

THE CONTROLS: a one-winner board (#8640's control — the graded winner is the whole
answer there and keeps the headline), and a board whose winners already fit
(unchanged apart from the winners' order).
"""

from types import SimpleNamespace

from app.routes.events import _build_search_top_outcomes

#: ``(id, name, prob, is_winner, resolution_source, rank)`` — market 60087232.
NLDS_LEGS = [
    (231082191, "Milwaukee Brewers", 1.0, True, "api_settlement", 1),
    (231082192, "Los Angeles Dodgers", 1.0, True, "api_settlement", 1),
    (232072991, "San Diego Padres", 0.565, None, None, 3),
    (231082193, "Atlanta Braves", 0.555, None, None, 4),
    (231082195, "Chicago Cubs", 0.465, None, None, 5),
    (231082194, "Philadelphia Phillies", 0.435, None, None, 6),
    (232072992, "Arizona Diamondbacks", 0.0, False, "api_settlement", 7),
    (231082196, "St. Louis Cardinals", 0.0, False, "api_settlement", 7),
    (231082198, "Pittsburgh Pirates", 0.0, False, "api_settlement", 7),
    (231082197, "Miami Marlins", 0.0, False, "api_settlement", 7),
]

WINNERS = {"Milwaukee Brewers", "Los Angeles Dodgers"}


def _leg(oid, name, prob, is_winner, resolution_source, rank):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"pm-{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=rank,
        probability_change_24h=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        current_yes_bid=None,
        current_yes_ask=None,
        price_changed_at=None,
        last_updated=None,
    )


def _market(legs=NLDS_LEGS, *, mutually_exclusive=False, order=None):
    rows = [_leg(*row) for row in legs]
    if order is not None:
        rows = [rows[i] for i in order]
    return SimpleNamespace(
        id=60087232,
        name="MLB Playoffs: Team to advance to NLDS",
        source="polymarket",
        status="open",
        mutually_exclusive=mutually_exclusive,
        outcomes=rows,
    )


def _names(out):
    return [o["name"] for o in out]


def test_both_winners_are_on_the_card():
    out = _build_search_top_outcomes(_market())
    assert WINNERS <= set(_names(out)), _names(out)
    assert len(out) == 5


def test_a_live_team_still_headlines_and_winners_follow_the_live_legs():
    # #8640 is unchanged: a result never headlines an open multi-winner board.
    out = _build_search_top_outcomes(_market())
    assert out[0]["name"] == "San Diego Padres", _names(out)
    assert _names(out)[-2:] == ["Los Angeles Dodgers", "Milwaukee Brewers"]
    for row in out[-2:]:
        assert row["probability"] == 1.0
        assert row["is_winner"] is True
        assert row["resolution_source"] == "api_settlement"


def test_the_live_leg_the_winners_cost_is_the_weakest_one():
    out = _build_search_top_outcomes(_market())
    assert _names(out)[:3] == ["San Diego Padres", "Atlanta Braves", "Chicago Cubs"]


def test_winner_order_does_not_depend_on_load_order():
    # The defect's second half: the two 1.0/rank-1 winners flipped between reads.
    forward = _build_search_top_outcomes(_market())
    reverse = _build_search_top_outcomes(_market(order=list(range(len(NLDS_LEGS)))[::-1]))
    assert _names(forward) == _names(reverse)


def test_lean_typeahead_keeps_both_winners_and_a_live_headline():
    # #993: the dropdown and the card are one pair.
    out = _build_search_top_outcomes(_market(), limit=3, lean=True)
    assert _names(out) == ["San Diego Padres", "Los Angeles Dodgers", "Milwaukee Brewers"]


def test_more_winners_than_rows_still_leaves_the_headline_to_a_live_leg():
    legs = [
        (i, f"Winner {i}", 1.0, True, "api_settlement", 1) for i in range(1, 7)
    ] + [(99, "Still Open", 0.4, None, None, 7)]
    out = _build_search_top_outcomes(_market(legs))
    assert out[0]["name"] == "Still Open"
    assert _names(out)[1:] == ["Winner 1", "Winner 2", "Winner 3", "Winner 4"]


def test_a_search_for_a_live_team_cut_from_the_card_evicts_a_live_leg_not_a_winner():
    # #8842's pin: 'phillies' recalls the card through the Phillies, who lost
    # their row to the winners. The pin takes a live leg's row.
    out = _build_search_top_outcomes(
        _market(), query_terms=[("phillies", None)]
    )
    names = _names(out)
    assert "Philadelphia Phillies" in names, names
    assert WINNERS <= set(names), names
    assert len(out) == 5


def test_control_one_winner_board_keeps_the_winner_as_the_headline():
    out = _build_search_top_outcomes(_market(mutually_exclusive=True))
    assert out[0]["is_winner"] is True, _names(out)


def test_control_winners_that_already_fit_change_nothing_but_their_order():
    legs = [row for row in NLDS_LEGS if row[1] in WINNERS | {"San Diego Padres"}]
    out = _build_search_top_outcomes(_market(legs))
    assert _names(out) == ["San Diego Padres", "Los Angeles Dodgers", "Milwaukee Brewers"]
