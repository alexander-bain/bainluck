"""Per-sport fixtures for the shared game-market CLASS classifier.

Guards the fix for the capture-census "impossible" finding (moneyline markets <
games): the dominant real game-winner phrasing is a BARE MATCHUP ("Team at
Team", "Team vs. Team") with no "winner"/"moneyline" word, plus a
KX<LEAGUE>GAME ticker. Every sport must recognize its own game-winner markets so
a per-game census lands at ~1+ moneyline/game and a small "other" bucket.

No sport-specific PATCHES here — one shared classifier, many per-sport FIXTURES.
"""

import pytest

from app.utils.game_market_class import (
    classify_game_market_class,
    is_bare_matchup,
    is_game_winner_market,
)


# (name, external_id, sport, expected_class)
MONEYLINE_FIXTURES = [
    # MLB — the exact shapes from real Kalshi/Polymarket fixtures.
    ("Yankees at Dodgers", None, "baseball_mlb", "moneyline"),
    ("MLB: Yankees at Dodgers", None, "baseball_mlb", "moneyline"),
    ("Yankees vs. Red Sox", None, "baseball_mlb", "moneyline"),
    ("Athletics at White Sox", "KXMLBGAME-26JUN01ATHCWS", "baseball_mlb", "moneyline"),
    ("Will the Yankees beat the Red Sox?", None, "baseball_mlb", "moneyline"),
    # NBA — the two shapes test_game_markets.py used to assert as "other".
    ("Celtics at Warriors", None, "basketball_nba", "moneyline"),
    ("Celtics vs. Warriors", None, "basketball_nba", "moneyline"),
    ("Will the Warriors beat the Celtics?", None, "basketball_nba", "moneyline"),
    # NFL / NHL / soccer bare matchups.
    ("Chiefs at Bills", None, "americanfootball_nfl", "moneyline"),
    ("Rangers vs. Bruins", None, "icehockey_nhl", "moneyline"),
    ("Arsenal vs. Chelsea", None, "soccer_epl", "moneyline"),
    # Explicit wording still works.
    ("Lakers Moneyline", None, "basketball_nba", "moneyline"),
    ("Super Bowl Winner: Chiefs", None, "americanfootball_nfl", "moneyline"),
]

NON_MONEYLINE_FIXTURES = [
    # Totals.
    ("Yankees vs Red Sox: Total Runs O/U 8.5", None, "baseball_mlb", "total"),
    ("Celtics at Warriors: Total Points", None, "basketball_nba", "total"),
    ("Over 224.5", None, "basketball_nba", "total"),
    # Spreads — including a bare-matchup NAME rescued by a spread ticker.
    ("Yankees at Red Sox: Run Line", None, "baseball_mlb", "spread"),
    ("Celtics at Warriors", "KXNBA2HSPREAD-26MAY14BOSGSW", "basketball_nba", "spread"),
    ("Chiefs -3.5", None, "americanfootball_nfl", "spread"),
    # Player props.
    ("Aaron Judge Home Runs", None, "baseball_mlb", "player_prop"),
    ("Gerrit Cole Strikeouts", None, "baseball_mlb", "player_prop"),
    ("Jayson Tatum Points", None, "basketball_nba", "player_prop"),
    # Team-scoped derivatives.
    ("Yankees Team Total", None, "baseball_mlb", "team_prop"),
    ("First to Score", None, "icehockey_nhl", "team_prop"),
]


@pytest.mark.parametrize("name,ext,sport,expected", MONEYLINE_FIXTURES)
def test_moneyline_recognized(name, ext, sport, expected):
    assert classify_game_market_class(name, ext, sport) == expected, (
        f"{name!r} (ticker={ext!r}, {sport}) should classify as {expected}"
    )
    assert is_game_winner_market(name, ext, sport) is True


@pytest.mark.parametrize("name,ext,sport,expected", NON_MONEYLINE_FIXTURES)
def test_non_moneyline_classes(name, ext, sport, expected):
    assert classify_game_market_class(name, ext, sport) == expected, (
        f"{name!r} (ticker={ext!r}, {sport}) should classify as {expected}"
    )


def test_bare_matchup_detection():
    assert is_bare_matchup("Celtics at Warriors")
    assert is_bare_matchup("Yankees vs. Red Sox")
    assert is_bare_matchup("MLB: Yankees at Dodgers")
    assert is_bare_matchup("Will the Yankees beat the Red Sox?")
    # A sub-market qualifier means it is NOT a bare game-winner.
    assert not is_bare_matchup("Athletics vs. Chicago White Sox - Player Props")
    assert not is_bare_matchup("Yankees vs Red Sox: Total Runs O/U 8.5")
    assert not is_bare_matchup("Celtics at Warriors: Rebounds")


def test_container_and_junk_are_not_moneyline():
    # A "- Player Props" container must not be miscounted as a game winner.
    assert (
        classify_game_market_class(
            "Athletics vs. Chicago White Sox - Player Props", None, "baseball_mlb"
        )
        != "moneyline"
    )
    # A Polymarket condition hash alone (no name signal) is not a winner.
    assert not is_game_winner_market("", "0xabc123def456", "baseball_mlb")


def test_no_false_moneyline_from_substring():
    # "Winnipeg" contains "win" but is a team name, not a winner market.
    assert classify_game_market_class(
        "Winnipeg Jets Stanley Cup", None, "icehockey_nhl"
    ) != "moneyline"
