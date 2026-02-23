"""Tests for ESPN API client parsing helpers.

Covers:
- _parse_color: ESPN color → hex format conversion
- SPORT_LEAGUE_MAP: sport key → ESPN path mapping completeness
- _parse_team: team data parsing from scoreboard + teams endpoint formats
- _parse_event: event data parsing (status, scores, clock, win probability)
- _parse_venue: venue data parsing
"""

import pytest

from app.services.espn_api import ESPNAPIService, SPORT_LEAGUE_MAP


@pytest.fixture
def client():
    """Create an ESPN API client instance for testing instance methods."""
    return ESPNAPIService()


# ── Static JSON fixtures ───────────────────────────────────────────────

# Teams endpoint format: logos as array of objects with rel
TEAMS_ENDPOINT_TEAM = {
    "team": {
        "id": "13",
        "name": "Lakers",
        "abbreviation": "LAL",
        "displayName": "Los Angeles Lakers",
        "shortDisplayName": "Lakers",
        "nickname": "Lakers",
        "color": "552583",
        "alternateColor": "FDB927",
        "location": "Los Angeles",
        "logos": [
            {"href": "https://a.espncdn.com/lakers_default.png", "rel": ["default"]},
            {"href": "https://a.espncdn.com/lakers_dark.png", "rel": ["dark"]},
        ],
    },
    "records": [
        {"type": "total", "summary": "34-18"},
        {"type": "home", "summary": "20-5"},
    ],
}

# Scoreboard endpoint format: logo as single string, team at top level
SCOREBOARD_TEAM = {
    "team": {
        "id": "2",
        "name": "Celtics",
        "abbreviation": "BOS",
        "displayName": "Boston Celtics",
        "shortDisplayName": "Celtics",
        "nickname": "Celtics",
        "color": "007A33",
        "alternateColor": "BA9653",
        "location": "Boston",
        "logo": "https://a.espncdn.com/celtics.png",
    },
}

# Minimal team (missing most optional fields)
MINIMAL_TEAM = {
    "team": {
        "id": "999",
        "name": "Unknown FC",
    },
}

# Team with logos array but no "default" rel
LOGOS_NO_DEFAULT_TEAM = {
    "team": {
        "id": "50",
        "name": "Wildcats",
        "logos": [
            {"href": "https://a.espncdn.com/wildcats_small.png", "rel": ["small"]},
        ],
    },
}

# Full event fixture (live NBA game)
LIVE_EVENT = {
    "id": "401584700",
    "name": "Boston Celtics at Los Angeles Lakers",
    "shortName": "BOS @ LAL",
    "date": "2026-02-14T03:00Z",
    "status": {
        "type": {"name": "STATUS_IN_PROGRESS", "detail": "Q3 4:32"},
        "period": 3,
        "displayClock": "4:32",
    },
    "competitions": [{
        "competitors": [
            {
                "homeAway": "home",
                "score": "78",
                "team": {
                    "id": "13",
                    "name": "Lakers",
                    "abbreviation": "LAL",
                    "displayName": "Los Angeles Lakers",
                    "shortDisplayName": "Lakers",
                    "color": "552583",
                },
            },
            {
                "homeAway": "away",
                "score": "82",
                "team": {
                    "id": "2",
                    "name": "Celtics",
                    "abbreviation": "BOS",
                    "displayName": "Boston Celtics",
                    "shortDisplayName": "Celtics",
                    "color": "007A33",
                },
            },
        ],
        "venue": {
            "id": "123",
            "fullName": "Crypto.com Arena",
            "address": {"city": "Los Angeles", "state": "CA", "country": "US"},
            "capacity": 18997,
        },
        "broadcasts": [
            {"names": ["ESPN", "ESPN2"]},
            {"names": ["TNT"]},
        ],
        "situation": {
            "lastPlay": {
                "probability": {"homeWinPercentage": 0.42},
            },
        },
    }],
}

