"""Tests for pure/near-pure helper functions in tasks/odds_polling.py.

Covers:
- get_max_duration_for_sport: sport key → max duration lookup
- _snapshots_are_equal: write-time dedup comparison logic
- get_statpal_end_time: StatPal end time extraction (column + JSONB fallback)
"""

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.tasks.odds_polling import get_max_duration_for_sport, _snapshots_are_equal, get_statpal_end_time
from app.tasks.config import SPORT_MAX_DURATIONS


# ── get_max_duration_for_sport ──────────────────────────────────────────


class TestGetMaxDurationForSport:
    """Tests for sport key → max game duration mapping."""

    def test_exact_prefix_tennis(self):
        assert get_max_duration_for_sport("tennis_atp") == 6.0

    def test_exact_prefix_tennis_wta(self):
        assert get_max_duration_for_sport("tennis_wta") == 6.0

    def test_basketball_nba(self):
        assert get_max_duration_for_sport("basketball_nba") == 3.5

    def test_basketball_ncaab(self):
        assert get_max_duration_for_sport("basketball_ncaab") == 3.5

    def test_americanfootball_nfl(self):
        assert get_max_duration_for_sport("americanfootball_nfl") == 4.5

    def test_americanfootball_ncaaf(self):
        assert get_max_duration_for_sport("americanfootball_ncaaf") == 4.5

    def test_icehockey_nhl(self):
        assert get_max_duration_for_sport("icehockey_nhl") == 3.5

    def test_baseball_mlb(self):
        assert get_max_duration_for_sport("baseball_mlb") == 5.0

    def test_golf_pga(self):
        assert get_max_duration_for_sport("golf_pga") == 8.0

    def test_mma_ufc(self):
        assert get_max_duration_for_sport("mma_ufc") == 4.0

    def test_boxing(self):
        assert get_max_duration_for_sport("boxing_any") == 3.0

    def test_lacrosse(self):
        assert get_max_duration_for_sport("lacrosse_pll") == 3.0

    def test_unknown_sport_returns_default(self):
        assert get_max_duration_for_sport("cricket_test") == 4.0

    def test_empty_string_returns_default(self):
        assert get_max_duration_for_sport("") == 4.0

    def test_default_value_in_config(self):
        """Verify the default key exists in the config dict."""
        assert "default" in SPORT_MAX_DURATIONS
        assert SPORT_MAX_DURATIONS["default"] == 4.0


# ── _snapshots_are_equal ────────────────────────────────────────────────


