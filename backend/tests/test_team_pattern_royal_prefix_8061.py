"""#8061 — a finished Real Sociedad page stops grading Mbappé.

WHAT A READER SAW, production 2026-09-22 18:0xZ, `https://bainluck.com/events/15011303`
(Real Sociedad 4–1 Real Betis, La Liga, FINAL). Under **WHAT HIT — "the pregame
script, graded"** the page graded Real MADRID's squad on it:

    Kylian Mbappé: 1+        HIT
    Vinícius Júnior: 1+      HIT
    Jude Bellingham: 1+      MISS
    Federico Valverde: 1+    MISS
    TEAM CORNERS  Real Madrid: 7+   MISS

and `GET /api/events/15011303/game-markets` served, among others, seven
`Ajax vs Real Madrid: Total Goals` rows — a fixture with NEITHER of this event's
teams in it — plus `Chelsea vs Real Sociedad: Total Goals` and
`Real Madrid vs Real Sociedad: Goalscorer`.

WHY. `_team_name_patterns("Real Sociedad")` emitted a bare `Real`. Two
consequences, and the second is the one that let a third club's fixture in:

1. `Real` occupies whole tokens of `Real Madrid`, so #6806's boundary rule
   cannot refuse it — the token really is there, as it was for `United` (#7858).
2. **BOTH sides of this match emitted the same bare `Real`.** The game-markets
   fallback admits an unlinked market only when a HOME pattern and an AWAY
   pattern both appear in its name; `Ajax vs Real Madrid` satisfied both halves
   with the same three letters. The AND was structurally an OR on this fixture.

THE FIX is the #7858 gate reaching a site it had never reached. `Leeds United`
puts the designator in `parts[-1]`, which was gated; `Real Sociedad` puts it in
the CITY half, which was not. Recall census (in the comment above
`_CLUB_TYPE_DESIGNATORS`): no outcome row, market row or team row is labelled
`real` alone — LOSS 0.
"""

import pytest

from app.routes.events import (
    _CLUB_TYPE_DESIGNATORS,
    _GENERIC_PLACE_QUALIFIERS,
    _NON_DISTINCTIVE_BARE_TOKENS,
    _team_name_patterns,
)
from app.utils.team_pattern_match import any_pattern_matches_token

HOME = "Real Sociedad"
AWAY = "Real Betis"

#: Market names the served payload carried on this event, verbatim, that belong
#: to another fixture.
_FOREIGN_MARKETS_ON_THE_PAGE = [
    "Ajax vs Real Madrid: Total Goals",
    "Chelsea vs Real Sociedad: Total Goals",
    "Real Madrid vs Real Sociedad: Total Corners",
    "Real Madrid vs Real Sociedad: Goalscorer",
    "Real Madrid vs Real Sociedad: First Goalscorer",
    "Chelsea vs Real Sociedad: BTTS",
    "Real Madrid vs Real Sociedad San Sebastian: First Team to Score",
]

#: This fixture's own rows. A fix that drops these is a recall regression
#: wearing the right answer's clothes.
_THIS_FIXTURES_OWN_MARKETS = [
    "Real Sociedad vs Real Betis",
    "Real Sociedad vs Real Betis: Total Goals",
    "Real Sociedad 4 - 1 Real Betis",
    "Draw (Real Sociedad de Fútbol vs. Real Betis Balompié)",
]


def _admitted_by_the_game_markets_fallback(market_name: str) -> bool:
    """The route's own admission rule for an UNLINKED game market, in Python.

    `_build_game_markets` builds `home_conditions` and `away_conditions` from the
    two teams' patterns (each `len(p) >= 4`) and requires a match from BOTH —
    `ilike('%pattern%')` on the market name. Reproduced here rather than
    described, because the defect is precisely that the AND collapsed to an OR
    when both sides emitted the same token.
    """
    home = [p for p in _team_name_patterns(HOME) if len(p) >= 4]
    away = [p for p in _team_name_patterns(AWAY) if len(p) >= 4]
    lowered = market_name.lower()
    return (
        any(p.lower() in lowered for p in home)
        and any(p.lower() in lowered for p in away)
    )