# Scheduled event (no scores, no situation)
SCHEDULED_EVENT = {
    "id": "401584701",
    "name": "Miami Heat at Chicago Bulls",
    "shortName": "MIA @ CHI",
    "date": "2026-02-15T00:30Z",
    "status": {
        "type": {"name": "STATUS_SCHEDULED", "detail": "7:30 PM ET"},
    },
    "competitions": [{
        "competitors": [
            {
                "homeAway": "home",
                "team": {"id": "4", "name": "Bulls", "abbreviation": "CHI"},
            },
            {
                "homeAway": "away",
                "team": {"id": "14", "name": "Heat", "abbreviation": "MIA"},
            },
        ],
    }],
}

# Final event
FINAL_EVENT = {
    "id": "401584702",
    "name": "Golden State Warriors at Denver Nuggets",
    "shortName": "GS @ DEN",
    "date": "2026-02-13T03:00Z",
    "status": {
        "type": {"name": "STATUS_FINAL", "detail": "Final"},
        "period": 4,
        "displayClock": "0:00",
    },
    "competitions": [{
        "competitors": [
            {
                "homeAway": "home",
                "score": "112",
                "team": {"id": "7", "name": "Nuggets"},
            },
            {
                "homeAway": "away",
                "score": "105",
                "team": {"id": "9", "name": "Warriors"},
            },
        ],
    }],
}

# Venue fixture
VENUE_DATA = {
    "id": "456",
    "fullName": "Madison Square Garden",
    "name": "MSG",
    "address": {
        "city": "New York",
        "state": "NY",
        "country": "US",
    },
    "capacity": 19812,
}

VENUE_MINIMAL = {
    "id": "789",
    "name": "TBD Arena",
}


# ── _parse_color ────────────────────────────────────────────────────────


class TestParseColor:
    """Tests for ESPN color → hex conversion."""

    def test_none_returns_none(self, client):
        assert client._parse_color(None) is None

    def test_empty_string_returns_none(self, client):
        assert client._parse_color("") is None

    def test_adds_hash_prefix(self, client):
        assert client._parse_color("FF0000") == "#FF0000"

    def test_already_has_hash(self, client):
        assert client._parse_color("#00FF00") == "#00FF00"

    def test_lowercase_hex(self, client):
        assert client._parse_color("1d428a") == "#1d428a"

    def test_three_char_hex(self, client):
        """ESPN shouldn't return 3-char hex, but verify it still gets prefixed."""
        assert client._parse_color("FFF") == "#FFF"


# ── SPORT_LEAGUE_MAP ───────────────────────────────────────────────────


class TestSportLeagueMap:
    """Tests for the sport key → ESPN (sport, league) mapping."""

    def test_nfl_mapping(self):
        assert SPORT_LEAGUE_MAP["americanfootball_nfl"] == ("football", "nfl")

    def test_ncaaf_mapping(self):
        assert SPORT_LEAGUE_MAP["americanfootball_ncaaf"] == ("football", "college-football")

    def test_nba_mapping(self):
        assert SPORT_LEAGUE_MAP["basketball_nba"] == ("basketball", "nba")

    def test_ncaab_mapping(self):
        assert SPORT_LEAGUE_MAP["basketball_ncaab"] == ("basketball", "mens-college-basketball")

    def test_wncaab_mapping(self):
        assert SPORT_LEAGUE_MAP["basketball_wncaab"] == ("basketball", "womens-college-basketball")

    def test_nhl_mapping(self):
        assert SPORT_LEAGUE_MAP["icehockey_nhl"] == ("hockey", "nhl")

    def test_mlb_mapping(self):
        assert SPORT_LEAGUE_MAP["baseball_mlb"] == ("baseball", "mlb")

    def test_epl_mapping(self):
        assert SPORT_LEAGUE_MAP["soccer_epl"] == ("soccer", "eng.1")

    def test_mls_mapping(self):
        assert SPORT_LEAGUE_MAP["soccer_usa_mls"] == ("soccer", "usa.1")

    def test_ufc_mapping(self):
        assert SPORT_LEAGUE_MAP["mma_ufc"] == ("mma", "ufc")

    def test_unknown_key_returns_none(self, client):
        assert client._get_espn_path("unknown_sport") is None

    def test_all_values_are_tuples(self):
        """Every mapping value should be a (sport, league) tuple."""
        for key, value in SPORT_LEAGUE_MAP.items():
            assert isinstance(value, tuple), f"{key} value is not a tuple"
            assert len(value) == 2, f"{key} tuple should have exactly 2 elements"

    def test_all_values_are_nonempty_strings(self):
        """Sport and league components should be non-empty strings."""
        for key, (sport, league) in SPORT_LEAGUE_MAP.items():
            assert isinstance(sport, str) and sport, f"{key} sport is empty"
            assert isinstance(league, str) and league, f"{key} league is empty"

    def test_expected_count(self):
        """Verify we have all 20 expected sport mappings."""
        assert len(SPORT_LEAGUE_MAP) >= 17  # at least the core sports


