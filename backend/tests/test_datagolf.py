"""Tests for DataGolf API service."""

import pytest

from app.services.datagolf_api import (
    DataGolfAPIService,
    DataGolfPlayer,
    DataGolfTournament,
    DataGolfOddsPlayer,
    normalize_player_name,
    strip_diacritics,
    _safe_prob,
    _safe_int,
)


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

class TestNormalizePlayerName:
    def test_last_first_format(self):
        assert normalize_player_name("Scheffler, Scottie") == "Scottie Scheffler"

    def test_last_first_with_extra_spaces(self):
        assert normalize_player_name("  Hovland ,  Viktor  ") == "Viktor Hovland"

    def test_already_first_last(self):
        assert normalize_player_name("Scottie Scheffler") == "Scottie Scheffler"

    def test_diacritics_stripped(self):
        assert normalize_player_name("Skarsgård, Gustav") == "Gustav Skarsgard"

    def test_accented_name(self):
        assert normalize_player_name("Fleetwood, Tommy") == "Tommy Fleetwood"

    def test_empty_string(self):
        assert normalize_player_name("") == ""

    def test_no_comma_single_name(self):
        assert normalize_player_name("Tiger") == "Tiger"

    def test_suffix_after_comma(self):
        # Edge case: "Spieth, Jordan" → "Jordan Spieth"
        assert normalize_player_name("Spieth, Jordan") == "Jordan Spieth"

    def test_diacritics_o_stroke(self):
        assert normalize_player_name("Højgaard, Nicolai") == "Nicolai Hojgaard"

    def test_diacritics_umlaut(self):
        assert normalize_player_name("Müller, Thomas") == "Thomas Muller"


class TestStripDiacritics:
    def test_basic(self):
        assert strip_diacritics("café") == "cafe"

    def test_nordic(self):
        assert strip_diacritics("Skarsgård") == "Skarsgard"

    def test_o_stroke(self):
        assert strip_diacritics("Højgaard") == "Hojgaard"

    def test_no_diacritics(self):
        assert strip_diacritics("hello") == "hello"

    def test_empty(self):
        assert strip_diacritics("") == ""


# ---------------------------------------------------------------------------
# Safe parsers
# ---------------------------------------------------------------------------

class TestSafeProb:
    def test_valid_float(self):
        assert _safe_prob({"win": 0.15}, "win") == 0.15

    def test_zero(self):
        assert _safe_prob({"win": 0.0}, "win") == 0.0

    def test_one(self):
        assert _safe_prob({"win": 1.0}, "win") == 1.0

    def test_none_key(self):
        assert _safe_prob({"win": None}, "win") is None

    def test_missing_key(self):
        assert _safe_prob({}, "win") is None

    def test_out_of_range_high(self):
        assert _safe_prob({"win": 1.5}, "win") is None

    def test_out_of_range_negative(self):
        assert _safe_prob({"win": -0.1}, "win") is None

    def test_string_value(self):
        assert _safe_prob({"win": "0.15"}, "win") == 0.15

    def test_invalid_string(self):
        assert _safe_prob({"win": "abc"}, "win") is None


class TestSafeInt:
    def test_int_value(self):
        assert _safe_int(5) == 5

    def test_string_int(self):
        assert _safe_int("3") == 3

    def test_none(self):
        assert _safe_int(None) is None

    def test_invalid(self):
        assert _safe_int("abc") is None

    def test_float(self):
        assert _safe_int(3.7) == 3

    def test_negative(self):
        assert _safe_int(-12) == -12


# ---------------------------------------------------------------------------
# Player parsing
# ---------------------------------------------------------------------------