class TestTheSpecimen:
    def test_neither_side_searches_on_a_bare_royal_prefix(self):
        assert _team_name_patterns(HOME) == ["Real Sociedad", "Sociedad"]
        assert _team_name_patterns(AWAY) == ["Real Betis", "Betis"]

    def test_the_two_sides_of_this_match_no_longer_match_each_other(self):
        """The sharpest arm: the bare token could not tell the HOME team from the
        AWAY team, which is what made a two-sided AND satisfiable by one club."""
        assert not any_pattern_matches_token(AWAY, _team_name_patterns(HOME))
        assert not any_pattern_matches_token(HOME, _team_name_patterns(AWAY))

    @pytest.mark.parametrize("market_name", _FOREIGN_MARKETS_ON_THE_PAGE)
    def test_another_fixtures_market_is_refused(self, market_name):
        assert not _admitted_by_the_game_markets_fallback(market_name)

    @pytest.mark.parametrize("market_name", _THIS_FIXTURES_OWN_MARKETS)
    def test_this_fixtures_own_markets_are_still_admitted(self, market_name):
        assert _admitted_by_the_game_markets_fallback(market_name)

    def test_ajax_v_real_madrid_needed_only_one_token_to_satisfy_both_sides(self):
        """Documents the mechanism, not just the outcome: the row names neither
        club, so after the fix neither half of the AND can be satisfied."""
        home = [p for p in _team_name_patterns(HOME) if len(p) >= 4]
        away = [p for p in _team_name_patterns(AWAY) if len(p) >= 4]
        row = "ajax vs real madrid: total goals"
        assert not any(p.lower() in row for p in home)
        assert not any(p.lower() in row for p in away)


class TestRecallIsPreserved:
    """The census measured 0 rows labelled `real` alone. These pin the mechanisms
    that make it 0 — every Real club still matches its own rows."""

    @pytest.mark.parametrize(
        "team,own_label",
        [
            ("Real Madrid", "Ajax vs Real Madrid: Total Goals"),
            ("Real Madrid", "Real Madrid CF"),
            ("Real Madrid", "Madrid"),
            ("Real Sociedad", "Real Sociedad de Fútbol"),
            ("Real Sociedad", "Sociedad"),
            ("Real Betis", "Real Betis Balompié"),
            ("Real Oviedo", "Real Oviedo vs Getafe CF"),
            ("Real Salt Lake", "Real Salt Lake (-1.5)"),
            ("Real Sporting de Gijón", "Real Sporting de Gijón"),
        ],
    )
    def test_a_real_club_still_matches_its_own_row(self, team, own_label):
        assert any_pattern_matches_token(own_label, _team_name_patterns(team))

    def test_a_three_word_real_club_keeps_its_multi_word_city(self):
        """Only the BARE token goes. `Real Salt` is multi-word and survives, the
        same line "Kansas City" is on."""
        assert _team_name_patterns("Real Salt Lake") == [
            "Real Salt Lake", "Lake", "Real Salt", "Salt",
        ]


class TestTheGateSiteThatWasMissed:
    """#7858 gated the mascot slot and the >=3-word loop. The CITY half of a
    two-word name was the third site, and it is where a front-loaded designator
    lands."""

    def test_the_designator_in_front_is_now_refused(self):
        assert "Real" not in _team_name_patterns("Real Sociedad")

    def test_the_designator_behind_is_still_refused(self):
        assert _team_name_patterns("Leeds United") == ["Leeds United", "Leeds"]

    @pytest.mark.parametrize(
        "team,expected",
        [
            # A multi-word city half containing a designator is untouched.
            ("Kansas City Chiefs",
             ["Kansas City Chiefs", "Chiefs", "Kansas City", "Kansas"]),
            ("Oklahoma City Thunder",
             ["Oklahoma City Thunder", "Thunder", "Oklahoma City", "Oklahoma"]),
            ("West Ham United", ["West Ham United", "West Ham"]),
            # An ordinary city half is still emitted — Kalshi labels outcomes
            # "Texas" and "Houston", and dropping those would cost real recall.
            ("Texas Rangers", ["Texas Rangers", "Rangers", "Texas"]),
            ("Los Angeles Dodgers",
             ["Los Angeles Dodgers", "Dodgers", "Los Angeles", "Angeles"]),
        ],
    )
    def test_the_other_city_halves_are_untouched(self, team, expected):
        assert _team_name_patterns(team) == expected


