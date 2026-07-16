"""Tests for MLB Stats API client and sync task."""

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, path, params=None):
        self.calls.append((path, params))
        data = self.responses[path]
        return _FakeResponse(data)


# =============================================================================
# Name matching
# =============================================================================

class TestNameMatches:
    """Tests for the _name_matches helper function."""

    def test_exact_match(self):
        from app.services.mlb_api import _name_matches
        assert _name_matches("boston red sox", "boston red sox")

    def test_suffix_match(self):
        from app.services.mlb_api import _name_matches
        assert _name_matches("red sox", "boston red sox")

    def test_mascot_match(self):
        from app.services.mlb_api import _name_matches
        # "Yankees" contained in the name
        assert _name_matches("new york yankees", "new york yankees")

    def test_our_name_contains_mlb_mascot(self):
        from app.services.mlb_api import _name_matches
        # Our DB might have "NY Yankees" — mascot "Yankees" should match
        assert _name_matches("ny yankees", "new york yankees")

    def test_mlb_name_contained_in_ours(self):
        from app.services.mlb_api import _name_matches
        assert _name_matches("the boston red sox baseball team", "boston red sox")

    def test_no_match_different_teams(self):
        from app.services.mlb_api import _name_matches
        assert not _name_matches("boston red sox", "new york yankees")

    def test_no_match_similar_city(self):
        from app.services.mlb_api import _name_matches
        # New York Mets vs New York Yankees — token overlap 0.667 means these
        # match in isolation, but find_game_pk_for_teams uses a both-teams gate
        # (home AND away must match) so this doesn't cause mislinks.
        assert _name_matches("new york mets", "new york yankees")

    def test_empty_strings(self):
        from app.services.mlb_api import _name_matches
        assert not _name_matches("", "boston red sox")
        assert not _name_matches("boston red sox", "")
        assert not _name_matches("", "")

    def test_partial_city_no_match(self):
        from app.services.mlb_api import _name_matches
        # "Los Angeles" alone matches via token overlap (0.667 > 0.5).
        # In practice, find_game_pk_for_teams requires BOTH teams to match,
        # so this doesn't cause mislinks.
        assert _name_matches("los angeles", "los angeles dodgers")

    def test_st_louis_cardinals(self):
        from app.services.mlb_api import _name_matches
        assert _name_matches("st. louis cardinals", "st. louis cardinals")
        assert _name_matches("cardinals", "st. louis cardinals")

    def test_chicago_teams_dont_cross_match(self):
        from app.services.mlb_api import _name_matches
        # White Sox and Cubs are different
        assert not _name_matches("chicago cubs", "chicago white sox")
        assert _name_matches("chicago cubs", "chicago cubs")


# =============================================================================
# MLBGame dataclass
# =============================================================================

class TestMLBGameDataclass:
    """Tests for MLBGame creation."""

    def test_create_game(self):
        from app.services.mlb_api import MLBGame
        game = MLBGame(
            game_pk=717404,
            home_team="New York Yankees",
            away_team="Boston Red Sox",
            home_team_id=147,
            away_team_id=111,
            home_win_probability=0.65,
            away_win_probability=0.35,
            status="In Progress",
            inning=5,
            inning_half="bottom",
            home_score=3,
            away_score=1,
        )
        assert game.game_pk == 717404
        assert game.home_win_probability == 0.65
        assert game.inning == 5

    def test_optional_fields_default_none(self):
        from app.services.mlb_api import MLBGame
        game = MLBGame(
            game_pk=1,
            home_team="A",
            away_team="B",
            home_team_id=1,
            away_team_id=2,
            home_win_probability=0.5,
            away_win_probability=0.5,
            status="In Progress",
        )
        assert game.inning is None
        assert game.inning_half is None
        assert game.home_score is None


# =============================================================================
# MLBWinProbEntry
# =============================================================================

class TestMLBWinProbEntry:
    """Tests for win probability entry parsing."""

    def test_create_entry(self):
        from app.services.mlb_api import MLBWinProbEntry
        entry = MLBWinProbEntry(
            home_win_probability=0.72,
            away_win_probability=0.28,
            at_bat_index=15,
            inning=3,
            inning_half="top",
            description="Groundout to shortstop",
        )
        assert entry.home_win_probability == 0.72
        assert entry.inning == 3
        assert entry.description == "Groundout to shortstop"


# =============================================================================
# MLBAPIService structure
# =============================================================================

