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


class TestSeasonString:
    def test_wrap_league_in_season(self):
        # April 2026 → the 2025-26 season is being played.
        assert sw.season_string("nba", _d(4, 1)) == "2025-26"
        assert sw.season_string("nhl", _d(4, 1)) == "2025-26"

    def test_wrap_league_fall_start(self):
        # December 2026 → the 2026-27 season has started.
        assert sw.season_string("nba", _d(12, 1)) == "2026-27"

    def test_wrap_league_offseason_points_upcoming(self):
        # July 2026 (offseason) → the upcoming 2026-27 season.
        assert sw.season_string("nba", _d(7, 14)) == "2026-27"

    def test_mlb_calendar_year(self):
        assert sw.season_string("mlb", _d(5, 1)) == "2026"

    def test_mlb_late_offseason_points_next_year(self):
        # November 2026 (post-World-Series) → next season 2027.
        assert sw.season_string("mlb", _d(11, 20)) == "2027"

    def test_nfl_starting_year(self):
        # September 2026 → the 2026 season.
        assert sw.season_string("nfl", _d(9, 15)) == "2026"

    def test_nfl_january_is_prior_season(self):
        # January 2026 playoffs → still the 2025 season.
        assert sw.season_string("nfl", _d(1, 20)) == "2025"

    def test_unknown_league_none(self):
        assert sw.season_string("golf", _d(5, 1)) is None
        assert sw.season_string("", _d(5, 1)) is None


class TestSeasonDescriptor:
    def test_shape(self):
        d = sw.season_descriptor("mlb", _d(5, 1))
        assert d["league"] == "mlb"
        assert d["season"] == "2026"
        assert d["phase"] == "in_season"
        assert d["label"] == "2026 · Regular season"

    def test_postseason_label(self):
        d = sw.season_descriptor("mlb", _d(10, 15))
        assert d["phase"] == "postseason"
        assert "Playoffs" in d["label"]

    def test_offseason_wrap_upcoming(self):
        d = sw.season_descriptor("nba", _d(7, 14))
        assert d["season"] == "2026-27"
        assert d["phase"] == "offseason"

    def test_unknown_league_still_returns_descriptor(self):
        d = sw.season_descriptor("golf", _d(5, 1))
        assert d["season"] is None
        # continuous leagues never suppress → phase is in_season
        assert d["phase"] == "in_season"


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
