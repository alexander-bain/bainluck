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


def test_a_team_name_that_is_not_english_is_still_a_game_winner():
    """#5041 — the team-token class was ASCII, so accents read as "not a game".

    MEASURED over every Polymarket market linked to an event commencing within
    48h (1,096 markets / 210 events, production 2026-09-11): 257 are a bare
    matchup carrying no sub-market qualifier, and 12 of them — 12 distinct
    events, every one a real match winner — were classified `other` for their
    diacritics alone. The bias ran one way: La Liga 2, Bundesliga, Liga MX,
    Brasileirão, Serie B, and US college teams with a parenthesised state.

    These are the production strings, not names invented from the pattern.
    """
    for name in (
        "1. FC Köln vs. SV Werder Bremen",
        "Club León FC vs. Atlético San Luis",
        "Associação Chapecoense de Futebol vs. SC Internacional",
        "SE Palmeiras vs. São Paulo FC",
        "Cádiz CF vs. UD Las Palmas",
        "Granada CF vs. Albacete Balompié",
        "VfL Bochum vs. SpVgg Greuther Fürth",
        "Holy Cross vs. Miami (OH)",
    ):
        assert is_bare_matchup(name), name
        assert classify_game_market_class(name, None) == "moneyline", name


def test_widening_the_team_class_did_not_admit_the_qualified_twins():
    """The guard that rejects a sub-market is the ":"/" - " test, not the letters.

    Every name here is the SAME fixture as above wearing a qualifier. If the
    widened class starts swallowing the qualifier into the second team token,
    a halftime or exact-score book becomes a game winner — which is the defect
    on the other side of this change.
    """
    for name in (
        "1. FC Köln vs. SV Werder Bremen - Exact Score",
        "Club León FC vs. Atlético San Luis - Player Props",
        "SE Palmeiras vs. São Paulo FC - Halftime Result",
        "VfL Bochum vs. SpVgg Greuther Fürth: O/U 2.5",
        "Cádiz CF vs. UD Las Palmas - More Markets",
        "Holy Cross vs. Miami (OH) - Second Half Result",
    ):
        assert not is_bare_matchup(name), name
        assert classify_game_market_class(name, None) != "moneyline", name


def test_a_matchup_behind_a_competition_prefix_is_the_match_winner():
    """#5660 — a tournament prefix made a real fixture invisible to the recognizer.

    The old test asked whether a ":" or a " - " appeared ANYWHERE in the title
    and answered "not a bare game" if one did. That is right for a qualifier
    hung off the END and wrong for a competition hung off the FRONT, which is
    how Polymarket titles most of its tennis, rugby, cricket, pickleball and
    doubles fixtures and how Kalshi titles its fight cards.

    MEASURED over every Polymarket/Kalshi market linked to an event commencing
    within +/-7 days (1,752 distinct names, production 2026-09-12): 408 names
    move `other` -> `moneyline` and ZERO move the other way.

    These are production strings, not names invented from the pattern.
    """
    for name in (
        "US Open ATP: Alexander Zverev vs Ben Shelton",
        "US Open WTA: Anna Kalinskaya vs Emma Navarro",
        "US Open ATP (Doubles): Bolelli/Vavassori vs Gille/Verbeek",
        "US Open WTA (Doubles): Bondar/Kalinina vs Routliffe/Sutjiadi",
        "M25 Sintra: Dino Molokova Ferreira vs Lucas Nunez",
        "W50 Guiyang: Anastasia Kulikova vs Haruka Kaji",
        "M15 Leme (moved from Sao Luis): Gabriel Schenekenberg vs Victor Pagotto",
        "Guadalajara Open Akron, Qualification: Carole Monnet vs Julia Garcia",
        "Barranquilla: Anastasia Tikhonova vs Darja Semenistaja",
        "Top 14: Bayonne vs ASM Clermont Auvergne",
        "United Rugby Championship: Benetton Treviso vs Dragons",
        "Premiership Rugby: Harlequins vs Bath",
        "T20 Series Japan vs Malaysia, Women: Japan vs Malaysia",
        "Test Series England vs Pakistan: England vs Pakistan",
        "Fight Night: Aldrich vs Tarin",
        "MMA: Kozak vs Echols",
    ):
        assert is_bare_matchup(name), name
        assert classify_game_market_class(name, None) == "moneyline", name


