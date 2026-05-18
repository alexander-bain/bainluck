"""Extended tests for DataGolf API service.

Covers methods not in test_datagolf.py:
- _first_int: correctly handles zero (even par), multi-key fallback
"""

from app.services.datagolf_api import DataGolfAPIService, _first_int


class TestFirstInt:
    """_first_int correctly handles 0 (even par) unlike chaining with `or`."""

    def test_zero_is_valid(self):
        """0 (even par) must be returned, not treated as falsy."""
        assert _first_int({"current_score": 0}, "current_score") == 0

    def test_first_key_wins(self):
        d = {"a": 5, "b": 10}
        assert _first_int(d, "a", "b") == 5

    def test_skips_none_to_find_value(self):
        d = {"a": None, "b": 7}
        assert _first_int(d, "a", "b") == 7

    def test_skips_missing_key(self):
        d = {"b": 3}
        assert _first_int(d, "a", "b") == 3

    def test_all_none_returns_none(self):
        d = {"a": None, "b": None}
        assert _first_int(d, "a", "b") is None

    def test_all_missing_returns_none(self):
        assert _first_int({}, "a", "b", "c") is None

    def test_single_key(self):
        assert _first_int({"x": 42}, "x") == 42

    def test_string_int_converted(self):
        """String integers are safely parsed via _safe_int."""
        assert _first_int({"a": "15"}, "a") == 15

    def test_invalid_string_skipped(self):
        d = {"a": "not_a_number", "b": 3}
        assert _first_int(d, "a", "b") == 3

    def test_zero_preferred_over_later_key(self):
        """0 from first key should not fall through to second key."""
        d = {"a": 0, "b": 99}
        assert _first_int(d, "a", "b") == 0

    def test_negative_value(self):
        assert _first_int({"score": -5}, "score") == -5


class TestParsePlayersGuardrails:
    """Parser-level guardrails for DataGolf's loose endpoint payloads."""

    def test_invalid_probability_alias_falls_back_to_valid_value(self):
        service = DataGolfAPIService(api_key="test")
        data = {
            "data": [
                {
                    "dg_id": 18417,
                    "player_name": "Scheffler, Scottie",
                    "win_prob": "not-a-probability",
                    "win": "0.125",
                    "top_5_prob": 1.5,
                    "top_5": 0.4,
                    "top_10_prob": -0.1,
                    "top_10": "0.55",
                },
            ]
        }

        players = service._parse_players(data, in_play=False)

        assert len(players) == 1
        assert players[0].win == 0.125
        assert players[0].top_5 == 0.4
        assert players[0].top_10 == 0.55

    def test_in_play_even_par_scores_do_not_fall_through_to_later_fields(self):
        service = DataGolfAPIService(api_key="test")
        data = {
            "data": [
                {
                    "dg_id": 18417,
                    "player_name": "Scheffler, Scottie",
                    "current_score": 0,
                    "total": -4,
                    "today": "0",
                    "today_to_par": -2,
                    "thru": 18,
                },
            ]
        }

        players = service._parse_players(data, in_play=True)

        assert len(players) == 1
        assert players[0].total_score == 0
        assert players[0].today_score == 0
        assert players[0].thru == "18"

    def test_baseline_history_fit_payload_is_accepted_without_data_key(self):
        service = DataGolfAPIService(api_key="test")
        data = {
            "baseline_history_fit": [
                {
                    "dg_id": 100,
                    "player_name": "Hovland, Viktor",
                    "win_prob": 0.07,
                },
            ]
        }

        players = service._parse_players(data, in_play=False)

        assert len(players) == 1
        assert players[0].player_name == "Viktor Hovland"
        assert players[0].win == 0.07
