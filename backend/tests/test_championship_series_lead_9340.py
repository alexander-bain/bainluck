"""#9340: a spelled-out round (`championship series`) leads with its own markets.

Pure: the rule that decides WHICH queries are the round and WHICH markets are
its own. The route wiring (the /search tier, the dropdown key, the partition
and the private alias) is gated on real Postgres in
`tests/integration/test_search_championship_series_lead_pg.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes import events as ev


def _m(name: str, source: str = "kalshi", external_id: str = "x"):
    return SimpleNamespace(name=name, source=source, external_id=external_id)


@pytest.mark.parametrize(
    "terms, expected",
    [
        (["championship", "series"], ("alcs", "nlcs")),
        (["Championship", "Series"], ("alcs", "nlcs")),
        (["mlb", "championship", "series"], ("alcs", "nlcs")),
        (["division", "series"], ("alds", "nlds")),
    ],
)
def test_the_round_is_named(terms, expected):
    assert ev._bare_postseason_named_round(terms) == expected


@pytest.mark.parametrize(
    "terms",
    [
        ["nfl", "championship", "series"],   # another league's question
        ["yankees", "championship", "series"],  # one club's question
        ["season", "series", "winner"],
        ["championship"],
        ["series"],
        ["alcs"],
    ],
)
def test_not_the_round(terms):
    assert ev._bare_postseason_named_round(terms) is None


def test_a_ticker_round_is_refused_for_another_league_too():
    assert ev._bare_postseason_round(["wild", "card"]) is not None
    assert ev._bare_postseason_round(["mlb", "wild", "card"]) is not None
    assert ev._bare_postseason_round(["nfl", "wild", "card"]) is None


def test_the_round_markets_are_the_whole_word_abbreviations():
    in_round = ev._postseason_round_lead_predicate(["championship", "series"])
    assert in_round(_m("MLB Playoffs: Team to advance to ALCS"))
    assert in_round(_m("MLB NLCS Qualifiers"))
    assert not in_round(_m("NFL: Cardinals vs. 49ers Season Series Winner"))
    assert not in_round(_m("MLB Championship Series Matchup"))
    assert not in_round(_m("Balcsy Cup winner"))  # the letters, not the word


def test_the_partition_puts_them_first_and_keeps_order():
    rows = [
        _m("NFL: Cardinals vs. 49ers Season Series Winner"),
        _m("MLB Championship Series Matchup"),
        _m("MLB NLCS Qualifiers"),
        _m("NFL: Lions vs. Packers Season Series Winner"),
        _m("MLB Playoffs: Team to advance to ALCS"),
    ]
    out = [m.name for m in ev._postseason_round_series_first(rows, ["championship", "series"])]
    assert out == [
        "MLB NLCS Qualifiers",
        "MLB Playoffs: Team to advance to ALCS",
        "NFL: Cardinals vs. 49ers Season Series Winner",
        "MLB Championship Series Matchup",
        "NFL: Lions vs. Packers Season Series Winner",
    ]
    # Not the round: untouched.
    assert ev._postseason_round_series_first(rows, ["season", "series"]) == rows


def test_no_lead_key_without_a_round():
    assert ev._futures_postseason_round_order_key(["season", "series", "winner"]) is None
    assert ev._futures_postseason_round_order_key(["championship", "series"]) is not None