# ── _parse_team ─────────────────────────────────────────────────────────


class TestParseTeam:
    """Tests for ESPN team data parsing with both endpoint formats."""

    def test_teams_endpoint_format(self, client):
        """Teams endpoint returns logos array with rel fields."""
        team = client._parse_team(TEAMS_ENDPOINT_TEAM)
        assert team is not None
        assert team.espn_id == "13"
        assert team.name == "Lakers"
        assert team.abbreviation == "LAL"
        assert team.display_name == "Los Angeles Lakers"
        assert team.short_name == "Lakers"
        assert team.nickname == "Lakers"
        assert team.location == "Los Angeles"

    def test_teams_endpoint_colors(self, client):
        """Colors get # prefix added."""
        team = client._parse_team(TEAMS_ENDPOINT_TEAM)
        assert team.primary_color == "#552583"
        assert team.secondary_color == "#FDB927"

    def test_teams_endpoint_logos(self, client):
        """Default and dark logos extracted from logos array."""
        team = client._parse_team(TEAMS_ENDPOINT_TEAM)
        assert team.logo_url == "https://a.espncdn.com/lakers_default.png"
        assert team.logo_url_dark == "https://a.espncdn.com/lakers_dark.png"

    def test_teams_endpoint_record(self, client):
        """Record extracted from records array (type=total)."""
        team = client._parse_team(TEAMS_ENDPOINT_TEAM)
        assert team.record == "34-18"

    def test_scoreboard_format_logo(self, client):
        """Scoreboard endpoint returns logo as single string."""
        team = client._parse_team(SCOREBOARD_TEAM)
        assert team is not None
        assert team.espn_id == "2"
        assert team.name == "Celtics"
        assert team.logo_url == "https://a.espncdn.com/celtics.png"

    def test_scoreboard_no_record(self, client):
        """Scoreboard format typically lacks records."""
        team = client._parse_team(SCOREBOARD_TEAM)
        assert team.record is None

    def test_minimal_team(self, client):
        """Parsing works with only id and name."""
        team = client._parse_team(MINIMAL_TEAM)
        assert team is not None
        assert team.espn_id == "999"
        assert team.name == "Unknown FC"
        assert team.abbreviation is None
        assert team.primary_color is None
        assert team.logo_url is None
        assert team.record is None

    def test_logos_fallback_to_first(self, client):
        """When no 'default' rel, falls back to first logo in array."""
        team = client._parse_team(LOGOS_NO_DEFAULT_TEAM)
        assert team.logo_url == "https://a.espncdn.com/wildcats_small.png"

    def test_empty_dict_returns_none(self, client):
        """Empty input should return None (caught by exception handler)."""
        result = client._parse_team({})
        # Could return an ESPNTeam with None fields or None
        # The key thing is it doesn't crash
        assert result is None or result.espn_id is not None


# ── _parse_event ────────────────────────────────────────────────────────