class TestTheGateReachesBeyondReal:
    """The city-half gate is not scoped to `real`, so its other 33 teams are
    pinned here rather than left to be discovered by a reader.

    Measured over all 5,642 distinct production team names
    (`artifacts-lane1-600/measure_8061_reach.py`): 48 teams lose a bare pattern
    across 10 tokens. The LOSS census over production rows
    (`measure_8061_loss.py`) is **0** — with a control that reports 4,380, so the
    0 is a measurement. These arms pin the mechanism that makes it 0: the team
    keeps a distinctive pattern.
    """

    @pytest.mark.parametrize(
        "team,expected",
        [
            ("South Korea", ["South Korea", "Korea"]),
            ("South Africa", ["South Africa", "Africa"]),
            ("Saint Etienne", ["Saint Etienne", "Etienne"]),
            ("Central Michigan", ["Central Michigan", "Michigan"]),
            ("Western Carolina", ["Western Carolina", "Carolina"]),
            ("Eastern Kentucky", ["Eastern Kentucky", "Kentucky"]),
            ("Northern Ireland", ["Northern Ireland", "Ireland"]),
            ("West Virginia", ["West Virginia", "Virginia"]),
        ],
    )
    def test_a_front_loaded_qualifier_goes_and_the_distinctive_word_stays(
        self, team, expected
    ):
        assert _team_name_patterns(team) == expected

    @pytest.mark.parametrize("team", ["West Ham", "Northern City"])
    def test_the_two_teams_left_with_only_a_full_name_still_match_themselves(
        self, team
    ):
        """Both words of these names are non-distinctive, so the full name is all
        that survives. That is correct — a bare `West` or `Northern` is exactly
        the leak — but it must still reach the club's own rows."""
        patterns = _team_name_patterns(team)
        assert patterns == [team]
        assert any_pattern_matches_token(f"{team} United", patterns)
        assert any_pattern_matches_token(f"{team} vs Arsenal", patterns)

    def test_west_ham_no_longer_answers_to_another_west_club(self):
        assert not any_pattern_matches_token(
            "West Bromwich Albion", _team_name_patterns("West Ham")
        )
        assert not any_pattern_matches_token(
            "Western Sydney Wanderers", _team_name_patterns("West Ham")
        )

    def test_south_korea_no_longer_answers_to_south_african_economics(self):
        """A real row the bare token reached: the FX and central-bank markets the
        census found under `south`. Neither is a football fixture."""
        patterns = _team_name_patterns("South Korea")
        assert not any_pattern_matches_token(
            "US Dollar / South African Rand (USD/ZAR) Up or Down on August 10?",
            patterns,
        )
        assert not any_pattern_matches_token(
            "South African Reserve Bank Decision in May?", patterns
        )


class TestSiblingClasses:
    def test_7858_united_is_still_in_the_set_and_still_refused(self):
        assert "united" in _CLUB_TYPE_DESIGNATORS
        assert not any_pattern_matches_token(
            "United Arab Emirates", _team_name_patterns("Leeds United")
        )

    def test_5798_place_qualifiers_still_refused(self):
        patterns = _team_name_patterns("Arkansas State Red Wolves")
        assert patterns == [
            "Arkansas State Red Wolves", "Wolves", "Arkansas State Red", "Arkansas",
        ]

    def test_6806_whole_token_rule_still_applies(self):
        assert not any_pattern_matches_token(
            "Anderlecht", _team_name_patterns("Lech Poznań")
        )

    def test_the_two_families_are_disjoint_and_unioned(self):
        assert _GENERIC_PLACE_QUALIFIERS & _CLUB_TYPE_DESIGNATORS == frozenset()
        assert (
            _NON_DISTINCTIVE_BARE_TOKENS
            == _GENERIC_PLACE_QUALIFIERS | _CLUB_TYPE_DESIGNATORS
        )
