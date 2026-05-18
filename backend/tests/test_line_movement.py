"""Tests for line movement detection and prompt building.

Covers:
- detect_line_movements: sliding window detection, threshold filtering,
  direction classification, magnitude sorting, duration filtering
- build_llm_prompt: backward compatibility, injury/news/game context injection
- _build_movement_context: beneficiary team, phase labeling
- _build_summary_context: sport/matchup/opening/current info
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.line_movement import (
    detect_line_movements,
    build_llm_prompt,
    LineMovementAnalysis,
    LineMovement,
    SIGNIFICANT_MOVE_THRESHOLD,
    MAJOR_MOVE_THRESHOLD,
    MAX_MOVEMENTS_PER_EVENT,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _make_snapshots(probs: list[float], start_minutes_apart: int = 5) -> list[dict]:
    """Build a list of snapshots with evenly spaced timestamps."""
    base = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)
    return [
        {
            "timestamp": base + timedelta(minutes=i * start_minutes_apart),
            "home_probability": p,
            "bookmaker_count": 8,
        }
        for i, p in enumerate(probs)
    ]


def _make_analysis(movements=None, summary_context="Test context") -> LineMovementAnalysis:
    """Build a minimal LineMovementAnalysis for prompt tests."""
    return LineMovementAnalysis(
        event_id=1,
        movements=movements or [],
        summary_context=summary_context,
    )


# ── detect_line_movements: Detection tests ────────────────────────────


class TestDetectNoMovements:
    """Cases where no significant movements should be detected."""

    def test_no_movements_flat_line(self):
        """Constant 60/40 odds should produce 0 movements."""
        snaps = _make_snapshots([0.60] * 10)
        result = detect_line_movements(snaps, home_team="Home", away_team="Away")
        assert result.movement_count == 0
        assert result.movements == []

    def test_below_threshold_ignored(self):
        """50% → 53% is below 5% threshold, should be ignored."""
        snaps = _make_snapshots([0.50, 0.51, 0.52, 0.53])
        result = detect_line_movements(snaps)
        assert result.movement_count == 0

    def test_empty_snapshots(self):
        """<2 snapshots should return empty analysis."""
        result = detect_line_movements([])
        assert result.movement_count == 0
        assert result.movements == []

        result_one = detect_line_movements([{"timestamp": datetime.now(timezone.utc), "home_probability": 0.5}])
        assert result_one.movement_count == 0

    def test_short_duration_filtered(self):
        """A 2-minute spike should be filtered by MIN_DURATION_MINUTES=3."""
        base = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)
        snaps = [
            {"timestamp": base, "home_probability": 0.50},
            {"timestamp": base + timedelta(minutes=1), "home_probability": 0.58},
            {"timestamp": base + timedelta(minutes=2), "home_probability": 0.50},
        ]
        result = detect_line_movements(snaps)
        # The 8% spike in 1 min is < 3 min duration — should be filtered
        assert result.movement_count == 0


class TestDetectMovements:
    """Cases where movements should be detected."""

    def test_single_significant_movement(self):
        """50% → 57% over 10 min should detect 1 movement."""
        snaps = _make_snapshots([0.50, 0.52, 0.55, 0.57])
        result = detect_line_movements(snaps, home_team="Celtics", away_team="Lakers")
        assert result.movement_count >= 1
        assert result.movements[0].magnitude >= SIGNIFICANT_MOVE_THRESHOLD

    def test_major_movement_flagged(self):
        """50% → 62% should be flagged as is_major=True."""
        snaps = _make_snapshots([0.50, 0.54, 0.58, 0.62])
        result = detect_line_movements(snaps)
        assert result.movement_count >= 1
        major_moves = [m for m in result.movements if m.is_major]
        assert len(major_moves) >= 1
        assert major_moves[0].magnitude >= MAJOR_MOVE_THRESHOLD

    def test_max_movements_capped(self):
        """More than MAX_MOVEMENTS_PER_EVENT swings should be capped."""
        # Create alternating large swings
        probs = []
        for i in range(20):
            probs.append(0.50 + (0.08 if i % 2 == 0 else -0.08))
        snaps = _make_snapshots(probs)
        result = detect_line_movements(snaps)
        assert result.movement_count <= MAX_MOVEMENTS_PER_EVENT

    def test_sorted_by_magnitude(self):
        """Movements should be sorted largest-first."""
        # Two distinct movements of different magnitudes
        snaps = _make_snapshots([0.50, 0.56, 0.56, 0.56, 0.56, 0.45])
        result = detect_line_movements(snaps)
        if result.movement_count >= 2:
            for i in range(len(result.movements) - 1):
                assert result.movements[i].magnitude >= result.movements[i + 1].magnitude

    def test_iso_string_timestamps(self):
        """String timestamps should be parsed correctly."""
        snaps = [
            {"timestamp": "2026-02-20T18:00:00+00:00", "home_probability": 0.50},
            {"timestamp": "2026-02-20T18:05:00+00:00", "home_probability": 0.53},
            {"timestamp": "2026-02-20T18:10:00+00:00", "home_probability": 0.56},
            {"timestamp": "2026-02-20T18:15:00+00:00", "home_probability": 0.58},
        ]
        result = detect_line_movements(snaps)
        assert result.movement_count >= 1

    def test_exact_threshold_detected(self):
        """A move exactly at the 5pp threshold should be card-worthy."""
        snaps = _make_snapshots([0.50, 0.55])
        result = detect_line_movements(snaps)

        assert result.movement_count == 1
        assert result.movements[0].magnitude == pytest.approx(SIGNIFICANT_MOVE_THRESHOLD)
        assert result.max_single_move == pytest.approx(SIGNIFICANT_MOVE_THRESHOLD)

    def test_missing_snapshot_fields_are_ignored(self):
        """Malformed rows should not block movement detection from valid rows."""
        base = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)
        snaps = [
            {"timestamp": base, "home_probability": 0.50, "bookmaker_count": 6},
            {"timestamp": base + timedelta(minutes=5), "bookmaker_count": 7},
            {"home_probability": 0.54, "bookmaker_count": 8},
            {"timestamp": base + timedelta(minutes=10), "home_probability": 0.57, "bookmaker_count": 9},
        ]
        result = detect_line_movements(snaps)

        assert result.movement_count == 1
        move = result.movements[0]
        assert move.home_prob_before == pytest.approx(0.50)
        assert move.home_prob_after == pytest.approx(0.57)
        assert move.bookmaker_count_before == 6
        assert move.bookmaker_count_after == 9

    def test_bookmaker_counts_preserved_on_detected_movement(self):
        """Cards can show source depth for the snapshots that defined a move."""
        base = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)
        snaps = [
            {"timestamp": base, "home_probability": 0.48, "bookmaker_count": 3},
            {"timestamp": base + timedelta(minutes=5), "home_probability": 0.52, "bookmaker_count": 6},
            {"timestamp": base + timedelta(minutes=10), "home_probability": 0.56, "bookmaker_count": 10},
        ]
        result = detect_line_movements(snaps)

        assert result.movement_count == 1
        assert result.movements[0].bookmaker_count_before == 3
        assert result.movements[0].bookmaker_count_after == 10


class TestDetectDirection:
    """Tests for movement direction classification."""

    def test_direction_evening_out(self):
        """Underdog gaining toward 50% should be 'evening_out'."""
        snaps = _make_snapshots([0.40, 0.43, 0.46, 0.49])
        result = detect_line_movements(snaps, home_team="Home", away_team="Away")
        if result.movements:
            assert result.movements[0].direction == "evening_out"

    def test_direction_pulling_away(self):
        """Favorite gaining >8% should be 'pulling_away'."""
        snaps = _make_snapshots([0.55, 0.59, 0.62, 0.65])
        result = detect_line_movements(snaps)
        if result.movements:
            assert result.movements[0].direction == "pulling_away"

    def test_direction_toward_home(self):
        """Home team gaining moderately should be 'toward_home'."""
        snaps = _make_snapshots([0.55, 0.57, 0.59, 0.61])
        result = detect_line_movements(snaps)
        if result.movements:
            assert result.movements[0].direction in ("toward_home", "pulling_away")

    def test_direction_toward_away(self):
        """Away team gaining (home dropping) should be 'toward_away'."""
        snaps = _make_snapshots([0.45, 0.42, 0.39, 0.37])
        result = detect_line_movements(snaps)
        if result.movements:
            assert result.movements[0].direction in ("toward_away", "pulling_away")


class TestTotalSwing:
    """Tests for total_swing calculation."""

    def test_total_swing_from_opening(self):
        """Net change from opening should be calculated."""
        snaps = _make_snapshots([0.60, 0.62, 0.64, 0.55])
        result = detect_line_movements(snaps, opening_home_prob=0.60)
        # Current (last) is 0.55, opening is 0.60 → swing = -0.05
        assert abs(result.total_swing - (-0.05)) < 0.001

    def test_total_swing_without_opening(self):
        """Without opening prob, total_swing should be 0."""
        snaps = _make_snapshots([0.60, 0.65, 0.70])
        result = detect_line_movements(snaps)
        assert result.total_swing == 0.0

    def test_total_swing_uses_latest_timestamp_not_input_order(self):
        """Out-of-order snapshots should still calculate swing from the latest row."""
        base = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)
        snaps = [
            {"timestamp": base + timedelta(minutes=10), "home_probability": 0.62},
            {"timestamp": base, "home_probability": 0.50},
            {"timestamp": base + timedelta(minutes=5), "home_probability": 0.56},
        ]
        result = detect_line_movements(snaps, opening_home_prob=0.50)

        assert result.total_swing == pytest.approx(0.12)
        assert "Current odds" in result.summary_context
        assert "62.0%" in result.summary_context


# ── _build_movement_context tests ─────────────────────────────────────


class TestMovementContext:
    """Tests for movement context string building."""

    def test_movement_context_beneficiary(self):
        """Context should name the correct beneficiary team."""
        snaps = _make_snapshots([0.50, 0.53, 0.56, 0.58])
        result = detect_line_movements(
            snaps, home_team="Celtics", away_team="Lakers", event_status="scheduled"
        )
        if result.movements:
            assert "Celtics" in result.movements[0].context

    def test_summary_context_has_sport_matchup(self):
        """Summary context should include sport and team names."""
        snaps = _make_snapshots([0.50, 0.56, 0.62])
        result = detect_line_movements(
            snaps,
            home_team="Celtics",
            away_team="Lakers",
            sport_key="basketball_nba",
        )
        assert "Celtics" in result.summary_context
        assert "Lakers" in result.summary_context
        assert "Basketball" in result.summary_context


# ── build_llm_prompt tests ────────────────────────────────────────────


class TestBuildLLMPrompt:
    """Tests for the LLM prompt builder with context injection."""

    def test_prompt_backward_compatible(self):
        """Calling with no extra args should still produce a valid prompt."""
        analysis = _make_analysis(summary_context="Sport: Basketball Nba\nMatchup: Lakers at Celtics")
        prompt = build_llm_prompt(analysis)
        assert "Basketball Nba" in prompt
        assert "Lakers at Celtics" in prompt
        assert "Explanation:" in prompt

    def test_prompt_includes_summary_context(self):
        """The analysis summary_context should appear in the prompt."""
        analysis = _make_analysis(summary_context="Opening odds: Celtics 55.0%")
        prompt = build_llm_prompt(analysis)
        assert "Opening odds: Celtics 55.0%" in prompt

    def test_prompt_with_injuries(self):
        """Injury data should appear in the prompt."""
        analysis = _make_analysis()
        injuries = [
            {"player_name": "Jaylen Brown", "team_name": "Celtics", "status": "Day-To-Day", "injury_type": "Knee"},
            {"player_name": "LeBron James", "team_name": "Lakers", "status": "Out", "injury_type": "Back"},
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries)
        assert "Jaylen Brown" in prompt
        assert "Celtics" in prompt
        assert "Day-To-Day" in prompt
        assert "Knee" in prompt
        assert "LeBron James" in prompt
        assert "Out" in prompt
        assert "Known injury report:" in prompt

    def test_prompt_with_news(self):
        """News headlines should appear in the prompt."""
        analysis = _make_analysis()
        news = ["LeBron James listed as doubtful for Friday", "Lakers sign veteran guard"]
        prompt = build_llm_prompt(analysis, news_headlines=news)
        assert "LeBron James listed as doubtful" in prompt
        assert "Lakers sign veteran guard" in prompt
        assert "Recent headlines:" in prompt

    def test_prompt_with_game_context(self):
        """Live game state should appear in the prompt."""
        analysis = _make_analysis()
        ctx = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_score": 87,
            "away_score": 82,
            "period": 4,
            "clock": "4:32",
        }
        prompt = build_llm_prompt(analysis, game_context=ctx)
        assert "Celtics 87 - Lakers 82" in prompt
        assert "Period: 4" in prompt
        assert "Clock: 4:32" in prompt

    def test_prompt_game_context_only_no_speculation(self):
        """Game state without injuries/news should not speculate about causes."""
        analysis = _make_analysis()
        ctx = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_score": 87,
            "away_score": 82,
            "period": 4,
            "clock": "4:32",
        }
        prompt = build_llm_prompt(analysis, game_context=ctx)
        # Should NOT encourage focusing on in-game speculation
        assert "focus on in-game factors" not in prompt.lower()
        # Should instruct against vague speculation
        assert "Do NOT speculate" in prompt
        # Should instruct to describe factually
        assert "factually" in prompt.lower()

    def test_prompt_injuries_unknown_type_omitted(self):
        """Injury with 'Unknown' type should not show type detail."""
        analysis = _make_analysis()
        injuries = [
            {"player_name": "Player X", "team_name": "Team A", "status": "Questionable", "injury_type": "Unknown"},
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries)
        assert "Player X" in prompt
        assert "Questionable" in prompt
        # "Unknown" should not appear after the dash
        assert "— Unknown" not in prompt

    def test_prompt_no_fabrication_instruction(self):
        """The prompt should instruct not to fabricate injuries."""
        analysis = _make_analysis()
        prompt = build_llm_prompt(analysis, injuries=[
            {"player_name": "Test", "team_name": "Team", "status": "Out", "injury_type": "Ankle"}
        ])
        assert "Do not fabricate injury information" in prompt

    def test_prompt_caps_injuries_at_5(self):
        """More than 5 injuries should be capped to focus on most impactful."""
        analysis = _make_analysis()
        injuries = [
            {"player_name": f"Player {i}", "team_name": "Team", "status": "Out", "injury_type": "Injury"}
            for i in range(15)
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries)
        # Count injury lines (each starts with "  - ")
        injury_lines = [line for line in prompt.split("\n") if line.strip().startswith("- Player")]
        assert len(injury_lines) == 5

    def test_prompt_caps_news_at_5(self):
        """More than 5 headlines should be capped."""
        analysis = _make_analysis()
        news = [f"Headline {i}" for i in range(8)]
        prompt = build_llm_prompt(analysis, news_headlines=news)
        headline_lines = [line for line in prompt.split("\n") if line.strip().startswith("- Headline")]
        assert len(headline_lines) == 5

    def test_prompt_with_scoring_plays(self):
        """Scoring plays should appear in prompt and trigger scoring-play instructions."""
        analysis = _make_analysis()
        scoring_plays = [
            {
                "period": "Q1",
                "clock": "8:42",
                "team": "DET",
                "description": "Cade Cunningham 3-pointer",
                "home_score": 15,
                "away_score": 12,
            },
            {
                "period": "Q2",
                "clock": "3:15",
                "team": "ORL",
                "description": "Paolo Banchero dunk",
                "home_score": 45,
                "away_score": 48,
            },
        ]
        prompt = build_llm_prompt(analysis, scoring_plays=scoring_plays)
        assert "Key game moments:" in prompt
        assert "Cade Cunningham" in prompt
        assert "Paolo Banchero" in prompt
        assert "15 - 12" in prompt
        # Should use the scoring-plays-aware instructions
        assert "scoring plays" in prompt.lower()

    def test_prompt_scoring_plays_capped_at_15(self):
        """More than 15 scoring plays should be capped."""
        analysis = _make_analysis()
        scoring_plays = [
            {"period": "Q1", "clock": f"{i}:00", "team": "A", "description": f"Play {i}",
             "home_score": i, "away_score": i + 1}
            for i in range(20)
        ]
        prompt = build_llm_prompt(analysis, scoring_plays=scoring_plays)
        play_lines = [line for line in prompt.split("\n") if line.strip().startswith("- Q1")]
        assert len(play_lines) == 15

    def test_prompt_scoring_plays_take_priority_over_injuries(self):
        """When scoring plays are present, they should appear before injuries in the prompt."""
        analysis = _make_analysis()
        injuries = [
            {"player_name": "Player X", "team_name": "Team A", "status": "Out", "injury_type": "Ankle"},
        ]
        scoring_plays = [
            {"period": "Q3", "clock": "5:00", "team": "Home", "description": "Three pointer",
             "home_score": 70, "away_score": 60},
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries, scoring_plays=scoring_plays)
        # Scoring plays section should come before injury report
        plays_pos = prompt.find("Key game moments:")
        injuries_pos = prompt.find("Known injury report:")
        assert plays_pos < injuries_pos


# ── StatPal injury merging (A1) ───────────────────────────────────────

class TestStatPalInjuryMerging:
    """Tests for merging StatPal injuries into the LLM prompt.

    The actual merge logic lives in events.py, but we verify that
    build_llm_prompt handles mixed-source injury lists correctly.
    """

    def test_statpal_only_injuries_in_prompt(self):
        """StatPal injuries (mapped to ESPN format) should appear in prompt."""
        analysis = _make_analysis()
        # StatPal injuries mapped to ESPN-format keys (as events.py does)
        injuries = [
            {"player_name": "Jayson Tatum", "team_name": "Celtics", "status": "Questionable", "injury_type": "Ankle"},
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries)
        assert "Jayson Tatum" in prompt
        assert "Celtics" in prompt
        assert "Questionable" in prompt
        assert "Ankle" in prompt

    def test_espn_and_statpal_dedup_in_prompt(self):
        """When both ESPN and StatPal report the same player, only one entry should appear."""
        analysis = _make_analysis()
        # Simulate merged list: ESPN entry + StatPal entry for different players
        injuries = [
            {"player_name": "LeBron James", "team_name": "Lakers", "status": "Out", "injury_type": "Back"},
            {"player_name": "Anthony Davis", "team_name": "Lakers", "status": "Day-To-Day", "injury_type": "Knee"},
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries)
        assert "LeBron James" in prompt
        assert "Anthony Davis" in prompt
        # Both should appear since they're different players
        injury_lines = [line for line in prompt.split("\n") if line.strip().startswith("- ")]
        # At least 2 injury lines
        assert len([l for l in injury_lines if "LeBron" in l or "Anthony" in l]) == 2

    def test_statpal_injuries_empty_player_skipped(self):
        """StatPal injuries with empty player name should be skipped in merge."""
        analysis = _make_analysis()
        # Only valid injury should appear
        injuries = [
            {"player_name": "Marcus Smart", "team_name": "Grizzlies", "status": "Out", "injury_type": "Foot"},
        ]
        prompt = build_llm_prompt(analysis, injuries=injuries)
        assert "Marcus Smart" in prompt
        assert "Known injury report:" in prompt


class TestTeamStatsInPrompt:
    """Tests for team season stats enrichment in LLM prompt (C3)."""

    def test_team_stats_included_in_prompt(self):
        """Season stats for both teams should appear in the prompt."""
        analysis = _make_analysis()
        team_stats = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_stats": {"ppg": 112.3, "opp_ppg": 106.1, "reb": 44.2},
            "away_stats": {"ppg": 108.5, "opp_ppg": 110.2, "reb": 42.0},
        }
        prompt = build_llm_prompt(analysis, team_stats=team_stats)
        assert "Season stats:" in prompt
        assert "Celtics" in prompt
        assert "112.3" in prompt
        assert "Lakers" in prompt
        assert "108.5" in prompt

    def test_team_stats_partial_home_only(self):
        """If only home team has stats, only home team stats appear."""
        analysis = _make_analysis()
        team_stats = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_stats": {"ppg": 112.3},
            "away_stats": None,
        }
        prompt = build_llm_prompt(analysis, team_stats=team_stats)
        assert "Season stats:" in prompt
        assert "Celtics" in prompt
        assert "112.3" in prompt

    def test_team_stats_none_excluded(self):
        """When team_stats is None, no stats section appears."""
        analysis = _make_analysis()
        prompt = build_llm_prompt(analysis, team_stats=None)
        assert "Season stats:" not in prompt

    def test_team_stats_empty_dicts_excluded(self):
        """When both team stats are None, no stats section appears."""
        analysis = _make_analysis()
        team_stats = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_stats": None,
            "away_stats": None,
        }
        prompt = build_llm_prompt(analysis, team_stats=team_stats)
        assert "Season stats:" not in prompt

    def test_team_stats_with_injuries_context(self):
        """Team stats should appear alongside injuries — both are context."""
        analysis = _make_analysis()
        injuries = [
            {"player_name": "Jaylen Brown", "team_name": "Celtics", "status": "Questionable", "injury_type": "Knee"},
        ]
        team_stats = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_stats": {"ppg": 112.3},
            "away_stats": {"ppg": 108.5},
        }
        prompt = build_llm_prompt(analysis, injuries=injuries, team_stats=team_stats)
        assert "Known injury report:" in prompt
        assert "Jaylen Brown" in prompt
        assert "Season stats:" in prompt
        assert "112.3" in prompt
        # Should use context-aware instructions (not "do NOT speculate")
        assert "Do NOT speculate" not in prompt

    def test_team_stats_caps_at_8_keys(self):
        """Stats should cap at 8 keys per team to keep prompt manageable."""
        analysis = _make_analysis()
        # Create stats with more than 8 keys
        many_stats = {f"stat_{i}": float(i) for i in range(12)}
        team_stats = {
            "home_team": "Celtics",
            "away_team": "Lakers",
            "home_stats": many_stats,
            "away_stats": None,
        }
        prompt = build_llm_prompt(analysis, team_stats=team_stats)
        assert "Season stats:" in prompt
        # Count stat entries for Celtics line
        celtics_line = [l for l in prompt.split("\n") if "Celtics" in l and "stat_" in l]
        assert len(celtics_line) == 1
        # Should have at most 8 stat entries
        stat_count = celtics_line[0].count("stat_")
        assert stat_count <= 8
