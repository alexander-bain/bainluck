"""#191: golfer sparkline history must survive accent + first-name-variant
differences between the display name and the evolution-market outcome name.

The concept-page competitor name comes from Kalshi/Polymarket display
("Matt Fitzpatrick", "Ludvig Åberg") while the evolution-market outcome name is
raw DataGolf ("Matthew Fitzpatrick", "Ludvig Aberg"). An exact lowercase join
silently dropped the sparkline for those golfers on The Open concept page.

These cover the pure name-key helpers that back the tolerant, ambiguity-guarded
join in attach_competitor_history.
"""

from app.utils.event_concept import (
    _ascii_player_name,
    _last_first_initial_key,
    _norm_player_name,
)


class TestAsciiPlayerName:
    def test_strips_diacritics(self):
        assert _ascii_player_name("Ludvig Åberg") == "ludvig aberg"
        assert _ascii_player_name("Ludvig Aberg") == "ludvig aberg"
        assert _ascii_player_name("Nicolás Echavarría") == "nicolas echavarria"

    def test_matches_when_only_accents_differ(self):
        assert _ascii_player_name("Séamus Power") == _ascii_player_name("Seamus Power")


class TestLastFirstInitialKey:
    def test_bridges_nickname_variants(self):
        # The Matt Fitzpatrick bug: DataGolf "Matthew" vs Kalshi "Matt".
        assert _last_first_initial_key("Matthew Fitzpatrick") == "fitzpatrick|m"
        assert _last_first_initial_key("Matt Fitzpatrick") == "fitzpatrick|m"

    def test_distinguishes_different_first_initials(self):
        # Alex Fitzpatrick must NOT collide with Matt/Matthew Fitzpatrick.
        assert _last_first_initial_key("Alex Fitzpatrick") == "fitzpatrick|a"

    def test_strips_suffixes(self):
        assert _last_first_initial_key("Davis Love III") == "love|d"

    def test_single_token_returns_none(self):
        assert _last_first_initial_key("Cheng") is None
        assert _last_first_initial_key("") is None
        assert _last_first_initial_key(None) is None

    def test_diacritics_stripped_in_key(self):
        assert _last_first_initial_key("Ludvig Åberg") == "aberg|l"


class TestNormPlayerNameUnchanged:
    def test_still_exact_normalizes(self):
        assert _norm_player_name("  Scottie   Scheffler ") == "scottie scheffler"
