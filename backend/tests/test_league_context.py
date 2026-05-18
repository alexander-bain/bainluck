"""Tests for league context service and league_configs lookups."""

import json
from types import SimpleNamespace

import pytest
from app.config.league_configs import (
    get_league_config,
    get_league_for_sport_key,
    SPORT_GROUPS,
    LEAGUE_TO_SPORT,
    LEAGUE_CONFIGS,
)
from app.services import league_context as league_context_service
from app.services.league_context import (
    TeamLeagueContext,
    LeagueContext,
    _compute_league_context,
    enrich_event_with_context,
    get_team_context,
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

    def test_all_league_configs_have_user_facing_labels(self):
        """League and column labels feed detail pages and must be presentable."""
        for slug, config in LEAGUE_CONFIGS.items():
            assert config.name.strip(), f"League {slug} has blank display name"
            assert config.sport_category.strip(), f"League {slug} has blank sport category"
            assert slug in LEAGUE_TO_SPORT, f"League {slug} has no sport group"

            column_keys = [column.key for column in config.columns]
            assert len(column_keys) == len(set(column_keys)), f"League {slug} has duplicate column keys"
            for column in config.columns:
                assert column.key.strip(), f"League {slug} has blank column key"
                assert column.label.strip(), f"League {slug} column {column.key} has blank label"

    def test_sport_key_mapping_stays_in_league_scope(self):
        """Sport keys should resolve to their owning league, not just sport group."""
        scoped_examples = {
            "basketball_nba": ("nba", "basketball"),
            "basketball_ncaab": ("ncaa-basketball", "basketball"),
            "soccer_epl": ("epl", "soccer"),
            "soccer_usa_mls": ("mls", "soccer"),
        }

        for sport_key, (expected_slug, expected_group) in scoped_examples.items():
            config = get_league_for_sport_key(sport_key)
            assert config is not None
            assert config.slug == expected_slug
            assert LEAGUE_TO_SPORT[config.slug] == expected_group


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


class TestLeagueContextService:
    """Tests for computed and event-facing league context behavior."""

    @pytest.mark.asyncio
    async def test_compute_league_context_from_grouped_teams_with_missing_rows_skipped(
        self,
        monkeypatch,
    ):
        async def fake_grid(**kwargs):
            assert kwargs["league_slug"] == "nba"
            return {
                "grouped_teams": {
                    "Eastern": [
                        {
                            "name": "Boston Celtics",
                            "team_id": 1,
                            "conference": "Eastern",
                            "record": "64-18",
                            "stages": [
                                {
                                    "key": "make_playoffs",
                                    "probability": 0.98,
                                    "trend_24h": 0.01,
                                    "sources": [{"source": "kalshi"}, {"source": ""}],
                                },
                                {
                                    "key": "championship",
                                    "probability": 0.22,
                                    "sources": [{"source": "polymarket"}],
                                },
                            ],
                        },
                        {"name": "No Cells", "stages": []},
                        {"stages": [{"key": "championship", "probability": 0.3}]},
                    ],
                },
            }

        monkeypatch.setattr("app.routes.playoffs.get_playoff_grid", fake_grid)

        ctx = await _compute_league_context("nba", db=object())

        assert ctx is not None
        assert ctx.league_slug == "nba"
        assert ctx.league_name == "NBA Playoffs 2025-26"
        assert ctx.sport_group == "basketball"
        assert {"key": "championship", "label": "Champion"} in ctx.columns
        assert list(ctx.teams) == ["boston celtics"]

        team = ctx.teams["boston celtics"]
        assert team.team_name == "Boston Celtics"
        assert team.team_id == 1
        assert team.league_slug == "nba"
        assert team.conference == "Eastern"
        assert team.record == "64-18"
        assert team.cells == {"make_playoffs": 0.98, "championship": 0.22}
        assert team.changes_24h == {"make_playoffs": 0.01}
        assert team.column_labels["make_playoffs"] == "Make Playoffs"
        assert team.sources_available == ["kalshi", "polymarket"]

    @pytest.mark.asyncio
    async def test_compute_league_context_unknown_or_missing_grid_returns_none(self, monkeypatch):
        async def missing_grid(**kwargs):
            return None

        monkeypatch.setattr("app.routes.playoffs.get_playoff_grid", missing_grid)

        assert await _compute_league_context("not-a-league", db=object()) is None
        assert await _compute_league_context("nba", db=object()) is None

    @pytest.mark.asyncio
    async def test_compute_league_context_empty_team_payload_keeps_league_metadata(
        self,
        monkeypatch,
    ):
        async def empty_grid(**kwargs):
            return {"teams": []}

        monkeypatch.setattr("app.routes.playoffs.get_playoff_grid", empty_grid)

        ctx = await _compute_league_context("nba", db=object())

        assert ctx is not None
        assert ctx.league_slug == "nba"
        assert ctx.league_name == "NBA Playoffs 2025-26"
        assert ctx.sport_group == "basketball"
        assert ctx.teams == {}

    @pytest.mark.asyncio
    async def test_get_team_context_uses_sport_key_scope_and_normalized_name(
        self,
        monkeypatch,
    ):
        league_calls = []

        async def fake_league_context(league_slug, db):
            league_calls.append(league_slug)
            return LeagueContext(
                league_slug=league_slug,
                teams={
                    "boston celtics": TeamLeagueContext(
                        team_name="Boston Celtics",
                        league_slug=league_slug,
                        cells={"championship": 0.22},
                    ),
                    "new york liberty": TeamLeagueContext(
                        team_name="New York Liberty",
                        league_slug=league_slug,
                        cells={"championship": 0.31},
                    ),
                },
            )

        monkeypatch.setattr(league_context_service, "get_league_context", fake_league_context)

        team = await get_team_context("Celtics", "basketball_nba", db=object())
        assert team is not None
        assert team.team_name == "Boston Celtics"
        assert team.league_slug == "nba"
        assert league_calls == ["nba"]

        assert await get_team_context("Boston Celtics", "cricket_test", db=object()) is None

    @pytest.mark.asyncio
    async def test_enrich_event_with_context_returns_detail_page_shape_for_matching_team(
        self,
        monkeypatch,
    ):
        class FakeScalarResult:
            def scalar(self):
                return "basketball_nba"

        class FakeDB:
            async def execute(self, statement):
                return FakeScalarResult()

        async def fake_league_context(league_slug, db):
            assert league_slug == "nba"
            return LeagueContext(
                league_slug="nba",
                league_name="NBA Playoffs 2025-26",
                sport_group="basketball",
                columns=[{"key": "championship", "label": "Champion"}],
                teams={
                    "boston celtics": TeamLeagueContext(
                        team_name="Boston Celtics",
                        league_slug="nba",
                        conference="Eastern",
                        record="64-18",
                        cells={"championship": 0.22},
                        changes_24h={"championship": 0.02},
                        sources_available=["kalshi"],
                    ),
                },
            )

        monkeypatch.setattr(league_context_service, "get_league_context", fake_league_context)
        event = SimpleNamespace(
            sport_id=7,
            home_team_name="Boston Celtics",
            away_team_name="Los Angeles Lakers",
        )

        result = await enrich_event_with_context(event, FakeDB())

        assert result == {
            "league_slug": "nba",
            "league_name": "NBA Playoffs 2025-26",
            "columns": [{"key": "championship", "label": "Champion"}],
            "league_page_url": "/basketball/nba",
            "home_team": {
                "cells": {"championship": 0.22},
                "changes_24h": {"championship": 0.02},
                "record": "64-18",
                "conference": "Eastern",
                "sources_available": ["kalshi"],
            },
        }

    @pytest.mark.asyncio
    async def test_enrich_event_with_context_returns_none_when_no_team_matches(
        self,
        monkeypatch,
    ):
        class FakeScalarResult:
            def scalar(self):
                return "basketball_nba"

        class FakeDB:
            async def execute(self, statement):
                return FakeScalarResult()

        async def fake_league_context(league_slug, db):
            return LeagueContext(
                league_slug="nba",
                teams={
                    "boston celtics": TeamLeagueContext(
                        team_name="Boston Celtics",
                        league_slug="nba",
                        cells={"championship": 0.22},
                    ),
                },
            )

        monkeypatch.setattr(league_context_service, "get_league_context", fake_league_context)
        event = SimpleNamespace(
            sport_id=7,
            home_team_name="Miami Heat",
            away_team_name="Denver Nuggets",
        )

        assert await enrich_event_with_context(event, FakeDB()) is None


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
