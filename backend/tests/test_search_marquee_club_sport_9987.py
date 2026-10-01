"""#9987 — a sport only a minor club holds stops riding onto a marquee club's card.

WHAT THE READER SAW. `https://bainluck.com/search?q=lakers`, production
2026-10-01 ~02:30Z, phone width. TEAMS leads with the Los Angeles Lakers; the
ANSWERS card "LAKERS" is headed `NL: Lugano vs. Rapperswil-Jona Lakers —
Lugano 59%` (Swiss hockey), above Bronny James and the Lakers' two Western
Conference markets. The same row is #2 in the flat futures list.

THE MECHANISM. #7355's evidence is the set of sports the matched TEAMS play.
`Växjö Lakers` (SHL) is a real club, so hockey is in the set, and every hockey
row with "Lakers" in it counts as a club's market — r1's sink and r3's card
exclusion both pass it.

THE FIX. `_marquee_club_sport_categories` narrows that set for the futures
stage only: once a marquee club matched, a sport whose every matched club is a
minor professional one (not marquee, not college) is no club's sport.

RED-FIRST. Make `_marquee_club_sport_categories` return `team_categories`
unchanged and `TestTheLakersSpecimen` fails on the card's headline.
"""

import inspect
from types import SimpleNamespace

from app.routes import events as events_module
from app.routes.events import (
    _compose_futures_families,
    _marquee_club_sport_categories,
    _rerank_search_futures,
    _team_evidence_sport_categories,
)

from tests.test_search_family_teamless_sport_7355r3 import _market


def _team(name, sport_key):
    return SimpleNamespace(name=name, sport_key=sport_key)


# The served TEAMS rows for `lakers` (production 2026-10-01).
LAKERS_TEAMS = [
    _team("Los Angeles Lakers", "basketball_nba"),
    _team("Mercyhurst Lakers", "americanfootball_ncaaf"),
    _team("ROOSEVELT Lakers", "baseball_ncaa"),
    _team("Växjö Lakers", "icehockey_sweden_hockey_league"),
]

LUGANO = 62554335
BRONNY = 59334204
LAL_WCF = 61380732
LAL_WCSF = 61380733


def _lakers_candidates():
    """The served entity-family rows, in served (reranked) order."""
    return [
        _market(LUGANO, "NL: Lugano vs. Rapperswil-Jona Lakers", "hockey",
                [("Lugano", 0.585), ("Rapperswil-Jona Lakers", 0.415)]),
        _market(BRONNY, "NBA: Bronny James to Play for the Lakers in 2026-27?",
                "basketball", [("Yes", 0.9615)]),
        _market(LAL_WCF, "Will Los Angeles Lakers advance to the Western Conference "
                "Finals in the 2027 NBA Playoffs?", "basketball", [("No", 0.885)]),
        _market(LAL_WCSF, "Will Los Angeles Lakers advance to the Western Conference "
                "Semifinals in the 2027 NBA Playoffs?", "basketball", [("No", 0.72)]),
    ]


def _evidence(rows):
    return _team_evidence_sport_categories(rows, 25)


def _compose(markets, cats):
    return _compose_futures_families(
        markets, [("lakers", None)], lambda m: {"id": m.id, "name": m.name},
        {m.id for m in markets}, team_sport_categories=cats,
    )


def _card_ids(fam):
    return [fam["headline"]["id"]] + [m["id"] for m in fam["members"]]