def _make_snapshot(**kwargs):
    """Create a mock OddsSnapshot with the given field values."""
    defaults = {
        "home_moneyline": -150,
        "away_moneyline": 130,
        "home_spread": -3.5,
        "over_under": 210.5,
        "home_win_probability": 0.6,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_values(**kwargs):
    """Create a new_values dict with the given overrides."""
    defaults = {
        "home_moneyline": -150,
        "away_moneyline": 130,
        "home_spread": -3.5,
        "over_under": 210.5,
        "home_win_probability": 0.6,
    }
    defaults.update(kwargs)
    return defaults


class TestSnapshotsAreEqual:
    """Tests for the write-time dedup comparison function."""

    def test_identical_values_are_equal(self):
        snap = _make_snapshot()
        vals = _make_values()
        assert _snapshots_are_equal(snap, vals) is True

    def test_different_home_moneyline(self):
        snap = _make_snapshot(home_moneyline=-150)
        vals = _make_values(home_moneyline=-160)
        assert _snapshots_are_equal(snap, vals) is False

    def test_different_away_moneyline(self):
        snap = _make_snapshot(away_moneyline=130)
        vals = _make_values(away_moneyline=120)
        assert _snapshots_are_equal(snap, vals) is False

    def test_different_home_spread(self):
        snap = _make_snapshot(home_spread=-3.5)
        vals = _make_values(home_spread=-4.0)
        assert _snapshots_are_equal(snap, vals) is False

    def test_different_over_under(self):
        snap = _make_snapshot(over_under=210.5)
        vals = _make_values(over_under=211.0)
        assert _snapshots_are_equal(snap, vals) is False

    def test_different_win_probability(self):
        snap = _make_snapshot(home_win_probability=0.6)
        vals = _make_values(home_win_probability=0.65)
        assert _snapshots_are_equal(snap, vals) is False

    def test_both_none_are_equal(self):
        snap = _make_snapshot(home_moneyline=None)
        vals = _make_values(home_moneyline=None)
        assert _snapshots_are_equal(snap, vals) is True

    def test_existing_none_new_has_value(self):
        snap = _make_snapshot(home_moneyline=None)
        vals = _make_values(home_moneyline=-150)
        assert _snapshots_are_equal(snap, vals) is False

    def test_existing_has_value_new_none(self):
        snap = _make_snapshot(home_moneyline=-150)
        vals = _make_values(home_moneyline=None)
        assert _snapshots_are_equal(snap, vals) is False

    def test_int_vs_float_are_equal(self):
        """Integer -150 and float -150.0 should compare as equal."""
        snap = _make_snapshot(home_moneyline=-150)
        vals = _make_values(home_moneyline=-150.0)
        assert _snapshots_are_equal(snap, vals) is True

    def test_missing_key_in_new_values_treated_as_none(self):
        """If a key is missing from new_values dict, .get() returns None."""
        snap = _make_snapshot(home_moneyline=None)
        vals = _make_values()
        del vals["home_moneyline"]
        assert _snapshots_are_equal(snap, vals) is True

    def test_all_none_are_equal(self):
        snap = _make_snapshot(
            home_moneyline=None, away_moneyline=None,
            home_spread=None, over_under=None,
            home_win_probability=None,
        )
        vals = _make_values(
            home_moneyline=None, away_moneyline=None,
            home_spread=None, over_under=None,
            home_win_probability=None,
        )
        assert _snapshots_are_equal(snap, vals) is True


# ── get_statpal_end_time ──────────────────────────────────────────────


class TestGetStatpalEndTime:
    """Tests for extracting StatPal end time from event objects."""

    def test_column_value_returned(self):
        """Dedicated column statpal_end_time should be returned directly."""
        end = datetime(2026, 2, 25, 22, 0, tzinfo=timezone.utc)
        event = SimpleNamespace(statpal_end_time=end, win_probability_sources=None)
        assert get_statpal_end_time(event) == end

    def test_jsonb_fallback(self):
        """Falls back to win_probability_sources JSONB when column is None."""
        event = SimpleNamespace(
            statpal_end_time=None,
            win_probability_sources={"statpal_end_time": "2026-02-25T22:00:00+00:00"},
        )
        result = get_statpal_end_time(event)
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.hour == 22

    def test_neither_source_returns_none(self):
        """Returns None when neither column nor JSONB has end time."""
        event = SimpleNamespace(statpal_end_time=None, win_probability_sources={})
        assert get_statpal_end_time(event) is None

    def test_none_sources_returns_none(self):
        """Returns None when win_probability_sources is None entirely."""
        event = SimpleNamespace(statpal_end_time=None, win_probability_sources=None)
        assert get_statpal_end_time(event) is None

    def test_invalid_iso_string_returns_none(self):
        """Invalid ISO string in JSONB should not crash, returns None."""
        event = SimpleNamespace(
            statpal_end_time=None,
            win_probability_sources={"statpal_end_time": "not-a-date"},
        )
        assert get_statpal_end_time(event) is None

    def test_column_preferred_over_jsonb(self):
        """Column value takes priority when both exist."""
        col_end = datetime(2026, 2, 25, 22, 0, tzinfo=timezone.utc)
        event = SimpleNamespace(
            statpal_end_time=col_end,
            win_probability_sources={"statpal_end_time": "2026-02-25T23:00:00+00:00"},
        )
        result = get_statpal_end_time(event)
        assert result == col_end  # Column value, not JSONB value
