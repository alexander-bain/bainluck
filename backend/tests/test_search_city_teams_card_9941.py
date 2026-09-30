"""#9941 — a bare city's TEAMS card shows its NFL club.

`chicago` on production 2026-09-30 (484e1777, 390px): the card was Blackhawks,
Bulls, Cubs, Sky and White Sox — each carries the alias `Chicago` (MC0) — and no
Bears, whose row carries only `Bears` (MC1 on the name). `new york` had no Giants
or Jets. #9897 fixed the games half; this is the card: when the typed words are
a city, the clubs the city names take one slot per major league (football,
baseball, basketball, hockey) before any league takes a second. The route arm on
real Postgres is `tests/integration/test_search_city_lead_tier_pg_9897.py`.
"""

import pytest

from app.routes import events as ev
from app.routes.events import (
    _search_bye_team_ids,
    _team_card_keyed,
    _team_card_lead_sport_keys,
)
from tests.test_search_city_lead_tier_9897 import CHICAGO, LOS_ANGELES, _team

# Production's rows and aliases (db-query 2026-09-30), in the window's arrival
# order: the city-aliased rows out-rank the NFL rows on `ts_rank_cd`.
NEW_YORK = [
    _team(108, "New York Knicks", "basketball_nba", ["New York", "Knicks", "New York Knicks"]),
    _team(10737, "New York Mets", "baseball_mlb", ["New York", "Mets"]),
    _team(6610, "New York Yankees", "baseball_mlb", ["New York", "yanks", "Yankees"]),
    _team(13414, "New York Liberty", "basketball_wnba", ["Liberty", "New York"]),
    _team(34, "New York Red Bulls", "soccer_usa_mls",
          ["NY Red Bulls", "Red Bull NY", "Red Bull New York", "New York"]),
    _team(54, "New York Islanders", "icehockey_nhl",
          ["New York I", "Islanders", "New York Islanders"], 0.1),
    _team(57, "New York Rangers", "icehockey_nhl",
          ["New York Rangers", "Rangers", "New York R"], 0.1),
    _team(547, "New York Giants", "americanfootball_nfl", ["Giants"], 0.1),
    _team(550, "New York Jets", "americanfootball_nfl", ["Jets"], 0.1),
]

NORTH_CAROLINA = [
    _team(1, "North Carolina Tar Heels", "americanfootball_ncaaf", ["Tar Heels", "North Carolina"]),
    _team(2, "North Carolina FC", "soccer_usa_usl", ["North Carolina"]),
    # Arrives first, so a tie re-sorted by arrival would lead with it: the
    # control bites only if the league clause is what disarms this query.
    _team(3, "North Carolina Central Eagles", "americanfootball_ncaaf", ["Eagles"], 0.3),
]

GIANTS = [
    _team(10750, "San Francisco Giants", "baseball_mlb", ["Giants"], 0.3),
    _team(547, "New York Giants", "americanfootball_nfl", ["Giants"]),
]

TEXAS = [
    _team(10742, "Texas Rangers", "baseball_mlb", ["Rangers", "Texas"]),
    _team(834, "Texas Longhorns", "americanfootball_ncaaf", ["Longhorns", "Texas"]),
    _team(14125, "Texas Tech Red Raiders", "americanfootball_ncaaf", ["Red Raiders"]),
]


def _card(rows, query):
    return [c["name"] for _k, c in _team_card_keyed(rows, query)]


def _before_9941(monkeypatch):
    """Today's order: the arm made a pass-through."""
    monkeypatch.setattr(ev, "_bare_city_card_order", lambda keyed, cards, query: keyed)


def test_chicago_cards_the_bears_first_and_one_club_per_league():
    assert _card(CHICAGO, "chicago") == [
        "Chicago Bears", "Chicago Cubs", "Chicago Bulls", "Chicago Blackhawks",
        "Chicago White Sox",
    ]


@pytest.mark.parametrize("typed", ["new york", "New York"])
def test_new_york_cards_both_football_clubs(typed):
    assert _card(NEW_YORK, typed) == [
        "New York Giants", "New York Mets", "New York Knicks", "New York Islanders",
        "New York Jets",
    ]


def test_los_angeles_cards_a_football_club_and_every_major_league():
    card = _card(LOS_ANGELES, "los angeles")
    assert card[0] in ("Los Angeles Chargers", "Los Angeles Rams"), card
    leagues = {c["sport_key"] for _k, c in _team_card_keyed(LOS_ANGELES, "los angeles")}
    assert leagues == {
        "americanfootball_nfl", "baseball_mlb", "basketball_nba", "icehockey_nhl",
    }, card


@pytest.mark.parametrize("rows,query", [
    (CHICAGO, "chicago"), (NEW_YORK, "new york"), (LOS_ANGELES, "los angeles"),
])
def test_strawman_counting_the_city_alias_brings_back_a_card_with_no_football(
    rows, query, monkeypatch
):
    """With the restated alias counted again the arm cannot tell a city from a
    club, and no football club reaches the card — production's defect."""
    monkeypatch.setattr(ev, "_alias_restates_name_prefix", lambda alias, name: False)
    sports = [c["sport_key"] for _k, c in _team_card_keyed(rows, query)]
    assert len(sports) == 5 and "americanfootball_nfl" not in sports, sports


def test_strawman_chicago_is_productions_card_row_for_row(monkeypatch):
    monkeypatch.setattr(ev, "_alias_restates_name_prefix", lambda alias, name: False)
    assert _card(CHICAGO, "chicago") == [
        "Chicago Blackhawks", "Chicago Bulls", "Chicago Cubs", "Chicago Sky",
        "Chicago White Sox",
    ]


@pytest.mark.parametrize("rows,query", [
    (CHICAGO, "bulls"),              # a nickname names its club
    (CHICAGO, "chicago bears"),      # the club, spelled out
    (NEW_YORK, "ny giants"),         # #9859's abbreviation arm
    (NEW_YORK, "new york rangers"),
    (GIANTS, "giants"),              # two leagues' Giants: arrival order stands
    (TEXAS, "texas"),                # the Rangers alone in the city tie
    (NORTH_CAROLINA, "north carolina"),  # a college leads: not a pro city
])
def test_control_a_query_that_is_not_a_bare_city_keeps_todays_card(
    rows, query, monkeypatch
):
    card = _card(rows, query)
    _before_9941(monkeypatch)
    assert _card(rows, query) == card


def test_the_games_lead_key_reads_the_same_tier(monkeypatch):
    """#9897's key follows the card's leader into the stripped tier; a Bears
    leader lands in the same tier the Blackhawks did."""
    after = _team_card_lead_sport_keys(CHICAGO, "chicago")
    _before_9941(monkeypatch)
    assert _team_card_lead_sport_keys(CHICAGO, "chicago") == after


def test_the_card_tier_is_one_club_group_for_the_bye_probe():
    """The re-ordered clubs carry one key, so #9632's club group is the card."""
    card_ids = sorted(c["id"] for _k, c in _team_card_keyed(CHICAGO, "chicago"))
    assert _search_bye_team_ids(CHICAGO, "chicago") == card_ids