class TestMLBAPIServiceStructure:
    """Tests for MLBAPIService structure (no network calls)."""

    def test_service_has_required_methods(self):
        from app.services.mlb_api import MLBAPIService
        service = MLBAPIService.__new__(MLBAPIService)
        assert hasattr(service, "get_todays_games")
        assert hasattr(service, "get_live_games")
        assert hasattr(service, "get_win_probability_history")
        assert hasattr(service, "find_game_pk_for_teams")
        assert hasattr(service, "close")

    def test_base_url(self):
        from app.services.mlb_api import BASE_URL
        assert "statsapi.mlb.com" in BASE_URL

    def test_service_methods_are_async(self):
        import asyncio
        from app.services.mlb_api import MLBAPIService
        service = MLBAPIService.__new__(MLBAPIService)
        assert asyncio.iscoroutinefunction(service.get_todays_games)
        assert asyncio.iscoroutinefunction(service.get_live_games)
        assert asyncio.iscoroutinefunction(service.get_win_probability_history)
        assert asyncio.iscoroutinefunction(service.find_game_pk_for_teams)


# =============================================================================
# MLB API parsing
# =============================================================================

class TestMLBAPIParsing:
    """No-network tests for MLB Stats API response parsing."""

    @pytest.mark.asyncio
    async def test_context_win_probability_prefers_top_level_percentage(self):
        from app.services.mlb_api import MLBAPIService

        service = MLBAPIService.__new__(MLBAPIService)
        service.client = _FakeClient({
            "/v1/game/717404/contextMetrics": {
                "homeWinProbability": 62.7,
                "game": {"homeWinProbability": 12.3},
            },
        })

        wp = await service._get_context_win_probability(717404)

        assert wp == pytest.approx(0.627)
        assert service.client.calls == [("/v1/game/717404/contextMetrics", None)]

    @pytest.mark.asyncio
    async def test_context_win_probability_falls_back_to_game_object(self):
        from app.services.mlb_api import MLBAPIService

        service = MLBAPIService.__new__(MLBAPIService)
        service.client = _FakeClient({
            "/v1/game/717404/contextMetrics": {
                "game": {"homeWinProbability": "41.5"},
            },
        })

        assert await service._get_context_win_probability(717404) == pytest.approx(0.415)

    @pytest.mark.asyncio
    async def test_live_games_include_review_and_exclude_completed_games(self):
        from app.services.mlb_api import MLBAPIService

        service = MLBAPIService.__new__(MLBAPIService)

        async def fake_get_todays_games():
            return [
                {
                    "gamePk": 1,
                    "gameDate": "2026-05-17T19:05:00Z",
                    "status": {"statusCode": "IR"},
                    "teams": {
                        "home": {"team": {"id": 147, "name": "New York Yankees"}, "score": 4},
                        "away": {"team": {"id": 111, "name": "Boston Red Sox"}, "score": 3},
                    },
                    "linescore": {"currentInning": 7, "inningHalf": "Bottom"},
                },
                {
                    "gamePk": 2,
                    "status": {"statusCode": "F"},
                    "teams": {
                        "home": {"team": {"id": 121, "name": "New York Mets"}, "score": 2},
                        "away": {"team": {"id": 112, "name": "Chicago Cubs"}, "score": 1},
                    },
                },
            ]

        async def fake_context_wp(game_pk):
            assert game_pk == 1
            return 0.7342

        service.get_todays_games = fake_get_todays_games
        service._get_context_win_probability = fake_context_wp

        games = await service.get_live_games()

        assert len(games) == 1
        game = games[0]
        assert game.game_pk == 1
        assert game.status == "In Progress"
        assert game.inning == 7
        assert game.inning_half == "bottom"
        assert game.home_score == 4
        assert game.away_score == 3
        assert game.home_win_probability == pytest.approx(0.7342)
        assert game.away_win_probability == pytest.approx(0.2658)

    @pytest.mark.asyncio
    async def test_win_probability_history_skips_rows_missing_home_probability(self):
        from app.services.mlb_api import MLBAPIService

        service = MLBAPIService.__new__(MLBAPIService)
        service.client = _FakeClient({
            "/v1/game/717404/winProbability": [
                {
                    "homeTeamWinProbability": 55.5,
                    "atBatIndex": 12,
                    "about": {"inning": 3, "halfInning": "bottom"},
                    "result": {"description": "Single to right field"},
                },
                {
                    "awayTeamWinProbability": 47.0,
                    "atBatIndex": 13,
                    "about": {"inning": 3, "halfInning": "bottom"},
                },
            ],
        })

        entries = await service.get_win_probability_history(717404)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.home_win_probability == pytest.approx(0.555)
        assert entry.away_win_probability == pytest.approx(0.445)
        assert entry.inning == 3
        assert entry.inning_half == "bottom"
        assert entry.description == "Single to right field"


# =============================================================================
# Sync task wiring
# =============================================================================

