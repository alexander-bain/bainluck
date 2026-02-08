"""Tests for _filter_stale_bookmaker_snapshots in events.py.

This filter prevents stale pregame odds from contaminating the aggregate
probability displayed on the event detail page. The bug it prevents:
bookmakers that stopped updating during a live game contribute their
pregame values (e.g., 59%) to the aggregate even though live bookmakers
show 2%. The filter must run for ALL non-scheduled statuses (live,
completed, closed) — not just live.
"""

import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.utils.odds_filtering import filter_stale_bookmaker_snapshots as _filter_stale_bookmaker_snapshots


def _snap(bookmaker: str, captured_at: datetime, home_prob: float | None = 0.5):
    """Create a lightweight snapshot-like object for testing."""
    return SimpleNamespace(
        bookmaker=bookmaker,
        captured_at=captured_at,
        home_win_probability=home_prob,
    )


@pytest.fixture
def commence_time():
    """Game start time."""
    return datetime(2026, 2, 7, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def pregame(commence_time):
    """Timestamp before game started (pregame odds)."""
    return commence_time - timedelta(hours=1)


@pytest.fixture
def live(commence_time):
    """Timestamp after game started (live odds)."""
    return commence_time + timedelta(minutes=30)


class TestScheduledEventsPassthrough:
    """Scheduled events should return all snapshots unchanged."""

    def test_scheduled_returns_all(self, commence_time, pregame):
        snaps = [_snap("bookA", pregame, 0.55), _snap("bookB", pregame, 0.60)]
        result = _filter_stale_bookmaker_snapshots(snaps, "scheduled", commence_time)
        assert result == snaps

    def test_scheduled_ignores_commence_time(self, pregame):
        snaps = [_snap("bookA", pregame, 0.55)]
        result = _filter_stale_bookmaker_snapshots(snaps, "scheduled", None)
        assert result == snaps


class TestLiveGames:
    """Live games should filter out pregame-only bookmakers."""

    def test_filters_pregame_bookmakers(self, commence_time, pregame, live):
        snaps = [
            _snap("stale_book", pregame, 0.59),   # pregame only
            _snap("live_book", live, 0.02),         # updated during game
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"

    def test_keeps_all_live_bookmakers(self, commence_time, live):
        snaps = [
            _snap("bookA", live, 0.02),
            _snap("bookB", live + timedelta(minutes=5), 0.03),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 2

    def test_falls_back_when_no_live_probs(self, commence_time, pregame, live):
        """If live snapshots have no probability, fall back to all."""
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, None),  # live but no prob
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert result == snaps


class TestCompletedGames:
    """Completed games MUST also filter — this was the original bug."""

    def test_completed_filters_pregame_bookmakers(self, commence_time, pregame, live):
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "completed", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"

    def test_closed_filters_pregame_bookmakers(self, commence_time, pregame, live):
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "closed", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"


class TestEdgeCases:
    def test_empty_snapshots(self, commence_time):
        result = _filter_stale_bookmaker_snapshots([], "live", commence_time)
        assert result == []

    def test_no_commence_time(self, pregame):
        snaps = [_snap("bookA", pregame, 0.55)]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", None)
        assert result == snaps

    def test_all_pregame_falls_back(self, commence_time, pregame):
        """If ALL bookmakers are pregame, return all (better than nothing)."""
        snaps = [
            _snap("bookA", pregame, 0.55),
            _snap("bookB", pregame, 0.60),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert result == snaps

    def test_snapshot_exactly_at_commence_time(self, commence_time):
        """Snapshot captured exactly at commence_time counts as live."""
        snaps = [_snap("bookA", commence_time, 0.50)]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
