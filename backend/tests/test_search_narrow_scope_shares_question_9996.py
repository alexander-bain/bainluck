"""#9996: a narrow-scope row sinks only below the broad rows that share the question.

Production 2026-10-01 04:0xZ, `?q=celtics`: the one futures row naming the club,
"Will Boston Celtics advance to the Eastern Conference Finals…", served 5th —
below the NBA Cup, the Draft Lottery (Celtics 1%) and "Steph Curry Next Team"
(Celtics 0.5%). `_demote_narrower_scope` (#993 L2-44) is applied to the FULL
re-ranked list and sank every row carrying an unasked scope word ("eastern",
"conference", "finals") below every row that carried none.
"""

import itertools
from types import SimpleNamespace

from app.routes.events import _demote_narrower_scope, _rerank_search_futures

_ids = itertools.count(1)


def _mkt(name, vol=0):
    return SimpleNamespace(
        id=next(_ids), name=name, volume=vol, llm_sport_category="basketball"
    )


_CELTICS = [("celtics", None)]
_NBA_MVP = [("nba", None), ("mvp", None)]


def _celtics_page():
    # The production specimen's five rows, at their stored lifetime volumes.
    return [
        _mkt("NBA: 2027 Champion", 22_979_251),
        _mkt("NBA: 2026 NBA Cup Winner", 1_870),
        _mkt("2027 NBA Draft Lottery: 1st Pick", 721),
        _mkt("NBA: Steph Curry Next Team", 47_843),
        _mkt(
            "Will Boston Celtics advance to the Eastern Conference Finals "
            "in the 2027 NBA Playoffs?",
            None,
        ),
    ]


def test_celtics_own_question_leads_the_boards_that_only_list_the_club():
    out = [m.name for m in _rerank_search_futures(_celtics_page(), _CELTICS)]
    assert out[0].startswith("Will Boston Celtics advance")
    # The four boards keep their incoming order beneath it.
    assert out[1:] == [
        "NBA: 2027 Champion",
        "NBA: 2026 NBA Cup Winner",
        "2027 NBA Draft Lottery: 1st Pick",
        "NBA: Steph Curry Next Team",
    ]


def test_no_question_sharing_broad_row_returns_the_list_itself():
    page = _celtics_page()
    club_first = [page[4], *page[:4]]
    assert _demote_narrower_scope(club_first, [("celtics", "")]) is club_first


def test_award_query_still_headlines_the_season_award():
    # #993 L2-44's case: "MVP Winner" holds `mvp`, so it shares the question.
    narrow = _mkt("Eastern Conference Finals MVP Winner", 5_000_000)
    season = _mkt("MVP Winner", 2_000_000)
    out = _demote_narrower_scope([narrow, season], [("nba", ""), ("mvp", "")])
    assert out == [season, narrow]


def test_a_league_word_in_the_query_makes_every_league_board_share_it():
    unrelated_above = _mkt("2027 NBA Draft Lottery: 1st Pick")
    narrow = _mkt("Eastern Conference Finals MVP")
    season = _mkt("NBA MVP Winner")
    unrelated_below = _mkt("NBA: Steph Curry Next Team")
    out = _demote_narrower_scope(
        [unrelated_above, narrow, season, unrelated_below],
        [("nba", ""), ("mvp", "")],
    )
    # `unrelated_*` hold `nba`, so both share the question here — which is the
    # point: the rule reads the query, not the row's sport.
    assert out == [unrelated_above, season, unrelated_below, narrow]


def test_rows_with_no_query_word_keep_their_place_around_a_moved_narrow_row():
    narrow = _mkt("Western Conference Finals MVP")
    season = _mkt("MVP Winner")
    no_word = _mkt("Rookie of the Year")
    out = _demote_narrower_scope([narrow, season, no_word], [("mvp", "")])
    assert out == [season, narrow, no_word]


def test_two_narrow_rows_keep_their_order_when_held():
    a = _mkt("Eastern Conference Finals MVP")
    b = _mkt("Western Conference Finals MVP")
    season = _mkt("MVP Winner")
    out = _demote_narrower_scope([a, b, season], [("mvp", "")])
    assert out == [season, a, b]


def test_expansion_counts_as_sharing_the_question():
    narrow = _mkt("Eastern Conference Finals MVP")
    season = _mkt("Most Valuable Player")
    out = _demote_narrower_scope([narrow, season], [("mvp", "most valuable")])
    assert out == [season, narrow]