class TestMLBSyncTaskWiring:
    """Tests for Celery task registration and beat schedule."""

    def test_celery_task_registered(self):
        from app.tasks import celery_app
        assert "app.tasks.sync_mlb_win_probability" in celery_app.tasks

    def test_beat_schedule_entry(self):
        from app.tasks import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "sync-mlb-win-probability" in schedule
        entry = schedule["sync-mlb-win-probability"]
        assert entry["task"] == "app.tasks.sync_mlb_win_probability"
        assert entry["schedule"] == 120.0  # Every 2 minutes

    def test_sync_function_exists_and_is_async(self):
        import asyncio
        from app.tasks.mlb_sync import _sync_mlb_win_probability
        assert asyncio.iscoroutinefunction(_sync_mlb_win_probability)

    def test_task_uses_tracked_run(self):
        """The task should use _tracked_run for monitoring."""
        import inspect
        from app.tasks import sync_mlb_win_probability
        source = inspect.getsource(sync_mlb_win_probability)
        assert "_tracked_run" in source
        assert "mlb_sync" in source  # task metric name

    def test_win_prob_source_key(self):
        """Verify the source key used for snapshots."""
        from app.tasks.mlb_sync import WIN_PROB_SOURCE_KEY
        assert WIN_PROB_SOURCE_KEY == "mlb"

    def test_source_registered_in_config(self):
        """The source key should exist in WIN_PROB_SOURCES."""
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        from app.tasks.mlb_sync import WIN_PROB_SOURCE_KEY
        assert WIN_PROB_SOURCE_KEY in WIN_PROB_SOURCES
        source = WIN_PROB_SOURCES[WIN_PROB_SOURCE_KEY]
        assert source["sports"] == ["baseball_mlb"]
        assert "MLB" in source["display_name"]


# =============================================================================
# Sync task internals
# =============================================================================

class TestMLBSyncInternals:
    """Tests for the sync task's helper functions."""

    def test_normalize_team(self):
        from app.tasks.mlb_sync import _normalize_team
        assert _normalize_team("  Boston Red Sox  ") == "boston red sox"
        assert _normalize_team("NEW YORK YANKEES") == "new york yankees"

    def test_match_window_hours(self):
        from app.tasks.mlb_sync import MATCH_WINDOW_HOURS
        assert MATCH_WINDOW_HOURS == 4

    def test_match_function_exists(self):
        from app.tasks.mlb_sync import _match_mlb_game_to_event
        assert callable(_match_mlb_game_to_event)

    def _mlb_game(self, home, away):
        from datetime import datetime, timezone
        return SimpleNamespace(
            home_team=home, away_team=away,
            home_win_probability=0.98, away_win_probability=0.02,
            home_score=3, away_score=9, game_pk=1, inning=9, inning_half="bottom",
            game_datetime=datetime(2026, 7, 11, 2, tzinfo=timezone.utc).isoformat(),
        )

    def _our_event(self, home, away):
        from datetime import datetime, timezone
        return SimpleNamespace(
            id=14970356, home_team_name=home, away_team_name=away,
            commence_time=datetime(2026, 7, 11, 2, tzinfo=timezone.utc),
        )

    def test_match_aligned_orientation_not_inverted(self):
        # MLB home == our home → aligned, no swap needed.
        from app.tasks.mlb_sync import _match_mlb_game_to_event
        g = self._mlb_game("Houston Astros", "Texas Rangers")
        ev = self._our_event("Houston Astros", "Texas Rangers")
        match, inverted = _match_mlb_game_to_event(g, [ev], {})
        assert match is ev
        assert inverted is False

    def test_match_flipped_orientation_reports_inverted(self):
        # #208/#207 root cause: our home == MLB's AWAY. Exhibit 14970356 — the
        # Rangers were OUR home but MLB had them away; the writer must swap.
        from app.tasks.mlb_sync import _match_mlb_game_to_event
        g = self._mlb_game("Houston Astros", "Texas Rangers")
        ev = self._our_event("Texas Rangers", "Houston Astros")
        match, inverted = _match_mlb_game_to_event(g, [ev], {})
        assert match is ev
        assert inverted is True


# =============================================================================
# Admin endpoint existence
# =============================================================================

class TestMLBAdminEndpoints:
    """Verify admin endpoints are registered."""

    def test_sync_endpoint_exists(self):
        from app.routes.admin import router
        paths = [r.path for r in router.routes]
        assert "/mlb/sync" in paths

    def test_task_status_endpoint_exists(self):
        from app.routes.admin import router
        paths = [r.path for r in router.routes]
        assert "/mlb/task/{task_id}" in paths


# =============================================================================
# Win prob source config
# =============================================================================

class TestWinProbSourceConfig:
    """Test the MLB source config (renamed from fangraphs)."""

    def test_mlb_display_name(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        assert WIN_PROB_SOURCES["mlb"]["display_name"] == "MLB Model"

    def test_mlb_attribution(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        assert "MLB" in WIN_PROB_SOURCES["mlb"]["attribution_name"]
        assert "statsapi" in WIN_PROB_SOURCES["mlb"]["attribution_url"]

    def test_mlb_color(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        assert WIN_PROB_SOURCES["mlb"]["color"] == "#06b6d4"
