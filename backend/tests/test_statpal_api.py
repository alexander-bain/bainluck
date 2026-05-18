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

    def test_dd_mm_yyyy_with_time(self):
        """StatPal uses DD.MM.YYYY HH:MM format for dates."""
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("27.02.2026 19:30")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 27
        assert dt.hour == 19
        assert dt.minute == 30
        assert dt.tzinfo == timezone.utc

    def test_dd_mm_yyyy_date_only(self):
        """StatPal date-only format."""
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("11.10.2025")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 11

    def test_dd_mm_yyyy_midnight(self):
        """StatPal sometimes has 00:00 for TBD times."""
        from app.services.statpal_api import _parse_datetime
        dt = _parse_datetime("15.03.2026 00:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour == 0


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

    def test_after_overtime_variants(self):
        """StatPal uses 'After Over Time' for overtime finishes."""
        from app.services.statpal_api import _normalize_status
        assert _normalize_status("After Over Time") == "finished"
        assert _normalize_status("after overtime") == "finished"
        assert _normalize_status("After Extra Time") == "finished"

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

    @pytest.mark.parametrize("raw_status", ["Q3", "1H", "HT"])
    def test_parse_live_period_status_preserves_raw_status(self, raw_status):
        from app.services.statpal_api import StatPalAPIService

        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "100",
            "home_team": "Team A",
            "away_team": "Team B",
            "status": raw_status,
        }
        fixture = service._parse_single_fixture(item)

        assert fixture is not None
        assert fixture.status == "live"
        assert fixture.raw_status == raw_status

    def test_parse_finished_status_does_not_set_raw_status(self):
        from app.services.statpal_api import StatPalAPIService

        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "100",
            "home_team": "Team A",
            "away_team": "Team B",
            "status": "Final",
        }
        fixture = service._parse_single_fixture(item)

        assert fixture is not None
        assert fixture.status == "finished"
        assert fixture.raw_status is None

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
# _extract_match_items — response format extraction
# =============================================================================

