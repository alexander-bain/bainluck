"""Queue #246 Item 1c / #1204 family — the odds-provider city-only duplicate
("Boston", NHL) must not shadow the real franchise ("Boston Bruins") in search,
while legit single-token clubs (Arsenal, Chelsea) are never suppressed."""
from types import SimpleNamespace

from app.routes.events import _dedupe_prefix_duplicate_team_rows


def _row(name, sport_key):
    return SimpleNamespace(name=name, sport_key=sport_key)


def _names(rows):
    return sorted(r.name for r in rows)


def test_drops_city_only_duplicate_same_sport():
    rows = [_row("Boston", "icehockey_nhl"), _row("Boston Bruins", "icehockey_nhl")]
    assert _names(_dedupe_prefix_duplicate_team_rows(rows)) == ["Boston Bruins"]


def test_keeps_legit_single_token_soccer_clubs():
    # Arsenal/Chelsea have no "Arsenal <x>" sibling in-league → untouched.
    rows = [_row("Arsenal", "soccer_epl"), _row("Chelsea", "soccer_epl")]
    assert _names(_dedupe_prefix_duplicate_team_rows(rows)) == ["Arsenal", "Chelsea"]


def test_prefix_guard_is_same_sport_only():
    # A same-name city in a DIFFERENT sport with no fuller sibling stays.
    rows = [
        _row("New York", "basketball_nba"),
        _row("New York Knicks", "basketball_nba"),
        _row("New York", "soccer_usa_mls"),  # RBNY city-only, no fuller MLS sibling here
    ]
    kept = _names(_dedupe_prefix_duplicate_team_rows(rows))
    assert "New York Knicks" in kept
    assert "New York" in kept          # the MLS one survives (nothing covers it)
    assert kept.count("New York") == 1  # the NBA city-only was dropped


def test_word_boundary_not_substring():
    # "York" must NOT be treated as a prefix-dup of "New York" (needs a space break).
    rows = [_row("York", "soccer_efl"), _row("New York City", "soccer_usa_mls")]
    assert len(_dedupe_prefix_duplicate_team_rows(rows)) == 2


def test_empty_and_none_safe():
    assert _dedupe_prefix_duplicate_team_rows([]) == []
    rows = [_row("", "x"), _row("Boston Bruins", "icehockey_nhl")]
    assert _names(_dedupe_prefix_duplicate_team_rows(rows)) == ["", "Boston Bruins"]