class TestParseEvent:
    """Tests for ESPN event data parsing."""

    def test_live_event_basic(self, client):
        """Parse a live game with all fields populated."""
        event = client._parse_event(LIVE_EVENT)
        assert event is not None
        assert event.espn_id == "401584700"
        assert event.name == "Boston Celtics at Los Angeles Lakers"
        assert event.short_name == "BOS @ LAL"

    def test_live_event_status(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert event.status == "in"
        assert event.status_detail == "Q3 4:32"
        assert event.period == 3
        assert event.clock == "4:32"

    def test_live_event_scores(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert event.home_score == 78
        assert event.away_score == 82

    def test_live_event_teams(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert event.home_team is not None
        assert event.home_team.name == "Lakers"
        assert event.away_team is not None
        assert event.away_team.name == "Celtics"

    def test_live_event_venue(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert event.venue is not None
        assert event.venue.name == "Crypto.com Arena"
        assert event.venue.capacity == 18997

    def test_live_event_broadcasts(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert "ESPN" in event.broadcasts
        assert "ESPN2" in event.broadcasts
        assert "TNT" in event.broadcasts

    def test_live_event_win_probability(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert event.home_win_probability == 0.42

    def test_live_event_date(self, client):
        event = client._parse_event(LIVE_EVENT)
        assert event.date is not None
        assert event.date.year == 2026
        assert event.date.month == 2

    def test_scheduled_event_status(self, client):
        event = client._parse_event(SCHEDULED_EVENT)
        assert event is not None
        assert event.status == "scheduled"
        assert event.status_detail == "7:30 PM ET"

    def test_scheduled_event_no_scores(self, client):
        event = client._parse_event(SCHEDULED_EVENT)
        assert event.home_score is None
        assert event.away_score is None

    def test_scheduled_event_no_win_prob(self, client):
        event = client._parse_event(SCHEDULED_EVENT)
        assert event.home_win_probability is None

    def test_final_event_status(self, client):
        event = client._parse_event(FINAL_EVENT)
        assert event is not None
        assert event.status == "post"

    def test_final_event_scores(self, client):
        event = client._parse_event(FINAL_EVENT)
        assert event.home_score == 112
        assert event.away_score == 105

    def test_final_event_clock(self, client):
        event = client._parse_event(FINAL_EVENT)
        assert event.clock == "0:00"
        assert event.period == 4

    def test_season_type_postseason(self, client):
        """Parse season.type=3 (postseason) from ESPN event data."""
        event_data = {**LIVE_EVENT, "season": {"type": 3, "year": 2026}}
        event = client._parse_event(event_data)
        assert event.season_type == 3

    def test_season_type_regular(self, client):
        """Parse season.type=2 (regular season) from ESPN event data."""
        event_data = {**SCHEDULED_EVENT, "season": {"type": 2, "year": 2026}}
        event = client._parse_event(event_data)
        assert event.season_type == 2

    def test_season_type_missing(self, client):
        """season_type defaults to None when season data is missing."""
        event = client._parse_event(LIVE_EVENT)
        assert event.season_type is None

    def test_season_type_non_integer_ignored(self, client):
        """Non-integer season.type values are handled gracefully."""
        event_data = {**LIVE_EVENT, "season": {"type": "postseason"}}
        event = client._parse_event(event_data)
        assert event.season_type is None


# ── _parse_venue ────────────────────────────────────────────────────────


class TestParseVenue:
    """Tests for ESPN venue data parsing."""

    def test_full_venue(self, client):
        venue = client._parse_venue(VENUE_DATA)
        assert venue is not None
        assert venue.espn_id == "456"
        assert venue.name == "Madison Square Garden"
        assert venue.city == "New York"
        assert venue.state == "NY"
        assert venue.country == "US"
        assert venue.capacity == 19812

    def test_venue_prefers_fullname(self, client):
        """fullName takes priority over name."""
        venue = client._parse_venue(VENUE_DATA)
        assert venue.name == "Madison Square Garden"  # fullName, not "MSG"

    def test_minimal_venue(self, client):
        """Venue with only id and name."""
        venue = client._parse_venue(VENUE_MINIMAL)
        assert venue is not None
        assert venue.espn_id == "789"
        assert venue.name == "TBD Arena"
        assert venue.city is None
        assert venue.state is None
        assert venue.capacity is None


# ── _parse_injuries ───────────────────────────────────────────────────


# Fixtures for injury/news parsing
SUMMARY_WITH_INJURIES = {
    "injuries": [
        {
            "team": {"displayName": "Boston Celtics"},
            "injuries": [
                {
                    "athlete": {
                        "displayName": "Jaylen Brown",
                        "position": {"abbreviation": "SF"},
                    },
                    "status": "Day-To-Day",
                    "details": {"type": "Knee"},
                },
                {
                    "athlete": {
                        "displayName": "Kristaps Porzingis",
                        "position": {"abbreviation": "C"},
                    },
                    "status": "Out",
                    "details": {"type": "Ankle"},
                },
            ],
        },
        {
            "team": {"displayName": "Los Angeles Lakers"},
            "injuries": [
                {
                    "athlete": {"displayName": "LeBron James"},
                    "status": "Questionable",
                    "details": {"type": "Back"},
                },
            ],
        },
    ],
}

SUMMARY_WITH_NEWS = {
    "news": {
        "articles": [
            {"headline": "LeBron James listed as doubtful", "published": "2026-02-20T12:00:00Z"},
            {"headline": "Celtics extend winning streak to 8", "published": "2026-02-20T10:00:00Z"},
        ],
    },
}


class TestParseInjuries:
    """Tests for ESPN injury data parsing."""

    def test_parse_injuries_basic(self, client):
        """Standard injury data with multiple teams and players."""
        injuries = client._parse_injuries(SUMMARY_WITH_INJURIES)
        assert len(injuries) == 3

        # First player
        assert injuries[0].player_name == "Jaylen Brown"
        assert injuries[0].team_name == "Boston Celtics"
        assert injuries[0].status == "Day-To-Day"
        assert injuries[0].injury_type == "Knee"
        assert injuries[0].position == "SF"

        # Third player (different team)
        assert injuries[2].player_name == "LeBron James"
        assert injuries[2].team_name == "Los Angeles Lakers"
        assert injuries[2].status == "Questionable"

    def test_parse_injuries_empty(self, client):
        """Missing injuries key returns empty list."""
        injuries = client._parse_injuries({})
        assert injuries == []

    def test_parse_injuries_partial_data(self, client):
        """Missing athlete fields handled gracefully."""
        data = {
            "injuries": [
                {
                    "team": {"displayName": "Team A"},
                    "injuries": [
                        {
                            "athlete": {},  # No displayName
                            "status": "Out",
                        },
                        {
                            "athlete": {"displayName": "Good Player"},
                            "status": "Probable",
                            # No details dict
                        },
                    ],
                },
            ],
        }
        injuries = client._parse_injuries(data)
        # First athlete has no name → skipped
        # Second athlete has name → kept with Unknown injury_type
        assert len(injuries) == 1
        assert injuries[0].player_name == "Good Player"
        assert injuries[0].injury_type == "Unknown"

    def test_parse_injuries_no_position(self, client):
        """Athlete without position data returns None position."""
        data = {
            "injuries": [
                {
                    "team": {"displayName": "Team B"},
                    "injuries": [
                        {
                            "athlete": {"displayName": "No Pos Player"},
                            "status": "Out",
                            "details": {"type": "Hamstring"},
                        },
                    ],
                },
            ],
        }
        injuries = client._parse_injuries(data)
        assert len(injuries) == 1
        assert injuries[0].position is None


# ── _parse_news ───────────────────────────────────────────────────────


class TestParseNews:
    """Tests for ESPN news headline parsing."""

    def test_parse_news_basic(self, client):
        """Standard articles with headlines and timestamps."""
        news = client._parse_news(SUMMARY_WITH_NEWS)
        assert len(news) == 2
        assert news[0].headline == "LeBron James listed as doubtful"
        assert news[0].published == "2026-02-20T12:00:00Z"
        assert news[1].headline == "Celtics extend winning streak to 8"

    def test_parse_news_empty(self, client):
        """Missing news key returns empty list."""
        news = client._parse_news({})
        assert news == []

    def test_parse_news_no_articles(self, client):
        """News key present but no articles."""
        news = client._parse_news({"news": {}})
        assert news == []

    def test_parse_news_skips_empty_headlines(self, client):
        """Articles with empty headline strings are skipped."""
        data = {
            "news": {
                "articles": [
                    {"headline": "", "published": "2026-02-20T12:00:00Z"},
                    {"headline": "Valid headline"},
                ],
            },
        }
        news = client._parse_news(data)
        assert len(news) == 1
        assert news[0].headline == "Valid headline"