class TestExtractMatchItems:
    """Tests for _extract_match_items with various StatPal response formats."""

    def test_v1_season_schedule_format(self):
        """v1 NBA/NFL/NHL/MLB: {"scores": {"tournament": {"match": [...]}}}"""
        from app.services.statpal_api import StatPalAPIService
        data = {
            "scores": {
                "tournament": {
                    "league": "NBA",
                    "season": "2025/2026",
                    "match": [
                        {"id": "1", "home": {"name": "Celtics"}, "away": {"name": "Lakers"}},
                        {"id": "2", "home": {"name": "Nets"}, "away": {"name": "Knicks"}},
                    ]
                }
            }
        }
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 2
        assert items[0]["id"] == "1"
        assert items[1]["id"] == "2"

    def test_v1_livescores_format(self):
        """v1 livescores: {"livescores": {"tournament": {"match": [...]}}}"""
        from app.services.statpal_api import StatPalAPIService
        data = {
            "livescores": {
                "tournament": {
                    "match": [
                        {"id": "10", "home": {"name": "Heat"}, "away": {"name": "Bulls"}},
                    ]
                }
            }
        }
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 1
        assert items[0]["id"] == "10"

    def test_soccer_v2_daily_format(self):
        """Soccer v2: {"matches_DD_MM_YYYY": {"league": [{"match": [...]}]}}"""
        from app.services.statpal_api import StatPalAPIService
        data = {
            "matches_28_02_2026": {
                "league": [
                    {
                        "league_name": "English Premier League",
                        "match": [
                            {"id": "100", "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                            {"id": "101", "home": {"name": "Liverpool"}, "away": {"name": "Man City"}},
                        ]
                    },
                    {
                        "league_name": "La Liga",
                        "match": [
                            {"id": "200", "home": {"name": "Barcelona"}, "away": {"name": "Real Madrid"}},
                        ]
                    },
                ]
            }
        }
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 3
        assert items[0]["id"] == "100"
        assert items[2]["id"] == "200"

    def test_soccer_v2_single_match_as_dict(self):
        """Soccer v2: single match returned as dict instead of list."""
        from app.services.statpal_api import StatPalAPIService
        data = {
            "matches_28_02_2026": {
                "league": [
                    {
                        "league_name": "MLS",
                        "match": {"id": "300", "home": {"name": "LAFC"}, "away": {"name": "Galaxy"}},
                    },
                ]
            }
        }
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 1
        assert items[0]["id"] == "300"

    def test_golf_fixtures_format(self):
        """Golf: {"fixtures": {"tournament": [...]}}"""
        from app.services.statpal_api import StatPalAPIService
        data = {
            "fixtures": {
                "tournament": [
                    {"id": "PGA1", "name": "The Masters"},
                    {"id": "PGA2", "name": "US Open"},
                ]
            }
        }
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 2

    def test_data_wrapper_fallback(self):
        """Fallback: {"data": [...]}"""
        from app.services.statpal_api import StatPalAPIService
        data = {
            "data": [
                {"id": "1", "home_team": "A", "away_team": "B"},
            ]
        }
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 1

    def test_empty_dict(self):
        from app.services.statpal_api import StatPalAPIService
        items = StatPalAPIService._extract_match_items({})
        assert items == []

    def test_non_dict_passthrough(self):
        """Non-dict, non-list data is wrapped in a list."""
        from app.services.statpal_api import StatPalAPIService
        items = StatPalAPIService._extract_match_items("some_string")
        assert items == ["some_string"]

    def test_list_input_passthrough(self):
        """List input is returned directly."""
        from app.services.statpal_api import StatPalAPIService
        data = [{"id": "1"}, {"id": "2"}]
        items = StatPalAPIService._extract_match_items(data)
        assert len(items) == 2
        assert items[0]["id"] == "1"

    def test_none_returns_empty(self):
        from app.services.statpal_api import StatPalAPIService
        items = StatPalAPIService._extract_match_items(None)
        assert items == []


# =============================================================================
# StatPal native match format parsing
# =============================================================================

class TestStatPalNativeFormat:
    """Tests for _parse_single_fixture with StatPal's actual v1 format.

    StatPal returns: {"id": "988739", "date": "11.10.2025", "time": "00:00",
                      "status": "Finished", "venue": "Frost Bank Center",
                      "home": {"id": "2689", "name": "San Antonio Spurs", "totalscore": "134"},
                      "away": {"id": "2679", "name": "Utah Jazz", "totalscore": "130"}}
    """

    def test_basic_nba_match(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "988739",
            "date": "11.10.2025",
            "time": "00:00",
            "status": "Finished",
            "venue": "Frost Bank Center",
            "home": {"id": "2689", "name": "San Antonio Spurs", "totalscore": "134"},
            "away": {"id": "2679", "name": "Utah Jazz", "totalscore": "130"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.fixture_id == "988739"
        assert fixture.home_team == "San Antonio Spurs"
        assert fixture.away_team == "Utah Jazz"
        assert fixture.home_team_id == "2689"
        assert fixture.away_team_id == "2679"
        assert fixture.home_score == 134
        assert fixture.away_score == 130
        assert fixture.status == "finished"
        assert fixture.venue == "Frost Bank Center"
        assert fixture.start_time is not None
        assert fixture.start_time.year == 2025
        assert fixture.start_time.month == 10
        assert fixture.start_time.day == 11

    def test_scheduled_match_with_time(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "1001234",
            "date": "27.02.2026",
            "time": "19:30",
            "status": "Not Started",
            "venue": "TD Garden",
            "home": {"id": "2685", "name": "Boston Celtics"},
            "away": {"id": "2691", "name": "Brooklyn Nets"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.home_team == "Boston Celtics"
        assert fixture.away_team == "Brooklyn Nets"
        assert fixture.status == "scheduled"
        assert fixture.home_score is None
        assert fixture.away_score is None
        assert fixture.start_time is not None
        assert fixture.start_time.hour == 19
        assert fixture.start_time.minute == 30

    def test_live_match_with_scores(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "1001235",
            "date": "27.02.2026",
            "time": "20:00",
            "status": "Q3",
            "venue": "Chase Center",
            "home": {"id": "2688", "name": "Golden State Warriors", "totalscore": "78"},
            "away": {"id": "2687", "name": "Denver Nuggets", "totalscore": "72"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture is not None
        assert fixture.status == "live"
        assert fixture.home_score == 78
        assert fixture.away_score == 72

    def test_totalscore_as_int(self):
        """totalscore may come as int instead of string."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "123",
            "date": "27.02.2026",
            "time": "19:00",
            "status": "Finished",
            "home": {"id": "1", "name": "Team A", "totalscore": 110},
            "away": {"id": "2", "name": "Team B", "totalscore": 105},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.home_score == 110
        assert fixture.away_score == 105

    def test_missing_totalscore(self):
        """Scheduled matches may have no totalscore."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "456",
            "date": "01.03.2026",
            "time": "20:00",
            "status": "NS",
            "home": {"id": "1", "name": "Team A"},
            "away": {"id": "2", "name": "Team B"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.home_score is None
        assert fixture.away_score is None

    def test_after_over_time_status(self):
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "789",
            "date": "27.02.2026",
            "time": "19:00",
            "status": "After Over Time",
            "home": {"id": "1", "name": "Team A", "totalscore": "120"},
            "away": {"id": "2", "name": "Team B", "totalscore": "118"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.status == "finished"

    def test_date_only_no_time(self):
        """When time field is missing, should still parse date."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        item = {
            "id": "999",
            "date": "15.03.2026",
            "status": "NS",
            "home": {"id": "1", "name": "Team A"},
            "away": {"id": "2", "name": "Team B"},
        }
        fixture = service._parse_single_fixture(item)
        assert fixture.start_time is not None
        assert fixture.start_time.day == 15
        assert fixture.start_time.month == 3


# =============================================================================
# Full _parse_fixtures chain with realistic data
# =============================================================================

class TestParseFixturesChain:
    """Tests for the full _parse_fixtures pipeline with realistic StatPal responses."""

    def test_nba_season_schedule(self):
        """Full NBA season-schedule response → parsed fixtures."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        data = {
            "scores": {
                "tournament": {
                    "league": "NBA",
                    "season": "2025/2026",
                    "match": [
                        {
                            "id": "988739",
                            "date": "11.10.2025",
                            "time": "00:00",
                            "status": "Finished",
                            "venue": "Frost Bank Center",
                            "home": {"id": "2689", "name": "San Antonio Spurs", "totalscore": "134"},
                            "away": {"id": "2679", "name": "Utah Jazz", "totalscore": "130"},
                        },
                        {
                            "id": "1001234",
                            "date": "27.02.2026",
                            "time": "19:30",
                            "status": "Not Started",
                            "venue": "TD Garden",
                            "home": {"id": "2685", "name": "Boston Celtics"},
                            "away": {"id": "2691", "name": "Brooklyn Nets"},
                        },
                    ]
                }
            }
        }
        fixtures = service._parse_fixtures(data, "nba")
        assert len(fixtures) == 2
        assert fixtures[0].fixture_id == "988739"
        assert fixtures[0].home_team == "San Antonio Spurs"
        assert fixtures[0].status == "finished"
        assert fixtures[0].home_score == 134
        assert fixtures[1].fixture_id == "1001234"
        assert fixtures[1].home_team == "Boston Celtics"
        assert fixtures[1].status == "scheduled"
        assert fixtures[1].start_time.hour == 19
        assert fixtures[1].start_time.minute == 30

    def test_soccer_v2_multi_league(self):
        """Soccer v2 multi-league response → parsed fixtures from all leagues."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        data = {
            "matches_28_02_2026": {
                "league": [
                    {
                        "league_name": "English Premier League",
                        "match": [
                            {
                                "id": "500",
                                "date": "28.02.2026",
                                "time": "15:00",
                                "status": "NS",
                                "home": {"id": "10", "name": "Arsenal"},
                                "away": {"id": "11", "name": "Chelsea"},
                            },
                        ]
                    },
                    {
                        "league_name": "La Liga",
                        "match": [
                            {
                                "id": "501",
                                "date": "28.02.2026",
                                "time": "21:00",
                                "status": "NS",
                                "home": {"id": "20", "name": "Real Madrid"},
                                "away": {"id": "21", "name": "Barcelona"},
                            },
                        ]
                    },
                ]
            }
        }
        fixtures = service._parse_fixtures(data, "soccer")
        assert len(fixtures) == 2
        assert fixtures[0].home_team == "Arsenal"
        assert fixtures[1].home_team == "Real Madrid"

    def test_empty_match_list(self):
        """Season schedule with no matches returns empty list."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        data = {
            "scores": {
                "tournament": {
                    "league": "NFL",
                    "match": []
                }
            }
        }
        fixtures = service._parse_fixtures(data, "nfl")
        assert fixtures == []

    def test_malformed_items_skipped(self):
        """Non-dict items in the match list are skipped gracefully."""
        from app.services.statpal_api import StatPalAPIService
        service = StatPalAPIService.__new__(StatPalAPIService)
        data = {
            "scores": {
                "tournament": {
                    "match": [
                        "not_a_dict",
                        None,
                        {
                            "id": "1",
                            "date": "27.02.2026",
                            "time": "19:00",
                            "status": "NS",
                            "home": {"id": "1", "name": "Team A"},
                            "away": {"id": "2", "name": "Team B"},
                        },
                    ]
                }
            }
        }
        fixtures = service._parse_fixtures(data, "nba")
        assert len(fixtures) == 1
        assert fixtures[0].home_team == "Team A"


# =============================================================================
# Schedule endpoint mapping
# =============================================================================

class TestScheduleEndpoints:
    """Tests for _SCHEDULE_ENDPOINTS mapping."""

    def test_major_sports_use_season_schedule(self):
        from app.services.statpal_api import StatPalAPIService
        for sport in ("nba", "nfl", "nhl", "mlb"):
            assert StatPalAPIService._SCHEDULE_ENDPOINTS[sport] == "season-schedule", \
                f"{sport} should use season-schedule"

    def test_soccer_uses_matches_daily(self):
        from app.services.statpal_api import StatPalAPIService
        assert StatPalAPIService._SCHEDULE_ENDPOINTS["soccer"] == "matches/daily"

    def test_golf_uses_schedule(self):
        from app.services.statpal_api import StatPalAPIService
        assert StatPalAPIService._SCHEDULE_ENDPOINTS["golf"] == "schedule"
        assert StatPalAPIService._SCHEDULE_ENDPOINTS["pga"] == "schedule"

    def test_f1_uses_schedule(self):
        from app.services.statpal_api import StatPalAPIService
        assert StatPalAPIService._SCHEDULE_ENDPOINTS["f1"] == "schedule"

    def test_cricket_uses_upcoming_schedule(self):
        from app.services.statpal_api import StatPalAPIService
        assert StatPalAPIService._SCHEDULE_ENDPOINTS["cricket"] == "upcoming-schedule"

    def test_unknown_sport_defaults_to_season_schedule(self):
        """Unknown sports fall back to season-schedule via dict.get()."""
        from app.services.statpal_api import StatPalAPIService
        assert StatPalAPIService._SCHEDULE_ENDPOINTS.get("esports", "season-schedule") == "season-schedule"


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

    @pytest.mark.asyncio
    async def test_livescore_sync_writes_raw_status_to_event_period(self, monkeypatch):
        import app.services.statpal_api as statpal_api
        import app.tasks.statpal_sync as statpal_sync
        from app.services.statpal_api import StatPalFixture

        class FakeEvent:
            id = 10
            sport_id = 1
            home_team_name = "Boston Celtics"
            away_team_name = "Los Angeles Lakers"
            status = "live"
            period = None
            home_score = 88
            away_score = 85
            statpal_fixture_id = None
            win_probability_sources = None

        class FakeSportRow:
            key = "basketball_nba"
            id = 1

        class FakeResult:
            def __init__(self, *, rows=None, scalars=None, first=None):
                self._rows = rows or []
                self._scalars = scalars or []
                self._first = first
                self._scalar_mode = False

            def all(self):
                return self._scalars if self._scalar_mode else self._rows

            def scalars(self):
                self._scalar_mode = True
                return self

            def first(self):
                return self._first

        class FakeSession:
            def __init__(self, event):
                self.event = event
                self.execute_calls = 0
                self.added = []

            async def execute(self, _stmt):
                self.execute_calls += 1
                if self.execute_calls == 1:
                    return FakeResult(rows=[FakeSportRow()])
                if self.execute_calls == 2:
                    return FakeResult(scalars=[self.event])
                return FakeResult(first=None)

            def add(self, obj):
                self.added.append(obj)

        class FakeSessionContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeStatPalService:
            async def get_live_scores(self, sport):
                assert sport == "nba"
                return [
                    StatPalFixture(
                        fixture_id="SP1",
                        home_team="Boston Celtics",
                        away_team="Los Angeles Lakers",
                        status="live",
                        raw_status="Q3",
                        home_score=90,
                        away_score=87,
                    )
                ]

            async def close(self):
                pass

        event = FakeEvent()
        session = FakeSession(event)
        monkeypatch.setattr(statpal_api, "is_available", lambda: True)
        monkeypatch.setattr(statpal_api, "StatPalAPIService", FakeStatPalService)
        monkeypatch.setattr(
            statpal_sync,
            "get_task_session",
            lambda: FakeSessionContext(session),
        )

        result = await statpal_sync._sync_statpal_livescores()

        assert event.period == "Q3"
        assert event.home_score == 90
        assert event.away_score == 87
        assert result["events_updated"] == 1
        assert result["score_snapshots_created"] == 1


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