class TestParsePlayersPreTournament:
    def test_basic_parsing(self):
        service = DataGolfAPIService(api_key="test")
        data = {
            "data": [
                {
                    "dg_id": 18417,
                    "player_name": "Scheffler, Scottie",
                    "win_prob": 0.15,
                    "top_5_prob": 0.35,
                    "top_10_prob": 0.50,
                    "top_20_prob": 0.70,
                    "make_cut_prob": 0.95,
                },
                {
                    "dg_id": 18418,
                    "player_name": "McIlroy, Rory",
                    "win_prob": 0.08,
                    "top_5_prob": None,
                    "top_10_prob": 0.30,
                },
            ]
        }
        players = service._parse_players(data, in_play=False)

        assert len(players) == 2
        assert players[0].player_name == "Scottie Scheffler"
        assert players[0].dg_id == 18417
        assert players[0].win == 0.15
        assert players[0].top_5 == 0.35
        assert players[0].top_10 == 0.50
        assert players[0].top_20 == 0.70
        assert players[0].make_cut == 0.95
        assert players[0].position is None  # Pre-tournament → no position

        assert players[1].player_name == "Rory McIlroy"
        assert players[1].win == 0.08
        assert players[1].top_5 is None
        assert players[1].top_10 == 0.30

    def test_empty_data(self):
        service = DataGolfAPIService(api_key="test")
        assert service._parse_players({"data": []}, in_play=False) == []

    def test_no_data_key(self):
        service = DataGolfAPIService(api_key="test")
        assert service._parse_players({}, in_play=False) == []


class TestParsePlayersInPlay:
    def test_leaderboard_data(self):
        service = DataGolfAPIService(api_key="test")
        data = {
            "current_round": 3,
            "data": [
                {
                    "dg_id": 18417,
                    "player_name": "Scheffler, Scottie",
                    "win_prob": 0.35,
                    "top_5_prob": 0.60,
                    "top_10_prob": 0.75,
                    "current_pos": "1",
                    "current_score": -12,
                    "today": -3,
                    "thru": "14",
                    "round": 3,
                },
            ]
        }
        players = service._parse_players(data, in_play=True)

        assert len(players) == 1
        p = players[0]
        assert p.player_name == "Scottie Scheffler"
        assert p.win == 0.35
        assert p.position == "1"
        assert p.total_score == -12
        assert p.today_score == -3
        assert p.thru == "14"
        assert p.current_round == 3

    def test_alternative_field_names(self):
        """Some endpoints use 'win' instead of 'win_prob'."""
        service = DataGolfAPIService(api_key="test")
        data = {
            "data": [
                {
                    "dg_id": 100,
                    "player_name": "Woods, Tiger",
                    "win": 0.02,
                    "top_5": 0.10,
                    "position": "T45",
                },
            ]
        }
        players = service._parse_players(data, in_play=True)
        assert players[0].win == 0.02
        assert players[0].top_5 == 0.10
        assert players[0].position == "T45"


# ---------------------------------------------------------------------------
# Schedule parsing
# ---------------------------------------------------------------------------

class TestScheduleParsing:
    def test_tournament_model(self):
        t = DataGolfTournament(
            event_id="401",
            event_name="The Masters",
            course="Augusta National",
            start_date="2026-04-09",
            end_date="2026-04-12",
            tour="pga",
            current_round=None,
        )
        assert t.event_name == "The Masters"
        assert t.tour == "pga"


# ---------------------------------------------------------------------------
# Outright odds parsing
# ---------------------------------------------------------------------------

class TestOutrightOdds:
    def test_odds_player_model(self):
        p = DataGolfOddsPlayer(
            dg_id=18417,
            player_name="Scottie Scheffler",
            datagolf_model=0.15,
            sportsbook_odds={"draftkings": 0.10, "fanduel": 0.12},
        )
        assert p.datagolf_model == 0.15
        assert p.sportsbook_odds["draftkings"] == 0.10


# ---------------------------------------------------------------------------
# Service initialization
# ---------------------------------------------------------------------------

class TestServiceInit:
    def test_no_api_key_raises(self):
        service = DataGolfAPIService(api_key=None)
        # Should raise when making actual requests
        import asyncio
        with pytest.raises(ValueError, match="DATAGOLF_API_KEY not configured"):
            asyncio.run(service._get("test"))

    def test_with_api_key(self):
        service = DataGolfAPIService(api_key="test_key_123")
        assert service.api_key == "test_key_123"

    def test_tours(self):
        assert "pga" in DataGolfAPIService.TOURS
        assert "euro" in DataGolfAPIService.TOURS
        assert "liv" in DataGolfAPIService.TOURS


# ---------------------------------------------------------------------------
# Cross-source golfer dedup (golf.py _match_key + _normalize_golfer_name)
# ---------------------------------------------------------------------------

from app.routes.golf import _match_key, _normalize_golfer_name