class TestTheLakersSpecimen:
    def test_the_unnarrowed_evidence_reproduces_the_card(self):
        """The BEFORE: #7355's set holds hockey, and the Swiss game heads the card."""
        assert "hockey" in _evidence(LAKERS_TEAMS)
        (card,) = _compose(_lakers_candidates(), _evidence(LAKERS_TEAMS))
        assert card["headline"]["id"] == LUGANO

    def test_the_narrowed_evidence_drops_only_the_minor_clubs_sport(self):
        assert _marquee_club_sport_categories(
            _evidence(LAKERS_TEAMS), LAKERS_TEAMS
        ) == frozenset({"basketball", "football", "baseball"})

    def test_the_card_is_the_lakers(self):
        cats = _marquee_club_sport_categories(_evidence(LAKERS_TEAMS), LAKERS_TEAMS)
        (card,) = _compose(_lakers_candidates(), cats)
        assert _card_ids(card) == [BRONNY, LAL_WCF, LAL_WCSF]

    def test_the_flat_list_sinks_the_swiss_game(self):
        cats = _marquee_club_sport_categories(_evidence(LAKERS_TEAMS), LAKERS_TEAMS)
        ranked = _rerank_search_futures(
            _lakers_candidates(), [("lakers", None)], None, cats
        )
        assert ranked[-1].id == LUGANO
        assert {m.id for m in ranked} == {m.id for m in _lakers_candidates()}


def test_two_marquee_clubs_in_two_sports_are_both_kept():
    """`jets`: Winnipeg (NHL) and New York (NFL) — the reader could mean either."""
    rows = [_team("Winnipeg Jets", "icehockey_nhl"), _team("New York Jets", "americanfootball_nfl"),
            _team("Jets FC", "soccer_australia_aleague")]
    assert _marquee_club_sport_categories(_evidence(rows), rows) == frozenset(
        {"hockey", "football"}
    )


def test_a_college_club_is_never_minor():
    """`texas`: the Rangers are marquee and the Longhorns keep football."""
    rows = [_team("Texas Rangers", "baseball_mlb"),
            _team("Texas Longhorns", "americanfootball_ncaaf"),
            _team("Rangers", "soccer_spl")]
    assert _marquee_club_sport_categories(_evidence(rows), rows) == frozenset(
        {"baseball", "football"}
    )


def test_no_marquee_club_changes_nothing():
    """With no marquee club there is no one the reader more plausibly meant —
    a college club alone does not arm it (the college row is what would
    survive a narrowing, so this case is the one that can tell)."""
    rows = [_team("Chicago Wolves", "icehockey_ahl"),
            _team("Warrington Wolves", "rugbyleague_super_league"),
            _team("Georgia Southern Wolves", "americanfootball_ncaaf")]
    cats = _evidence(rows)
    assert cats == frozenset({"hockey", "rugby", "football"})
    assert _marquee_club_sport_categories(cats, rows) == cats


def test_a_marquee_leagues_preseason_row_is_marquee():
    rows = [_team("Los Angeles Lakers", "basketball_nba_preseason"),
            _team("Växjö Lakers", "icehockey_sweden_hockey_league")]
    assert _marquee_club_sport_categories(_evidence(rows), rows) == frozenset({"basketball"})


def test_disarmed_evidence_stays_disarmed():
    assert _marquee_club_sport_categories(None, LAKERS_TEAMS) is None
    assert _marquee_club_sport_categories(frozenset(), LAKERS_TEAMS) == frozenset()


def test_it_never_empties_the_set():
    """An emptied set would read as disarmed — never sink everything instead."""
    rows = [_team("Los Angeles Lakers", "basketball_nba")]
    assert _marquee_club_sport_categories(frozenset({"hockey"}), rows) == frozenset({"hockey"})


def test_the_route_narrows_the_futures_evidence_only():
    """Applied to the futures stage's set, after it is read and before every
    futures reader; the games list's own evidence (#8697) is untouched."""
    src = inspect.getsource(events_module.search_events)
    narrow = src.index(
        "_team_sport_categories = _marquee_club_sport_categories(\n"
        "        _team_sport_categories, _team_result_rows\n"
    )
    assert src.count("_marquee_club_sport_categories(") == 1
    assert src.index("_team_sport_categories = _team_evidence_sport_categories(") < narrow
    assert narrow < src.index("reranked_futures = _rerank_search_futures(")
    assert narrow < src.index("futures_families = _compose_futures_families(")
    games_key = src.index("_teamless_sport_key = _event_teamless_sport_order_key(")
    assert games_key < narrow
