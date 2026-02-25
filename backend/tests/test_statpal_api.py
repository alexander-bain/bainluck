"""Tests for StatPal API client parsing and helpers."""

import pytest
from datetime import datetime, timezone


# =============================================================================
# Datetime parsing
# =============================================================================

class TestParseDatetime:
    """Tests for the _parse_datetime helper."""

    def test_iso_with_timezone(self):
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("2026-02-25T19:00:00+00:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.hour == 19

    def test_iso_with_z(self):
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("2026-02-25T19:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_iso_with_milliseconds(self):
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("2026-02-25T19:00:00.123Z")
        assert dt is not None
        assert dt.year == 2026

    def test_date_only(self):
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("2026-02-25")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 25

    def test_datetime_no_tz(self):
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("2026-02-25 19:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc  # Should assume UTC

    def test_none_input(self):
        from app.services.statpal_api import _parse_datetime
        assert _parse_datetime(None) is None

    def test_empty_string(self):
        from app.services.statpal_api import _parse_datetime
        assert _parse_datetime("") is None

    def test_garbage_input(self):
        from app.services.statpal_api import _parse_datetime
        assert _parse_datetime("not-a-date") is None

    def test_already_datetime(self):
        from app.services.statpal_api import _parse_datetime
        dt = datetime(2026, 2, 25, tzinfo=timezone.utc)
        assert _parse_datetime(dt) == dt


# =============================================================================
# Status normalization
# =============================================================================

class TestNormalizeStatus:
    """Tests for the _normalize_status helper."""

    def test_scheduled_variants(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("Scheduled") == "scheduled"
        assert _normalize_status("Not Started") == "scheduled"
        assert _normalize_status("NS") == "scheduled"
        assert _normalize_status("TBD") == "scheduled"

    def test_live_variants(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("Live") == "live"
        assert _normalize_status("In Progress") == "live"
        assert _normalize_status("1H") == "live"
        assert _normalize_status("2H") == "live"
        assert _normalize_status("HT") == "live"
        assert _normalize_status("Q1") == "live"
        assert _normalize_status("Q4") == "live"
        assert _normalize_status("OT") == "live"

    def test_finished_variants(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("Finished") == "finished"
        assert _normalize_status("Final") == "finished"
        assert _normalize_status("FT") == "finished"
        assert _normalize_status("AET") == "finished"
        assert _normalize_status("Completed") == "finished"
        assert _normalize_status("Game Over") == "finished"

    def test_postponed_variants(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("Postponed") == "postponed"
        assert _normalize_status("PST") == "postponed"
        assert _normalize_status("Delayed") == "postponed"

    def test_cancelled_variants(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("Cancelled") == "cancelled"
        assert _normalize_status("CANC") == "cancelled"
        assert _normalize_status("Abandoned") == "cancelled"

    def test_suspended_variants(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("Suspended") == "suspended"
        assert _normalize_status("SUSP") == "suspended"
        assert _normalize_status("INT") == "suspended"

    def test_unknown_status_passthrough(self):
        from app.services.statpal_api import _normalize_status
        result = _normalize_status("some_weird_status")
        assert result == "some_weird_status"

    def test_case_insensitive(self):
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("FINISHED") == "finished"
        assert _normalize_status("LIVE") == "live"
        assert _normalize_status("SCHEDULED") == "scheduled"


# =============================================================================
# Safe int conversion
# =============================================================================

class TestSafeInt:
    """Tests for the _safe_int helper."""

    def test_int_input(self):
        from app.services.statpal_api import _safe_int
        assert _safe_int(42) == 42

    def test_string_int(self):
        from app.services.statpal_api import _safe_int
        assert _safe_int("42") == 42

    def test_float_input(self):
        from app.services.statpal_api import _safe_int
        assert _safe_int(42.0) == 42

    def test_none_input(self):
        from app.services.statpal_api import _safe_int
        assert _safe_int(None) is None

    def test_garbage_input(self):
        from app.services.statpal_api import _safe_int
        assert _safe_int("not-a-number") is None

    def test_empty_string(self):
        from app.services.statpal_api import _safe_int
        assert _safe_int("") is None


# =============================================================================
# Fixture parsing
# =============================================================================

class TestFixtureParsing:
    """Tests for _parse_single_fixture and _parse_fixtures."""

    def test_parse_nested_teams(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "12345",
            "teams": {
                "home": {"id": 1, "name": "Boston Celtics"},
                "away": {"id": 2, "name": "Los Angeles Lakers"},
            },
            "scores": {"home": 105, "away": 98},
            "status": "Final",
            "date": "2026-02-25T19:00:00Z",
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.home_team == "Boston Celtics"
        assert fixture.away_team == "Los Angeles Lakers"
        assert fixture.home_score == 105
        assert fixture.away_score == 98
        assert fixture.status == "finished"
        assert fixture.fixture_id == "12345"

    def test_parse_flat_teams(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "67890",
            "home_team": "New York Yankees",
            "away_team": "Boston Red Sox",
            "home_score": 5,
            "away_score": 3,
            "status": "Finished",
            "date": "2026-06-15T18:00:00Z",
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.home_team == "New York Yankees"
        assert fixture.away_team == "Boston Red Sox"
        assert fixture.home_score == 5
        assert fixture.away_score == 3

    def test_parse_missing_teams_returns_none(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {"id": "99", "status": "Scheduled"}
        fixture = service._parse_single_fixture(item)
        assert fixture is None

    def test_parse_non_dict_returns_none(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert service._parse_single_fixture("not a dict") is None
        assert service._parse_single_fixture(None) is None

    def test_parse_dict_status(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "100",
            "home_team": "Team A",
            "away_team": "Team B",
            "status": {"long": "In Progress", "short": "1H"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.status == "live"

    def test_parse_venue_dict(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "101",
            "home_team": "Team A",
            "away_team": "Team B",
            "status": "Scheduled",
            "venue": {"name": "TD Garden", "city": "Boston"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.venue == "TD Garden"

    def test_parse_venue_string(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "102",
            "home_team": "Team A",
            "away_team": "Team B",
            "status": "Scheduled",
            "venue": "Madison Square Garden",
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.venue == "Madison Square Garden"

    def test_parse_fixtures_data_wrapper(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        data = {
            "data": [
                {
                    "id": "1",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "status": "Scheduled",
                },
                {
                    "id": "2",
                    "home_team": "Team C",
                    "away_team": "Team D",
                    "status": "Live",
                },
            ]
        }
        fixtures = service._parse_fixtures(data, "nfl")
        assert len(fixtures) == 2
        assert fixtures[0].fixture_id == "1"
        assert fixtures[1].fixture_id == "2"

    def test_parse_fixtures_list_directly(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        data = [
            {"id": "1", "home_team": "A", "away_team": "B", "status": "NS"},
        ]
        fixtures = service._parse_fixtures(data, "nba")
        assert len(fixtures) == 1

    def test_parse_fixtures_empty(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert service._parse_fixtures({}, "nfl") == []
        assert service._parse_fixtures({"data": []}, "nfl") == []

    def test_parse_scores_nested(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "200",
            "home_team": "A",
            "away_team": "B",
            "status": "FT",
            "scores": {"home": "110", "away": "105"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.home_score == 110
        assert fixture.away_score == 105

    def test_parse_league_dict(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "300",
            "home_team": "A",
            "away_team": "B",
            "status": "NS",
            "league": {"name": "NBA", "id": 1},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.league == "NBA"

    def test_parse_round_info(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "400",
            "home_team": "A",
            "away_team": "B",
            "status": "NS",
            "round": "Week 15",
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.round_info == "Week 15"

    def test_parse_end_time(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "500",
            "home_team": "A",
            "away_team": "B",
            "status": "FT",
            "date": "2026-02-25T19:00:00Z",
            "end_time": "2026-02-25T22:30:00Z",
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.end_time is not None
        assert fixture.end_time.hour == 22


# =============================================================================
# is_available check
# =============================================================================

class TestIsAvailable:
    """Tests for the is_available function."""

    def test_not_available_without_key(self, monkeypatch):
        monkeypatch.delenv("STATPAL_API_KEY", raising=False)
        from app.services.statpal_api import is_available
        assert not is_available()

    def test_available_with_key(self, monkeypatch):
        monkeypatch.setenv("STATPAL_API_KEY", "test_key_123")
        from app.services.statpal_api import is_available
        assert is_available()


# =============================================================================
# Base URL selection
# =============================================================================

class TestBaseUrl:
    """Tests for sport-based URL routing."""

    def test_soccer_uses_v2(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert "v2" in service._base_url("soccer")

    def test_nfl_uses_v1(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert "v1" in service._base_url("nfl")

    def test_nba_uses_v1(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert "v1" in service._base_url("nba")

    def test_mlb_uses_v1(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert "v1" in service._base_url("mlb")

    def test_nhl_uses_v1(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        assert "v1" in service._base_url("nhl")


# =============================================================================
# Dataclass construction
# =============================================================================

class TestDataclasses:
    """Tests for StatPal data classes."""

    def test_fixture_defaults(self):
        from app.services.statpal_api import StatPalFixture
        f = StatPalFixture(fixture_id="1", home_team="A", away_team="B")
        assert f.status == "scheduled"
        assert f.home_score is None
        assert f.end_time is None

    def test_player_defaults(self):
        from app.services.statpal_api import StatPalPlayer
        p = StatPalPlayer(player_id="1", name="John Doe")
        assert p.position is None
        assert p.jersey_number is None
        assert p.status is None

    def test_injury_defaults(self):
        from app.services.statpal_api import StatPalInjury
        i = StatPalInjury(player_id="1", player_name="John", team="TeamA")
        assert i.injury_type == ""
        assert i.status == ""
        assert i.detail is None

    def test_play_event_defaults(self):
        from app.services.statpal_api import StatPalPlayEvent
        p = StatPalPlayEvent(description="Touchdown")
        assert p.play_id is None
        assert p.period is None
        assert p.team is None

    def test_team_defaults(self):
        from app.services.statpal_api import StatPalTeam
        t = StatPalTeam(team_id="1", name="Test Team")
        assert t.short_name is None
        assert t.abbreviation is None

    def test_game_detail_defaults(self):
        from app.services.statpal_api import StatPalGameDetail
        g = StatPalGameDetail(fixture_id="1", status="live")
        assert g.plays == []
        assert g.injuries == []
        assert g.home_team == ""


# =============================================================================
# Sync task helpers
# =============================================================================

class TestSyncHelpers:
    """Tests for sync task helper functions."""

    def test_fixture_match_key(self):
        from app.tasks.statpal_sync import _fixture_match_key
        key = _fixture_match_key("Boston Celtics", "Los Angeles Lakers")
        assert key == "boston celtics|los angeles lakers"

    def test_fixture_match_key_strips_whitespace(self):
        from app.tasks.statpal_sync import _fixture_match_key
        key = _fixture_match_key("  Boston Celtics  ", "  Lakers  ")
        assert key == "boston celtics|lakers"

    def test_get_set_statpal_id(self):
        from app.tasks.statpal_sync import _get_statpal_id, _set_statpal_id

        class FakeEvent:
            win_probability_sources = None

        event = FakeEvent()
        assert _get_statpal_id(event) is None

        _set_statpal_id(event, "SP12345")
        assert _get_statpal_id(event) == "SP12345"

    def test_set_statpal_id_preserves_existing(self):
        from app.tasks.statpal_sync import _get_statpal_id, _set_statpal_id

        class FakeEvent:
            win_probability_sources = {"espn": 0.65}

        event = FakeEvent()
        _set_statpal_id(event, "SP99")
        assert _get_statpal_id(event) == "SP99"
        assert event.win_probability_sources["espn"] == 0.65


# =============================================================================
# Config mapping
# =============================================================================

class TestConfig:
    """Tests for StatPal config in tasks/config.py."""

    def test_sport_mapping_exists(self):
        from app.tasks.config import STATPAL_SPORT_MAPPING
        assert "americanfootball_nfl" in STATPAL_SPORT_MAPPING
        assert "basketball_nba" in STATPAL_SPORT_MAPPING
        assert "baseball_mlb" in STATPAL_SPORT_MAPPING
        assert "icehockey_nhl" in STATPAL_SPORT_MAPPING

    def test_sport_mapping_values(self):
        from app.tasks.config import STATPAL_SPORT_MAPPING
        assert STATPAL_SPORT_MAPPING["americanfootball_nfl"] == "nfl"
        assert STATPAL_SPORT_MAPPING["basketball_nba"] == "nba"
        assert STATPAL_SPORT_MAPPING["baseball_mlb"] == "mlb"
        assert STATPAL_SPORT_MAPPING["icehockey_nhl"] == "nhl"
        assert STATPAL_SPORT_MAPPING["soccer_epl"] == "soccer"

    def test_polling_intervals(self):
        from app.tasks.config import (
            STATPAL_SCHEDULE_POLL_INTERVAL,
            STATPAL_INJURY_POLL_INTERVAL,
            STATPAL_LIVE_PLAY_POLL_INTERVAL,
        )
        assert STATPAL_SCHEDULE_POLL_INTERVAL == 3600  # hourly
        assert STATPAL_INJURY_POLL_INTERVAL == 900     # 15 min
        assert STATPAL_LIVE_PLAY_POLL_INTERVAL == 60   # 1 min
