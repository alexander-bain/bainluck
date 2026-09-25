"""#8726 — search must not lead with a board that has no open question left.

`bainluck.com/search?q=presidents cup` (production, 2026-09-25 ~22:05Z, during
round 2) led with `Golfers to compete in the Presidents Cup this year` (Kalshi
KXPGACOMPETE-PRESCUP26SEP, 58728412): twenty legs at 0.965-0.995 or 0.01-0.02,
the teams named weeks earlier. `Presidents Cup Winner` (KXPRESCUP-26, 16757297,
Team USA 85.5%) came second because the name-match sort reads lifetime volume,
109,301 against 67,447. Fixture values are the production rows (id, name, tier,
volume, legs).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.routes import events as events_route

STAMP = datetime.now(timezone.utc) - timedelta(hours=5)


class _Outcome:
    def __init__(self, id, name, p):
        self.id = id
        self.name = name
        self.current_probability = p
        self.last_updated = STAMP


class _Market:
    def __init__(self, id, name, volume, legs, market_tier=1):
        self.id = id
        self.source = "kalshi"
        self.name = name
        self.market_tier = market_tier
        self.volume = volume
        self.outcomes = [_Outcome(id * 100 + i, n, p) for i, (n, p) in enumerate(legs)]
        self.canonical_market_key = None
        self.external_id = None
        self.llm_sport_category = "golf"
        self.sport = None


ROSTER_LEGS = [
    ("Cameron Young", 0.995), ("Russell Henley", 0.995), ("Jacob Bridgeman", 0.995),
    ("Patrick Cantlay", 0.995), ("Sam Burns", 0.995), ("Chris Gotterup", 0.995),
    ("Scottie Scheffler", 0.995), ("Wyndham Clark", 0.99),
    ("Xander Schauffele", 0.975), ("Collin Morikawa", 0.975),
    ("Jackson Koivun", 0.975), ("Justin Thomas", 0.965),
    ("Harris English", 0.02), ("Jordan Spieth", 0.02), ("Ben Griffin", 0.02),
    ("Patrick Reed", 0.01), ("Brooks Koepka", 0.01), ("Akshay Bhatia", 0.01),
    ("Ryan Gerard", 0.01), ("J.J. Spaun", 0.01),
]


def _roster():
    return _Market(58728412, "Golfers to compete in the Presidents Cup this year",
                   109301, ROSTER_LEGS, market_tier=5)


def _winner():
    return _Market(16757297, "Presidents Cup Winner", 67447,
                   [("Team USA", 0.855), ("Team World", 0.115), ("Tie", 0.035)])


QUERY = [("presidents", None), ("cup", None)]


def _ids(rows):
    return [m.id for m in rows]


def test_precondition_the_roster_board_wins_the_volume_sort():
    # Without this the specimen cannot fail on the old rule.
    assert _roster().volume > _winner().volume
    assert events_route._query_name_match(_roster(), QUERY)
    assert events_route._query_name_match(_winner(), QUERY)


def test_presidents_cup_leads_with_the_winner_question():
    ranked = events_route._rerank_search_futures([_roster(), _winner()], QUERY)
    assert _ids(ranked) == [16757297, 58728412]


def test_the_decided_board_is_moved_not_dropped():
    ranked = events_route._rerank_search_futures([_winner(), _roster()], QUERY)
    assert sorted(_ids(ranked)) == [16757297, 58728412]


def test_the_specimens_are_classified_as_measured():
    assert events_route._search_board_is_decided(_roster()) is True
    assert events_route._search_board_is_decided(_winner()) is False


def test_one_contested_leg_keeps_a_board_in_play():
    # A roster board with a single real selection question left still leads.
    legs = ROSTER_LEGS[:-1] + [("J.J. Spaun", 0.40)]
    open_roster = _Market(58728412, "Golfers to compete in the Presidents Cup this year",
                          109301, legs, market_tier=5)
    assert events_route._search_board_is_decided(open_roster) is False
    ranked = events_route._rerank_search_futures([open_roster, _winner()], QUERY)
    assert _ids(ranked) == [58728412, 16757297]


def test_the_band_edges():
    at_edge = _Market(1, "Presidents Cup edge", 1, [("A", 0.95), ("B", 0.05)])
    inside = _Market(2, "Presidents Cup inside", 1, [("A", 0.949), ("B", 0.051)])
    assert events_route._search_board_is_decided(at_edge) is True
    assert events_route._search_board_is_decided(inside) is False


def test_a_board_printing_nothing_cannot_be_called_decided():
    blank = _Market(3, "Presidents Cup blank", 999999, [("A", None), ("B", None)])
    assert events_route._search_board_is_decided(blank) is False
    ranked = events_route._rerank_search_futures([blank, _winner()], QUERY)
    assert _ids(ranked) == [3, 16757297]


def test_a_dash_only_leg_does_not_contest():
    # Printed legs are all decided; the unpriced one renders a dash and has no vote.
    m = _Market(4, "Presidents Cup dash", 1, [("A", 0.99), ("B", None), ("C", 0.01)])
    assert events_route._search_board_is_decided(m) is True


def test_a_decided_name_match_still_leads_every_outcome_only_row():
    # The partition runs inside each group: being ABOUT the query outranks
    # being contested.
    outcome_only = _Market(5, "Ryder Cup 2027 Winner", 5_000_000,
                           [("Presidents Cup captain", 0.5), ("Other", 0.5)])
    ranked = events_route._rerank_search_futures([outcome_only, _roster()], QUERY)
    assert _ids(ranked) == [58728412, 5]


def test_outcome_only_rows_are_partitioned_too():
    decided = _Market(6, "Golf novelty A", 900, [("Presidents Cup", 0.99)])
    open_ = _Market(7, "Golf novelty B", 100, [("Presidents Cup", 0.5)])
    ranked = events_route._rerank_search_futures([decided, open_], QUERY)
    assert _ids(ranked) == [7, 6]


def test_all_decided_or_all_contested_keeps_the_volume_order():
    a = _Market(8, "Presidents Cup A", 300, [("X", 0.99)])
    b = _Market(9, "Presidents Cup B", 200, [("X", 0.01)])
    assert _ids(events_route._rerank_search_futures([b, a], QUERY)) == [8, 9]
    c = _Market(10, "Presidents Cup C", 300, [("X", 0.5)])
    d = _Market(11, "Presidents Cup D", 200, [("X", 0.6)])
    assert _ids(events_route._rerank_search_futures([d, c], QUERY)) == [10, 11]


def test_contested_boards_keep_their_volume_order_among_themselves():
    small = _Market(12, "Presidents Cup Top American", 10, [("Scheffler", 0.3)])
    ranked = events_route._rerank_search_futures([small, _roster(), _winner()], QUERY)
    assert _ids(ranked) == [16757297, 12, 58728412]