def test_the_issues_own_gamma_specimen_classifies_moneyline():
    """#5660's acceptance, stated as the issue states it.

    Polymarket Gamma event `1007524`, read live 2026-09-12: active,
    non-neg-risk, ONE market, `sportsMarketType=moneyline`. That row IS the
    match winner and the venue says so; we answered `other` for the prefix
    alone, while the identical bare matchup answered `moneyline`.
    """
    prefixed = "PPA - Women's Singles: Hannah Blatt vs Polina Libo"
    bare = "Hannah Blatt vs. Polina Libo"
    assert classify_game_market_class(prefixed, "1007524", "tennis") == "moneyline"
    assert classify_game_market_class(bare, "1007524", "tennis") == "moneyline"


def test_a_segment_prefix_is_not_a_competition_prefix():
    """The head is free to name a PART of the match — and then it is not the match.

    This is the defect on the other side of #5660: a strip that trusted any
    prefix would publish a set winner, a map handicap or a golf head-to-head as
    the contest's moneyline, which is exactly the #5031/#5273/#5432 class.
    Production strings; the first four are the largest prefix families in the
    measured window (493 + 439 + 118 + 64 rows).

    Asserted on `is_bare_matchup`, the predicate this change touches. Four of
    these ALSO carry a derivative word that other, older branches read, so
    `classify_game_market_class` answers before the matchup test is reached —
    see the companion test for the two that it answers WRONGLY today (#5698).
    """
    for name in (
        "Set Handicap: Abasolo (-1.5) vs Marques (+1.5)",
        "Set 1 Winner: Aboian vs Martin",
        "Set 2 Winner: Aboian vs Martin",
        "Game Spread: Acosta (-0.5) vs Munar (+0.5)",
        "Map Handicap: 1WIN (-1.5) vs Heroic (+1.5)",
        "Map 2 Rounds Handicap: B8 (-3.5) vs Nuclear TigeRES (+3.5)",
        "1st Round Head-to-Head: Åberg vs Fleetwood",
        "Will there be a run scored in the first inning?: "
        "Chicago White Sox vs. Cleveland Guardians",
    ):
        assert not is_bare_matchup(name), name


def test_a_segment_scope_prefix_is_refused_by_name():
    """`_DERIVATIVE_SCOPE_RE` is MEASURED INERT and kept as the fail-closed margin.

    Over the 1,752-name production window it blocked nothing the module's
    existing vocabulary did not already block. It is here because the esports
    rows carry these scopes TODAY as a SUFFIX ("Counter-Strike: 1WIN vs B8 -
    Map 1 Winner", 151 rows, refused by the " - " test), and a venue that moves
    one to the front must not thereby publish a map winner as the match winner.

    These inputs are therefore MANUFACTURED, not observed, and this test is the
    only thing standing between that clause and vacuity: delete the scope
    pattern from `_PREFIX_DISQUALIFIERS` and every line here goes green-to-red.
    """
    for name in (
        "Map 1: 1WIN vs B8",
        "Period 2: Bruins vs Rangers",
        "Quarter 3: Celtics vs Warriors",
        "Frame 4: O'Sullivan vs Trump",
        "Game 5: Yankees vs Red Sox",
    ):
        assert not is_bare_matchup(name), name
        assert classify_game_market_class(name, None) != "moneyline", name


def test_a_trailing_qualifier_is_still_refused_when_a_prefix_is_present():
    """A qualifier trails the matchup, so the unchanged ":"/" - " test sees it.

    `Counter-Strike: 1WIN vs B8 - Map 1 Winner` is 151 production rows, and it
    is the case that shows why the tail is re-tested rather than trusted: its
    dash-bearing second token is one `_BARE_MATCHUP_RE` would happily swallow.
    """
    for name in (
        "Counter-Strike: 1WIN vs B8 - Map 1 Winner",
        "US Open ATP: Alexander Zverev vs Ben Shelton - Exact Score",
        "M25 Sintra: Dino Molokova Ferreira vs Lucas Nunez: Total Games",
    ):
        assert not is_bare_matchup(name), name


def test_a_multi_segment_competition_head_is_read_whole():
    """Pins the last-colon split, which is otherwise unobservable.

    Every title in the measured window carries exactly ONE colon, so a
    first-colon and a last-colon split agree on all 1,752 of them and a
    mutation between the two survives the rest of this file. They diverge only
    here: a head of two competition segments, which a first-colon split refuses
    (its tail still holds a ":") and this one admits.

    Admitting it is safe for a stated reason, not by luck — the disqualifier
    test reads the ENTIRE head, so a derivative word in any segment still
    refuses, which the second case pins. This input is manufactured; multi-colon
    titles are unobserved in the window.
    """
    assert is_bare_matchup("US Open ATP: Qualification: Carole Monnet vs Julia Garcia")
    assert not is_bare_matchup("US Open ATP: Set 1 Winner: Carole Monnet vs Julia Garcia")
