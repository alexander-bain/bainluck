"""Tests for scoring play extraction from StatPal play-by-play data.

Covers:
- extract_scoring_plays: filtering to scoring types, requiring captured_at,
  handling empty/missing data, type string matching
"""

import pytest

from app.routes.events import _assign_wall_clock_timestamps, extract_scoring_plays


class TestExtractScoringPlays:
    """Tests for extract_scoring_plays utility."""

    def test_touchdown_extracted(self):
        """Touchdown plays should be included."""
        plays = [
            {
                "type": "touchdown",
                "description": "Brady 24-yd TD pass to Evans",
                "team": "Buccaneers",
                "captured_at": "2026-02-25T20:34:00+00:00",
                "home_score": 21,
                "away_score": 14,
                "period": "Q3",
                "clock": "4:22",
            }
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 1
        assert result[0]["description"] == "Brady 24-yd TD pass to Evans"
        assert result[0]["team"] == "Buccaneers"
        assert result[0]["home_score"] == 21

    def test_non_scoring_plays_excluded(self):
        """Non-scoring plays like penalties should be excluded."""
        plays = [
            {
                "type": "penalty",
                "description": "Holding on offense",
                "team": "Cowboys",
                "captured_at": "2026-02-25T20:35:00+00:00",
                "home_score": 21,
                "away_score": 14,
            },
            {
                "type": "punt",
                "description": "Punt for 45 yards",
                "team": "Cowboys",
                "captured_at": "2026-02-25T20:36:00+00:00",
                "home_score": 21,
                "away_score": 14,
            },
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 0

    def test_plays_without_captured_at_excluded(self):
        """Plays missing captured_at cannot be placed on chart, so excluded."""
        plays = [
            {
                "type": "goal",
                "description": "Messi scores",
                "team": "Inter Miami",
                "home_score": 1,
                "away_score": 0,
            }
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 0

    def test_empty_plays_list(self):
        """Empty input should return empty output."""
        assert extract_scoring_plays([]) == []

    def test_multiple_scoring_types(self):
        """Various scoring types across sports should all be extracted."""
        plays = [
            {"type": "field_goal", "captured_at": "2026-02-25T20:00:00+00:00", "description": "42-yd FG"},
            {"type": "three_pointer", "captured_at": "2026-02-25T20:05:00+00:00", "description": "Curry 3PT"},
            {"type": "home_run", "captured_at": "2026-02-25T20:10:00+00:00", "description": "Judge HR"},
            {"type": "power_play_goal", "captured_at": "2026-02-25T20:15:00+00:00", "description": "PPG"},
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 4

    def test_type_substring_matching(self):
        """Types containing 'goal' or 'score' should match even if not exact."""
        plays = [
            {"type": "penalty_goal_scored", "captured_at": "2026-02-25T20:00:00+00:00", "description": "PK"},
            {"type": "score_update", "captured_at": "2026-02-25T20:05:00+00:00", "description": "Score change"},
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 2

    def test_case_insensitive_type(self):
        """Type matching should be case-insensitive."""
        plays = [
            {"type": "Touchdown", "captured_at": "2026-02-25T20:00:00+00:00", "description": "TD"},
            {"type": "GOAL", "captured_at": "2026-02-25T20:05:00+00:00", "description": "Goal"},
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 2

    def test_none_type_excluded(self):
        """Plays with None type should be excluded."""
        plays = [
            {"type": None, "captured_at": "2026-02-25T20:00:00+00:00", "description": "Unknown"},
        ]
        result = extract_scoring_plays(plays)
        assert len(result) == 0


class TestAssignWallClockTimestamps:
    """Tests for mapping ESPN score states to chart timestamps."""

    def test_preserves_order_and_duplicate_score_state(self):
        """Duplicate score states should keep both plays in source order."""
        espn_plays = [
            {
                "description": "Made free throw",
                "type": "Free Throw",
                "home_score": "10",
                "away_score": "8",
                "period": 1,
                "clock": "3:14",
            },
            {
                "description": "Technical free throw",
                "type": "Free Throw",
                "home_score": "10",
                "away_score": "8",
                "period": 1,
                "clock": "3:14",
            },
        ]
        espn_history = [
            {
                "timestamp": "2026-02-25T20:10:00+00:00",
                "home_score": 10,
                "away_score": 8,
            },
            {
                "timestamp": "2026-02-25T20:11:00+00:00",
                "home_score": 10,
                "away_score": 8,
            },
        ]

        result = _assign_wall_clock_timestamps(espn_plays, espn_history)

        assert [play["description"] for play in result] == [
            "Made free throw",
            "Technical free throw",
        ]
        assert [play["timestamp"] for play in result] == [
            "2026-02-25T20:10:00+00:00",
            "2026-02-25T20:10:00+00:00",
        ]
        assert [play["period"] for play in result] == ["1", "1"]
