"""#8843 — search must print the 2028 presidential winner once, not once per venue.

`bainluck.com/search?q=election` (390px, 2026-09-26 ~15:15Z) showed Polymarket
`112897` "Presidential Election Winner 2028" (JD Vance 21%) and Kalshi `108326`
"2028 U.S. Presidential Election winner?" (J.D. Vance 20%) as two rows. The
fixtures are those production rows: id, source, name, tier, and the first
listed contender names in the venue's own spelling (db-query, 2026-09-26 16:45Z).
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as events_route


class _Outcome:
    def __init__(self, name):
        self.name = name


class _Market:
    def __init__(self, id, source, name, market_tier, names=()):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.canonical_market_key = None
        self.outcomes = [_Outcome(n) for n in names]


POLY_2028 = _Market(
    112897,
    "polymarket",
    "Presidential Election Winner 2028",
    1,
    [
        "JD Vance",
        "Alexandria Ocasio-Cortez",
        "Jon Ossoff",
        "Marco Rubio",
        "Gavin Newsom",
        "Kamala Harris",
        "Josh Shapiro",
        "Pete Buttigieg",
        "Tucker Carlson",
        "Ron DeSantis",
        "JB Pritzker",
        "Elon Musk",
    ],
)
KALSHI_2028 = _Market(
    108326,
    "kalshi",
    "2028 U.S. Presidential Election winner?",
    1,
    [
        "J.D. Vance",
        "Jon Ossoff",
        "Marco Rubio",
        "Alexandria Ocasio-Cortez",
        "Gavin Newsom",
        "Kamala Harris",
        "Mark Kelly",
        "Pete Buttigieg",
        "Andy Beshear",
        "Ron DeSantis",
        "J.B. Pritzker",
        "Tim Walz",
    ],
)
KALSHI_PARTY = _Market(
    108327,
    "kalshi",
    "2028 Presidential Election winner? (Party)",
    1,
    ["Democratic party", "Republican party"],
)

GOLFERS = [
    "Scottie Scheffler",
    "Rory McIlroy",
    "Xander Schauffele",
    "Jon Rahm",
    "Bryson DeChambeau",
    "Ludvig Aberg",
]
US_OPEN = _Market(9001, "kalshi", "U.S. Open winner?", 2, GOLFERS)
THE_OPEN = _Market(9002, "polymarket", "The Open Championship Winner", 2, GOLFERS)


def _page(rows):
    """Run rows through the route's own per-row decision, in order."""
    seen: set = set()
    kept: dict = {}
    boards: list = []
    return [
        m.id for m in rows if events_route._admit_search_future(m, seen, kept, boards)
    ]


def test_precondition_the_question_key_splits_the_specimen():
    """Otherwise the #8378 arm folds it and this file proves nothing."""
    a, _ = events_route._search_question_identity(POLY_2028)
    b, _ = events_route._search_question_identity(KALSHI_2028)
    assert a != b


@pytest.mark.parametrize(
    "first, second",
    [(POLY_2028, KALSHI_2028), (KALSHI_2028, POLY_2028)],
    ids=["polymarket-first", "kalshi-first"],
)
def test_the_specimen_prints_once_and_the_ranking_picks_the_venue(first, second):
    assert _page([first, second]) == [first.id]


def test_the_page_as_served_keeps_the_party_board():
    """The served family: headline 112897, members 108326 and 108327."""
    assert _page([POLY_2028, KALSHI_2028, KALSHI_PARTY]) == [
        POLY_2028.id,
        KALSHI_PARTY.id,
    ]


@pytest.mark.parametrize(
    "first, second",
    [(POLY_2028, KALSHI_PARTY), (KALSHI_PARTY, POLY_2028)],
    ids=["person-first", "party-first"],
)
def test_the_party_board_is_a_different_question(first, second):
    """The house matcher alone pairs these titles — the field gate refuses."""
    from app.utils.cross_source_matching import is_same_question

    assert is_same_question(first.name, second.name)
    assert _page([first, second]) == [first.id, second.id]


def test_the_us_open_is_not_the_open_championship():
    """Same golfers, different majors — the title gate refuses."""
    assert _page([US_OPEN, THE_OPEN]) == [US_OPEN.id, THE_OPEN.id]


def test_two_editions_with_one_field_stay_two_rows():
    kalshi_2032 = _Market(
        9003,
        "kalshi",
        "2032 U.S. Presidential Election winner?",
        1,
        [o.name for o in KALSHI_2028.outcomes],
    )
    assert _page([POLY_2028, kalshi_2032]) == [POLY_2028.id, kalshi_2032.id]


def test_one_venues_two_boards_stay_two_rows():
    """Cross-venue only: a venue's own two listings are that venue's call."""
    same_venue = _Market(
        9004,
        "polymarket",
        "2028 U.S. Presidential Election winner?",
        1,
        [o.name for o in POLY_2028.outcomes],
    )
    assert _page([POLY_2028, same_venue]) == [POLY_2028.id, same_venue.id]


def test_a_row_without_loaded_outcomes_is_kept():
    bare = _Market(9005, "kalshi", KALSHI_2028.name, 1)
    assert _page([POLY_2028, bare]) == [POLY_2028.id, bare.id]


def test_two_shared_names_are_not_a_field():
    thin = _Market(
        9006,
        "kalshi",
        KALSHI_2028.name,
        1,
        ["J.D. Vance", "Jon Ossoff", "Someone Else", "Another Person"],
    )
    assert _page([POLY_2028, thin]) == [POLY_2028.id, thin.id]


def test_yes_no_boards_fold_only_on_the_same_question():
    a = _Market(
        9007, "kalshi", "Will the Fed cut rates in September 2026?", 3, ["Yes", "No"]
    )
    b = _Market(
        9008, "polymarket", "Fed cut rates in September 2026?", 3, ["Yes", "No"]
    )
    c = _Market(9009, "polymarket", "Fed cut rates in October 2026?", 3, ["Yes", "No"])
    assert _page([a, c]) == [a.id, c.id]
    assert _page([a, b]) == [a.id]


def test_two_small_boards_with_different_answers_stay_two_rows():
    """Both boards list two or fewer names, so they must list the SAME names."""
    yes_no = _Market(
        9010,
        "polymarket",
        "2028 U.S. Presidential Election winner? (Party)",
        1,
        ["Yes", "No"],
    )
    same = _Market(
        9011,
        "polymarket",
        yes_no.name,
        1,
        ["Democratic Party", "Republican Party"],
    )
    assert _page([KALSHI_PARTY, same]) == [KALSHI_PARTY.id]
    assert _page([KALSHI_PARTY, yes_no]) == [KALSHI_PARTY.id, yes_no.id]


def test_contender_names_compare_without_punctuation():
    assert "jd vance" in events_route._search_listed_names(KALSHI_2028)
    assert "jd vance" in events_route._search_listed_names(POLY_2028)


def test_both_route_loops_share_the_kept_boards():
    """The window and the refill pass the SAME list, or the refill re-admits
    the copy the window dropped."""
    src = inspect.getsource(events_route.search_events)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert code.count("kept_sources_by_question, kept_boards") == 2
    assert code.count("kept_boards: list = []") == 1
