"""The game-state window guard (#1828).

Anchored to Alex's 2026-08-13 specimen: event 15192596, Red Sox @ Blue Jays,
first pitch 19:07 UTC, final 21:35 UTC — carrying 27 period markers and ~65
state-bearing snapshots from the PREVIOUS NIGHT'S game (2026-08-12T23:35 →
2026-08-13T01:37).

Every timestamp below is a literal from that production payload. Nothing here
is relative to the wall clock (gotcha #44): the fixture carries its own dates,
so the assertions cannot acquire an expiry.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.game_window import (
    MAX_GAME_DURATION,
    filter_state_bearing_rows,
    game_state_window,
    has_in_game_state,
    is_in_game_window,
)

# ── The real specimen ────────────────────────────────────────────────────────
COMMENCE = datetime(2026, 8, 13, 19, 7, 0, tzinfo=timezone.utc)
COMPLETED = datetime(2026, 8, 13, 21, 35, 43, 237161, tzinfo=timezone.utc)

# Verbatim from /api/events/15192596/history?hours=48 on 2026-08-13.
CONTAMINATED_ESPN_ROWS = [
    {"timestamp": "2026-08-12T23:34:11.283025+00:00", "period": "Bottom 2nd", "home_score": 1, "away_score": 0},
    {"timestamp": "2026-08-12T23:57:10.045249+00:00", "period": "Top 4th", "home_score": 1, "away_score": 0},
    {"timestamp": "2026-08-13T00:02:10.045308+00:00", "period": "Bottom 4th", "home_score": 1, "away_score": 0},
]
OWN_GAME_ESPN_ROWS = [
    {"timestamp": "2026-08-13T19:32:13.485083+00:00", "period": "Top 2nd", "home_score": 0, "away_score": 1},
    {"timestamp": "2026-08-13T19:37:13.917435+00:00", "period": "Bottom 2nd", "home_score": 0, "away_score": 1},
    {"timestamp": "2026-08-13T20:56:34.194418+00:00", "period": "Top 8th", "home_score": 0, "away_score": 5},
    {"timestamp": "2026-08-13T21:07:34.220311+00:00", "period": "Bottom 8th", "home_score": 0, "away_score": 5},
    {"timestamp": "2026-08-13T21:35:00+00:00", "period": "Final", "home_score": 0, "away_score": 7},
]


class TestGameStateWindow:
    def test_window_spans_first_pitch_to_completion_with_grace(self):
        lower, upper = game_state_window(COMMENCE, COMPLETED)
        assert lower == COMMENCE - timedelta(hours=1)
        assert upper == COMPLETED + timedelta(hours=1)

    def test_no_commence_time_means_no_window(self):
        # No first pitch => no claim to test => callers must filter nothing.
        assert game_state_window(None, COMPLETED) is None

    def test_live_game_without_completion_uses_duration_ceiling(self):
        lower, upper = game_state_window(COMMENCE, None)
        assert upper == COMMENCE + MAX_GAME_DURATION
        # The ceiling must still exclude the next night's game.
        assert upper < COMMENCE + timedelta(hours=20)

    def test_inverted_completed_at_falls_back_to_ceiling(self):
        # gotcha #46's corruption class: completed_at BEFORE commence_time.
        # It must not produce an upper bound below the lower bound.
        _, upper = game_state_window(COMMENCE, COMMENCE - timedelta(hours=3))
        assert upper == COMMENCE + MAX_GAME_DURATION

    def test_accepts_iso_strings_and_naive_datetimes(self):
        from_iso = game_state_window("2026-08-13T19:07:00+00:00", None)
        from_naive = game_state_window(COMMENCE.replace(tzinfo=None), None)
        assert from_iso == from_naive == game_state_window(COMMENCE, None)


class TestHasInGameState:
    @pytest.mark.parametrize(
        "row",
        [
            {"period": "Top 9th"},
            {"game_clock": "0:00"},
            {"game_state": {"period": "Bottom 3rd"}},
            {"game_state": {"inning": 4}},
        ],
    )
    def test_state_bearing_rows_are_recognised(self, row):
        assert has_in_game_state(row) is True

    @pytest.mark.parametrize(
        "row",
        [
            {"home_probability": 0.4011},                  # pre-game odds
            {"period": None},
            {"period": ""},
            {"period": "   "},
            {"game_state": None},
            {"game_state": {"period": None, "inning": None}},
            {"game_state": {"inning": 0}},                 # 0 = not started
            None,
            "not a row",
        ],
    )
    def test_rows_without_a_live_claim_are_not_state_bearing(self, row):
        assert has_in_game_state(row) is False


class TestFilterStateBearingRows:
    def test_drops_the_previous_nights_innings_and_keeps_its_own(self):
        window = game_state_window(COMMENCE, COMPLETED)
        rows = CONTAMINATED_ESPN_ROWS + OWN_GAME_ESPN_ROWS
        kept, dropped = filter_state_bearing_rows(rows, window)

        assert dropped == 3
        assert kept == OWN_GAME_ESPN_ROWS

    def test_the_final_row_survives(self):
        # The 21:35 'Final' row carries the true 7-0 score. Losing it is what
        # made the Game Segments total read 5 next to a hero reading 7.
        window = game_state_window(COMMENCE, COMPLETED)
        kept, _ = filter_state_bearing_rows(OWN_GAME_ESPN_ROWS, window)
        assert kept[-1]["period"] == "Final"
        assert kept[-1]["away_score"] == 7

    def test_pregame_odds_are_never_dropped_however_old(self):
        # The chart's "All" range is built from these. They carry no in-game
        # state, so the window has no jurisdiction over them.
        window = game_state_window(COMMENCE, COMPLETED)
        pregame = [
            {"timestamp": "2026-08-09T18:08:00+00:00", "home_probability": 0.3933},
            {"timestamp": "2026-08-01T00:00:00+00:00", "home_probability": 0.51},
        ]
        kept, dropped = filter_state_bearing_rows(pregame, window)
        assert dropped == 0
        assert kept == pregame

    def test_win_prob_shape_with_nested_game_state(self):
        window = game_state_window(COMMENCE, COMPLETED)
        rows = [
            {"timestamp": "2026-08-12T23:35:10.797383+00:00",
             "game_state": {"period": "Bottom 2nd"}, "home_probability": 0.4},
            {"timestamp": "2026-08-13T21:33:34.230595+00:00",
             "game_state": {"period": "End 9th"}, "home_probability": 0.001},
            # No game_state at all — a market source. Untouched.
            {"timestamp": "2026-08-12T20:41:19.310871+00:00",
             "game_state": None, "home_probability": 0.565},
        ]
        kept, dropped = filter_state_bearing_rows(rows, window)
        assert dropped == 1
        assert [r["timestamp"] for r in kept] == [
            "2026-08-13T21:33:34.230595+00:00",
            "2026-08-12T20:41:19.310871+00:00",
        ]

    def test_no_window_is_the_identity_function(self):
        rows = CONTAMINATED_ESPN_ROWS + OWN_GAME_ESPN_ROWS
        kept, dropped = filter_state_bearing_rows(rows, None)
        assert dropped == 0
        assert kept == rows

    def test_clean_data_is_untouched(self):
        # The monotonicity claim in the module docstring, asserted: on an event
        # with no contamination this filter changes nothing at all.
        window = game_state_window(COMMENCE, COMPLETED)
        kept, dropped = filter_state_bearing_rows(OWN_GAME_ESPN_ROWS, window)
        assert dropped == 0
        assert kept == OWN_GAME_ESPN_ROWS

    def test_unparseable_timestamp_is_not_convicted(self):
        window = game_state_window(COMMENCE, COMPLETED)
        rows = [{"timestamp": "not-a-date", "period": "Top 3rd"}]
        kept, dropped = filter_state_bearing_rows(rows, window)
        assert dropped == 0
        assert kept == rows


class TestIsInGameWindow:
    def test_absent_window_admits_everything(self):
        assert is_in_game_window("2026-01-01T00:00:00+00:00", None) is True

    def test_boundaries_are_inclusive(self):
        window = game_state_window(COMMENCE, COMPLETED)
        assert is_in_game_window(window[0], window) is True
        assert is_in_game_window(window[1], window) is True
        assert is_in_game_window(window[0] - timedelta(seconds=1), window) is False
        assert is_in_game_window(window[1] + timedelta(seconds=1), window) is False
