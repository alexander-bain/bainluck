"""#8632 — a club's sport word is never a bare ILIKE token.

WHAT A READER SAW, production 2026-09-25 ~14:00Z, `https://bainluck.com/events/15318532`
(Gargzdai Basketball v BC Neptunas Klaipeda, `basketball_other`): Bigger Picture →
Gargzdai → CHAMPIONSHIP PATH was every NBA and WNBA title, award, division and seed
market — `/related-futures` served **775 rows on Gargzdai's side, across 37
markets, and exactly ONE of them was Gargzdai's** (its own game line). The page
ran to 17,664 px.

WHY. `_team_name_patterns("Gargzdai Basketball")` emitted a bare `Basketball`,
which is a whole token of every `Pro Basketball …` / `Women's Pro Basketball …`
market title, so the market-name fallback admitted all of their answers. Neither
team resolves to a `teams` row, so #7867 and #8620 (which need a resolved club)
cannot see it. It is #7858's defect (`United`) with a sport in the mascot slot.

THE FIX adds sport words to `_CLUB_TYPE_DESIGNATORS`. Measured over production
before moving (`artifacts-lane1-815/measure_8632.py`, 2026-09-25): 305 distinct
team names (teams + events) lose a bare sport word; every production label that
is the sport word ALONE (231 outcome rows — `Handball` x112, `Soccer` x93,
`Football` x11, `Hockey` x9, `Basketball` x6) is an answer to a "What will the
announcers say…" mention market, not a club. LOSS 0. Control (`Texas Rangers`
hypothetically losing `Texas`): 4,608 labels — the 0 is a measurement.
"""

import pytest

from app.routes.events import (
    _CLUB_TYPE_DESIGNATORS,
    _NON_DISTINCTIVE_BARE_TOKENS,
    _team_name_patterns,
)
from app.utils.team_pattern_match import any_pattern_matches_token

HOME = "Gargzdai Basketball"
AWAY = "BC Neptunas Klaipeda"

#: Market titles served on Gargzdai's side, verbatim from the production payload.
_FOREIGN_MARKETS_ON_THE_PAGE = [
    "Pro Basketball Finals MVP Winner",
    "Pro Basketball Cup Tournament MVP Winner",
    "Pro Basketball Sixth Man of the Year Winner",
    "2026 Pro Basketball Cup Champion",
    "2027 Pro Basketball Champion",
    "9th Straight Different Pro Basketball Champion",
    "Women's Pro Basketball Champion",
    "Top 5 Pro Basketball Draft Pick Wins Rookie of the Year?",
]

#: The one row that WAS Gargzdai's, from the same payload.
_GARGZDAIS_OWN_MARKET = "Gargzdai Basketball vs. BC Neptunas Klaipeda"


class TestTheSpecimen:
    def test_gargzdai_no_longer_searches_on_its_sport(self):
        assert _team_name_patterns(HOME) == ["Gargzdai Basketball", "Gargzdai"]

    @pytest.mark.parametrize("market_name", _FOREIGN_MARKETS_ON_THE_PAGE)
    def test_a_pro_basketball_market_is_not_gargzdais(self, market_name):
        assert not any_pattern_matches_token(market_name, _team_name_patterns(HOME))

    def test_gargzdais_own_game_still_matches_both_sides(self):
        assert any_pattern_matches_token(_GARGZDAIS_OWN_MARKET, _team_name_patterns(HOME))
        assert any_pattern_matches_token(_GARGZDAIS_OWN_MARKET, _team_name_patterns(AWAY))


class TestEverySportWordSlot:
    """The shared set reaches all three emission sites; one production name per site."""

    @pytest.mark.parametrize(
        "team,expected",
        [
            # mascot slot (parts[-1])
            ("Lyon Rugby", ["Lyon Rugby", "Lyon"]),
            ("Montpellier Handball", ["Montpellier Handball", "Montpellier"]),
            ("Modo Hockey", ["Modo Hockey", "Modo"]),
            ("Valencia Basket", ["Valencia Basket", "Valencia"]),
            ("Enterprise Esports", ["Enterprise Esports", "Enterprise"]),
            # city half of a two-word name (#8061's site)
            ("Basket Zaragoza", ["Basket Zaragoza", "Zaragoza"]),
            ("Basketball Nymburk", ["Basketball Nymburk", "Nymburk"]),
            # the >=3-word loop
            ("Hong Kong Cricket Club",
             ["Hong Kong Cricket Club", "Club", "Hong Kong Cricket", "Hong", "Kong"]),
            ("Rodez Aveyron Football",
             ["Rodez Aveyron Football", "Rodez Aveyron", "Rodez", "Aveyron"]),
        ],
    )
    def test_the_sport_word_is_dropped_and_the_club_word_kept(self, team, expected):
        assert _team_name_patterns(team) == expected

    @pytest.mark.parametrize(
        "team,foreign_label",
        [
            ("Lyon Rugby", "Rugby World Cup Winner"),
            ("Montpellier Handball", "Handball"),       # a mention-market answer
            ("Modo Hockey", "Pro Hockey Champion"),
            ("Enterprise Esports", "Esports World Cup 2026 Winner"),
            ("Rodez Aveyron Football", "College Football Playoff"),
        ],
    )
    def test_a_market_about_the_sport_is_not_the_club(self, team, foreign_label):
        assert not any_pattern_matches_token(foreign_label, _team_name_patterns(team))


class TestRecallIsPreserved:
    @pytest.mark.parametrize(
        "team,own_label",
        [
            ("Gargzdai Basketball", "Gargzdai"),
            ("Paris Basketball", "Paris Basketball (-6.5)"),
            ("Cardiff Rugby", "Stormers/Cardiff Rugby"),
            ("Bilbao Basket", "Surne Bilbao Basket"),
            ("G2 Esports", "G2 Esports"),
            ("Rugby Borough FC", "Rugby Borough FC"),
        ],
    )
    def test_a_club_still_matches_its_own_row(self, team, own_label):
        assert any_pattern_matches_token(own_label, _team_name_patterns(team))

    def test_a_multi_word_pattern_containing_a_sport_word_is_untouched(self):
        """Only the BARE word goes: `Rugby Borough` (a town) survives as the city half."""
        assert "Rugby Borough" in _team_name_patterns("Rugby Borough FC")

    def test_an_unrelated_team_is_untouched(self):
        assert _team_name_patterns("Texas Rangers") == ["Texas Rangers", "Rangers", "Texas"]


class TestTheSet:
    @pytest.mark.parametrize(
        "word",
        ["basketball", "basket", "football", "soccer", "hockey", "handball",
         "volleyball", "baseball", "rugby", "cricket", "esports"],
    )
    def test_the_sport_word_is_a_club_type_designator(self, word):
        assert word in _CLUB_TYPE_DESIGNATORS
        assert word in _NON_DISTINCTIVE_BARE_TOKENS

    def test_the_earlier_designators_are_still_there(self):
        assert {"united", "city", "town", "real"} <= _CLUB_TYPE_DESIGNATORS
