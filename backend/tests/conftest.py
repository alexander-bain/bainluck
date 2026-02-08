"""Shared test fixtures for the OddsTracker backend test suite."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.pulse import PulseDataPoint


@pytest.fixture
def game_start():
    """A game start time for testing."""
    return datetime(2026, 2, 1, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def current_time(game_start):
    """A current time 2 hours after game start."""
    return game_start + timedelta(hours=2)


@pytest.fixture
def make_snapshots(game_start):
    """Factory for creating PulseDataPoint lists.

    Usage:
        snapshots = make_snapshots([0.50, 0.55, 0.48, 0.52], interval_seconds=60)
    """
    def _make(probabilities, interval_seconds=60, bookmaker="consensus"):
        return [
            PulseDataPoint(
                captured_at=game_start + timedelta(seconds=i * interval_seconds),
                home_win_probability=p,
                bookmaker=bookmaker,
            )
            for i, p in enumerate(probabilities)
        ]
    return _make


@pytest.fixture
def make_multi_bookmaker_snapshots(game_start):
    """Factory for creating multi-bookmaker snapshots at same timestamps.

    Usage:
        snapshots = make_multi_bookmaker_snapshots([
            [0.50, 0.51, 0.49],  # 3 bookmakers at t=0
            [0.55, 0.56, 0.54],  # 3 bookmakers at t=60s
        ])
    """
    def _make(prob_groups, interval_seconds=60):
        bookmakers = ["fanduel", "draftkings", "betmgm", "caesars", "pointsbet"]
        snapshots = []
        for i, probs in enumerate(prob_groups):
            t = game_start + timedelta(seconds=i * interval_seconds)
            for j, p in enumerate(probs):
                snapshots.append(PulseDataPoint(
                    captured_at=t,
                    home_win_probability=p,
                    bookmaker=bookmakers[j % len(bookmakers)],
                ))
        return snapshots
    return _make