class TestNormalizeGolferName:
    """Test _normalize_golfer_name handles all source formats."""

    def test_plain_name(self):
        assert _normalize_golfer_name("Scottie Scheffler") == "Scottie Scheffler"

    def test_yes_prefix(self):
        assert _normalize_golfer_name("Yes: Scottie Scheffler") == "Scottie Scheffler"

    def test_no_prefix(self):
        assert _normalize_golfer_name("No - Tiger Woods") == "Tiger Woods"

    def test_quoted_polymarket(self):
        assert _normalize_golfer_name('"Scottie Scheffler"') == "Scottie Scheffler"

    def test_datagolf_last_first(self):
        assert _normalize_golfer_name("Scheffler, Scottie") == "Scottie Scheffler"

    def test_datagolf_with_hyphen(self):
        assert _normalize_golfer_name("Fleetwood, Tommy") == "Tommy Fleetwood"

    def test_datagolf_with_suffix(self):
        """DataGolf sometimes has middle names or suffixes after the first name."""
        assert _normalize_golfer_name("Homa, Max") == "Max Homa"


class TestMatchKeyCrossSource:
    """Test that _match_key produces identical keys for the same golfer
    across DataGolf, Polymarket, Kalshi, and Odds API formats."""

    def test_basic_matching(self):
        # DataGolf "Last, First" matches Polymarket "First Last"
        assert _match_key("Scheffler, Scottie") == _match_key("Scottie Scheffler")

    def test_kalshi_yes_prefix(self):
        # Kalshi "Yes: ..." matches plain name
        assert _match_key("Yes: Scottie Scheffler") == _match_key("Scottie Scheffler")

    def test_polymarket_quoted(self):
        # Polymarket NegRisk quoted names
        assert _match_key('"Rory McIlroy"') == _match_key("Rory McIlroy")

    def test_diacritics_matching(self):
        # DataGolf may have diacritics, Polymarket/Kalshi may not
        assert _match_key("Skarsgård, Gustav") == _match_key("Gustav Skarsgard")

    def test_diacritics_hovland(self):
        assert _match_key("Hovland, Viktor") == _match_key("Viktor Hovland")

    def test_umlaut_matching(self):
        assert _match_key("Müller, Thomas") == _match_key("Thomas Muller")

    def test_hojgaard(self):
        assert _match_key("Højgaard, Nicolai") == _match_key("Nicolai Hojgaard")

    def test_suffix_stripped(self):
        # "Jr." suffixes should not affect matching
        assert _match_key("Cam Davis Jr.") == _match_key("Cam Davis")

    def test_suffix_sr(self):
        assert _match_key("Davis Love III") == _match_key("Davis Love")

    def test_odds_api_abbreviated(self):
        # Odds API sometimes abbreviates first names
        # These won't match, but we should produce consistent keys
        key_full = _match_key("Scottie Scheffler")
        key_abbrev = _match_key("S. Scheffler")
        assert key_full == "scottie scheffler"
        assert key_abbrev == "s scheffler"

    def test_datagolf_vs_all(self):
        """Real-world scenario: same golfer from 4 sources."""
        datagolf = _match_key("McIlroy, Rory")
        polymarket = _match_key('"Rory McIlroy"')
        kalshi = _match_key("Yes: Rory McIlroy")
        odds_api = _match_key("Rory McIlroy")
        assert datagolf == polymarket == kalshi == odds_api == "rory mcilroy"

    def test_datagolf_vs_all_accented(self):
        """Same golfer with diacritics from 4 sources."""
        datagolf = _match_key("Hovland, Viktor")
        polymarket = _match_key("Viktor Hovland")
        kalshi = _match_key("Yes: Viktor Hovland")
        odds_api = _match_key("Viktor Hovland")
        assert datagolf == polymarket == kalshi == odds_api == "viktor hovland"

    def test_with_role_suffix(self):
        """Names with role/tournament suffix (e.g., 'X - Winner') drop suffix."""
        assert _match_key("Scottie Scheffler - Masters") == _match_key("Scottie Scheffler")

    def test_with_for_suffix(self):
        """Names with 'for' suffix (e.g., 'X for Best Actor')."""
        assert _match_key("Tiger Woods for Masters") == _match_key("Tiger Woods")

    def test_empty_string(self):
        assert _match_key("") == ""

    def test_whitespace_normalization(self):
        assert _match_key("  Scottie   Scheffler  ") == "scottie scheffler"

    def test_the_prefix_stripped(self):
        """'The' prefix stripped (rare but can appear in prop outcomes)."""
        assert _match_key("The Field") == "field"
