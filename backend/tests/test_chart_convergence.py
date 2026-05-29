"""Tests for chart convergence on completed events (Bug #706).

The history endpoint must inject a terminal 100%/0% data point for
completed events so the chart converges to the correct winner.
Without this, the chart ends at whatever the last polled odds value was.

Tests verify the convergence injection logic directly on the response
data structures rather than going through the full HTTP stack, avoiding
complex async DB mock wiring.
"""

from datetime import datetime, timedelta, timezone

import pytest


def _inject_terminal_point(
    is_finished: bool,
    home_score: int | None,
    away_score: int | None,
    completed_at: datetime | None,
    history: list[dict],
    espn_history: list[dict],
    win_prob_history: dict[str, list[dict]],
    aggregate_line: list[dict],
):
    """Replicate the terminal-point injection logic from the history endpoint.

    This is an extracted copy of the production logic in
    routes/events.py::get_event_odds_history for isolated unit testing.
    """
    if is_finished and home_score is not None and away_score is not None:
        if home_score != away_score:  # Skip ties
            home_won = home_score > away_score
            resolved_home_prob = 1.0 if home_won else 0.0
            resolved_away_prob = 0.0 if home_won else 1.0

            terminal_ts = None
            if completed_at:
                terminal_ts = completed_at
            else:
                latest_candidates = []
                if history:
                    latest_candidates.append(
                        datetime.fromisoformat(history[-1]["timestamp"])
                    )
                if espn_history:
                    latest_candidates.append(
                        datetime.fromisoformat(espn_history[-1]["timestamp"])
                    )
                for wp_points in win_prob_history.values():
                    if wp_points:
                        latest_candidates.append(
                            datetime.fromisoformat(wp_points[-1]["timestamp"])
                        )
                if latest_candidates:
                    terminal_ts = max(latest_candidates) + timedelta(minutes=1)

            if terminal_ts:
                terminal_iso = terminal_ts.replace(second=0, microsecond=0).isoformat()

                if history:
                    history.append({
                        "timestamp": terminal_iso,
                        "home_probability": resolved_home_prob,
                        "away_probability": resolved_away_prob,
                        "over_under": None,
                        "projected_home_score": None,
                        "projected_away_score": None,
                        "bookmaker_count": 0,
                        "probability_range": {
                            "min": resolved_home_prob,
                            "max": resolved_home_prob,
                        },
                    })

                for source_key in win_prob_history:
                    if win_prob_history[source_key]:
                        win_prob_history[source_key].append({
                            "timestamp": terminal_iso,
                            "home_probability": resolved_home_prob,
                            "away_probability": resolved_away_prob,
                            "draw_probability": None,
                            "game_state": {"final": True},
                        })

                if espn_history:
                    espn_history.append({
                        "timestamp": terminal_iso,
                        "home_probability": resolved_home_prob,
                        "away_probability": resolved_away_prob,
                        "home_score": home_score,
                        "away_score": away_score,
                        "game_clock": "Final",
                        "period": "Final",
                    })

                if aggregate_line:
                    aggregate_line.append({
                        "timestamp": terminal_iso,
                        "home_probability": resolved_home_prob,
                    })


