"""Tests for the shared season-windows helper (Queue #196 Item 3).

The single source of truth for "is this league in season?" — drives the Grid
Sentinel artifact registry and break-aware seasonality in the data-quality
watchdog's coverage-drop alarm. `now` is injected so these are date-stable.
"""

from datetime import datetime, timezone

from app.utils import season_windows as sw


def _d(month, day):
    return datetime(2026, month, day, 12, 0, tzinfo=timezone.utc)


class TestLeaguePhase:
    def test_mlb_regular_season(self):
        assert sw.league_phase("mlb", _d(5, 1)) == "in_season"

    def test_mlb_all_star_break(self):
        # Mid-July is the All-Star break.
        assert sw.league_phase("mlb", _d(7, 15)) == "break"

    def test_mlb_postseason(self):
        assert sw.league_phase("mlb", _d(10, 20)) == "postseason"

    def test_mlb_offseason(self):
        assert sw.league_phase("mlb", _d(1, 15)) == "offseason"

    def test_nba_offseason_in_july(self):
        assert sw.league_phase("nba", _d(7, 14)) == "offseason"

    def test_nba_regular_season_wraps_new_year(self):
        assert sw.league_phase("nba", _d(1, 5)) == "in_season"
        assert sw.league_phase("nba", _d(11, 20)) == "in_season"

    def test_nba_playoffs(self):
        assert sw.league_phase("nba", _d(5, 20)) == "postseason"

    def test_nhl_offseason_in_july(self):
        assert sw.league_phase("nhl", _d(7, 14)) == "offseason"

    def test_nfl_in_season_wraps(self):
        assert sw.league_phase("nfl", _d(10, 1)) == "in_season"
        assert sw.league_phase("nfl", _d(1, 1)) == "in_season"

    def test_unknown_league_defaults_in_season(self):
        # Never suppress an alarm for a league we don't model.
        assert sw.league_phase("cricket", _d(7, 14)) == "in_season"

    def test_golf_is_continuous(self):
        assert sw.league_phase("golf", _d(1, 1)) == "in_season"
        assert sw.league_phase("golf", _d(7, 14)) == "in_season"

    def test_case_insensitive(self):
        assert sw.league_phase("MLB", _d(5, 1)) == "in_season"


class TestPredicates:
    def test_is_offseason(self):
        assert sw.is_offseason("nba", _d(7, 14)) is True
        assert sw.is_offseason("mlb", _d(5, 1)) is False

    def test_is_break(self):
        assert sw.is_break("mlb", _d(7, 15)) is True
        assert sw.is_break("mlb", _d(5, 1)) is False

    def test_is_active(self):
        assert sw.is_active("mlb", _d(5, 1)) is True
        assert sw.is_active("mlb", _d(10, 20)) is True  # postseason counts as active
        assert sw.is_active("nba", _d(7, 14)) is False

    def test_is_quiet(self):
        assert sw.is_quiet("nba", _d(7, 14)) is True   # offseason
        assert sw.is_quiet("mlb", _d(7, 15)) is True    # break
        assert sw.is_quiet("mlb", _d(5, 1)) is False


class TestSeasonalNote:
    def test_offseason_note(self):
        note = sw.seasonal_note("nba", _d(7, 14))
        assert note is not None and "offseason" in note.lower()

    def test_break_note(self):
        note = sw.seasonal_note("mlb", _d(7, 15))
        assert note is not None and "break" in note.lower()

    def test_active_no_note(self):
        assert sw.seasonal_note("mlb", _d(5, 1)) is None
        assert sw.seasonal_note("nba", _d(1, 5)) is None
