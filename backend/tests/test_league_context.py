"""Tests for league context service and league_configs lookups."""

import json
import pytest
from app.config.league_configs import (
    get_league_config,
    get_league_for_sport_key,
    SPORT_GROUPS,
    LEAGUE_TO_SPORT,
    LEAGUE_CONFIGS,
)
from app.services.league_context import (
    TeamLeagueContext,
    LeagueContext,
)
from app.routes.playoffs import _volume_confidence


class TestLeagueConfigLookups:
    """Tests for league_configs.py sport/league resolution."""

    def test_sport_key_to_league_nba(self):
        config = get_league_for_sport_key("basketball_nba")
        assert config is not None
        assert config.slug == "nba"

    def test_sport_key_to_league_nfl(self):
        config = get_league_for_sport_key("americanfootball_nfl")
        assert config is not None
        assert config.slug == "nfl"

    def test_sport_key_to_league_nhl(self):
        config = get_league_for_sport_key("icehockey_nhl")
        assert config is not None
        assert config.slug == "nhl"

    def test_sport_key_to_league_golf(self):
        config = get_league_for_sport_key("golf_pga")
        assert config is not None
        assert config.slug == "golf"

    def test_sport_key_to_league_epl(self):
        config = get_league_for_sport_key("soccer_epl")
        assert config is not None
        assert config.slug == "epl"

    def test_sport_key_to_league_unknown(self):
        config = get_league_for_sport_key("cricket_test")
        assert config is None

    def test_sport_groups_cover_all_leagues(self):
        """Every configured league should appear in exactly one sport group."""
        all_grouped = set()
        for leagues in SPORT_GROUPS.values():
            all_grouped.update(leagues)
        for slug in LEAGUE_CONFIGS:
            assert slug in all_grouped, f"League {slug} not in any SPORT_GROUP"

    def test_league_to_sport_reverse_lookup(self):
        assert LEAGUE_TO_SPORT["nba"] == "basketball"
        assert LEAGUE_TO_SPORT["nfl"] == "football"
        assert LEAGUE_TO_SPORT["epl"] == "soccer"
        assert LEAGUE_TO_SPORT["golf"] == "golf"

    def test_all_league_configs_have_columns(self):
        """Every league config should have at least 2 columns."""
        for slug, config in LEAGUE_CONFIGS.items():
            assert len(config.columns) >= 2, f"League {slug} has < 2 columns"

    def test_all_league_configs_have_matching_rules(self):
        """Every league config should have at least 1 matching rule."""
        for slug, config in LEAGUE_CONFIGS.items():
            assert len(config.matching_rules) >= 1, f"League {slug} has no matching rules"


class TestLeagueContextDataModel:
    """Tests for TeamLeagueContext and LeagueContext serialization."""

    def test_team_context_basic(self):
        ctx = TeamLeagueContext(
            team_name="Boston Celtics",
            league_slug="nba",
            cells={"make_playoffs": 0.95, "conference": 0.35, "championship": 0.18},
            changes_24h={"championship": 0.02},
            column_labels={"make_playoffs": "Playoffs", "conference": "Conference", "championship": "Champion"},
        )
        assert ctx.cells["championship"] == 0.18
        assert ctx.changes_24h["championship"] == 0.02

    def test_league_context_serialization_roundtrip(self):
        ctx = LeagueContext(
            league_slug="nba",
            league_name="NBA 2025-26",
            sport_group="basketball",
            teams={
                "boston celtics": TeamLeagueContext(
                    team_name="Boston Celtics",
                    league_slug="nba",
                    cells={"championship": 0.18},
                    column_labels={"championship": "Champion"},
                ),
            },
            columns=[{"key": "championship", "label": "Champion"}],
            last_computed="2026-04-15T00:00:00+00:00",
        )
        json_str = ctx.to_json()
        restored = LeagueContext.from_json(json_str)
        assert restored.league_slug == "nba"
        assert "boston celtics" in restored.teams
        assert restored.teams["boston celtics"].cells["championship"] == 0.18

    def test_league_context_empty_roundtrip(self):
        ctx = LeagueContext(league_slug="test")
        restored = LeagueContext.from_json(ctx.to_json())
        assert restored.league_slug == "test"
        assert len(restored.teams) == 0


class TestVolumeConfidence:
    """Tests for volume confidence weighting in grid merging."""

    def test_no_volume(self):
        assert _volume_confidence(None) == 0.5

    def test_zero_volume(self):
        assert _volume_confidence(0) == 0.5

    def test_low_volume(self):
        assert _volume_confidence(500) == 0.3

    def test_moderate_volume(self):
        assert _volume_confidence(5000) == 0.6

    def test_high_volume(self):
        assert _volume_confidence(100000) == 1.0