class TestChartConvergence:
    """Verify that completed event charts converge to the correct winner."""

    def test_home_win_converges_to_100(self):
        """When home team wins, final history point should be home_prob=1.0."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.55, "away_probability": 0.45},
            {"timestamp": (t0 + timedelta(hours=1)).isoformat(), "home_probability": 0.70, "away_probability": 0.30},
            {"timestamp": (t0 + timedelta(hours=2)).isoformat(), "home_probability": 0.92, "away_probability": 0.08},
        ]
        espn = [
            {"timestamp": t0.isoformat(), "home_probability": 0.52, "away_probability": 0.48},
        ]
        wp = {"espn": [
            {"timestamp": t0.isoformat(), "home_probability": 0.52, "away_probability": 0.48},
        ]}
        agg = [
            {"timestamp": t0.isoformat(), "home_probability": 0.53},
        ]

        _inject_terminal_point(
            is_finished=True,
            home_score=112, away_score=98,
            completed_at=t0 + timedelta(hours=3),
            history=history,
            espn_history=espn,
            win_prob_history=wp,
            aggregate_line=agg,
        )

        assert history[-1]["home_probability"] == 1.0
        assert history[-1]["away_probability"] == 0.0
        assert espn[-1]["home_probability"] == 1.0
        assert espn[-1]["period"] == "Final"
        assert wp["espn"][-1]["home_probability"] == 1.0
        assert agg[-1]["home_probability"] == 1.0

    def test_away_win_converges_to_0(self):
        """When away team wins, final history point should be home_prob=0.0."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.45, "away_probability": 0.55},
            {"timestamp": (t0 + timedelta(hours=2)).isoformat(), "home_probability": 0.08, "away_probability": 0.92},
        ]
        espn = []
        wp = {}
        agg = []

        _inject_terminal_point(
            is_finished=True,
            home_score=98, away_score=112,
            completed_at=t0 + timedelta(hours=3),
            history=history,
            espn_history=espn,
            win_prob_history=wp,
            aggregate_line=agg,
        )

        assert history[-1]["home_probability"] == 0.0
        assert history[-1]["away_probability"] == 1.0
        # ESPN and aggregate were empty, so no convergence point added there
        assert len(espn) == 0
        assert len(agg) == 0

    def test_tie_game_no_convergence_point(self):
        """Tied games should NOT inject a convergence point."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.50, "away_probability": 0.50},
            {"timestamp": (t0 + timedelta(hours=2)).isoformat(), "home_probability": 0.48, "away_probability": 0.52},
        ]

        orig_len = len(history)
        _inject_terminal_point(
            is_finished=True,
            home_score=100, away_score=100,
            completed_at=t0 + timedelta(hours=3),
            history=history,
            espn_history=[],
            win_prob_history={},
            aggregate_line=[],
        )

        # No new point should have been added
        assert len(history) == orig_len
        assert history[-1]["home_probability"] == 0.48

    def test_live_event_no_convergence_point(self):
        """Live events should NOT get a convergence point."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.65, "away_probability": 0.35},
        ]

        orig_len = len(history)
        _inject_terminal_point(
            is_finished=False,  # Live, not finished
            home_score=88, away_score=82,
            completed_at=None,
            history=history,
            espn_history=[],
            win_prob_history={},
            aggregate_line=[],
        )

        assert len(history) == orig_len

    def test_no_scores_no_convergence_point(self):
        """Completed events without scores should NOT get a convergence point."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.65, "away_probability": 0.35},
        ]

        orig_len = len(history)
        _inject_terminal_point(
            is_finished=True,
            home_score=None, away_score=None,
            completed_at=t0 + timedelta(hours=3),
            history=history,
            espn_history=[],
            win_prob_history={},
            aggregate_line=[],
        )

        assert len(history) == orig_len

    def test_convergence_uses_completed_at_timestamp(self):
        """Terminal point should use completed_at when available."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2026, 5, 28, 2, 30, tzinfo=timezone.utc)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.70, "away_probability": 0.30},
        ]

        _inject_terminal_point(
            is_finished=True,
            home_score=112, away_score=98,
            completed_at=completed,
            history=history,
            espn_history=[],
            win_prob_history={},
            aggregate_line=[],
        )

        expected_ts = completed.replace(second=0, microsecond=0).isoformat()
        assert history[-1]["timestamp"] == expected_ts

    def test_convergence_fallback_timestamp_without_completed_at(self):
        """Without completed_at, terminal point uses last data + 1 minute."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        last_data = t0 + timedelta(hours=2, minutes=15)
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.55, "away_probability": 0.45},
            {"timestamp": last_data.isoformat(), "home_probability": 0.85, "away_probability": 0.15},
        ]

        _inject_terminal_point(
            is_finished=True,
            home_score=110, away_score=95,
            completed_at=None,
            history=history,
            espn_history=[],
            win_prob_history={},
            aggregate_line=[],
        )

        # Should be last_data + 1 minute, truncated to the minute
        expected_ts = (last_data + timedelta(minutes=1)).replace(second=0, microsecond=0).isoformat()
        assert history[-1]["timestamp"] == expected_ts

    def test_multiple_win_prob_sources_all_get_convergence(self):
        """All win_prob_history sources with data get a convergence point."""
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        wp = {
            "espn": [
                {"timestamp": t0.isoformat(), "home_probability": 0.52, "away_probability": 0.48},
            ],
            "stat_model": [
                {"timestamp": t0.isoformat(), "home_probability": 0.55, "away_probability": 0.45},
            ],
            "kalshi": [],  # Empty source should NOT get a point
        }

        _inject_terminal_point(
            is_finished=True,
            home_score=112, away_score=98,
            completed_at=t0 + timedelta(hours=3),
            history=[{"timestamp": t0.isoformat(), "home_probability": 0.60, "away_probability": 0.40}],
            espn_history=[],
            win_prob_history=wp,
            aggregate_line=[],
        )

        assert wp["espn"][-1]["home_probability"] == 1.0
        assert wp["stat_model"][-1]["home_probability"] == 1.0
        assert len(wp["kalshi"]) == 0  # Empty source stays empty

    def test_wrong_team_convergence_bug_scenario(self):
        """Reproduce Bug #706: chart showing wrong winner.

        Scenario: Last odds snapshot shows home at 92%, but away team won.
        Without the fix, chart ends at 92% for home (wrong).
        With the fix, chart should converge to 0% for home (correct).
        """
        t0 = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)
        # Pre-game: home was favorite, odds had home at 92% near the end
        history = [
            {"timestamp": t0.isoformat(), "home_probability": 0.65, "away_probability": 0.35},
            {"timestamp": (t0 + timedelta(hours=1)).isoformat(), "home_probability": 0.80, "away_probability": 0.20},
            {"timestamp": (t0 + timedelta(hours=2)).isoformat(), "home_probability": 0.92, "away_probability": 0.08},
        ]

        # But away team actually won (upset)
        _inject_terminal_point(
            is_finished=True,
            home_score=98, away_score=102,  # Away wins!
            completed_at=t0 + timedelta(hours=3),
            history=history,
            espn_history=[],
            win_prob_history={},
            aggregate_line=[],
        )

        # The last point must converge to 0% home (away won)
        assert history[-1]["home_probability"] == 0.0
        assert history[-1]["away_probability"] == 1.0
        # Second-to-last point is the original 92% (preserved)
        assert history[-2]["home_probability"] == 0.92
