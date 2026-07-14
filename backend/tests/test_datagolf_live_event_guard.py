"""#191: the DataGolf live poll must not blast one event's in-play board onto
every open market for the tour.

The in-play endpoint is per-TOUR and returns ONE event's leaderboard +
probabilities. Without an identity + future-date guard, `_poll_datagolf_live`
wrote that board to every open `datagolf:{tour}:%` market — putting a stale
winner's -17 round-4 leaderboard (Tom Kim @ 1.0 win prob) onto The Open
Championship's markets TWO DAYS before tee-off, and clobbering the hourly
pre-tournament poll's correct probs ~40s later on every cycle.

Two tests: (1) the pure event-match helper's substring logic, and (2) a
structural guard that the live poll skips future-dated + mismatched-event
markets (repo idiom for the large async poll functions — see
test_datagolf_future_resolution_guard.py).
"""

import importlib
import inspect

datagolf = importlib.import_module("app.tasks.datagolf")
_in_play_event_matches = datagolf._in_play_event_matches


def _src(fn_name: str) -> str:
    return inspect.getsource(getattr(datagolf, fn_name))


class TestInPlayEventMatches:
    def test_same_event_matches(self):
        assert _in_play_event_matches(
            "The Open Championship - Winner", "The Open Championship"
        )
        assert _in_play_event_matches(
            "The Open Championship - Top 10 Finish", "The Open Championship"
        )

    def test_different_event_does_not_match(self):
        # The real Tom Kim bug: a different in-play event's board onto The Open.
        assert not _in_play_event_matches(
            "The Open Championship - Winner", "Genesis Scottish Open"
        )
        assert not _in_play_event_matches(
            "NV5 Invitational - Winner", "Barbasol Championship"
        )

    def test_unknown_in_play_event_does_not_block(self):
        # When the in-play info lacks an event name we fall back to the
        # future-date guard at the call site — the helper must not block.
        assert _in_play_event_matches("The Open Championship - Winner", "")
        assert _in_play_event_matches("The Open Championship - Winner", None)

    def test_missing_market_name_does_not_crash(self):
        assert _in_play_event_matches(None, "The Open Championship")

    def test_substring_either_direction(self):
        # in-play name is a substring of the market event part, or vice versa.
        assert _in_play_event_matches("Genesis Scottish Open - Winner", "Scottish Open")
        assert _in_play_event_matches("Scottish Open - Winner", "Genesis Scottish Open")


class TestLivePollGuardStructural:
    def test_live_poll_uses_event_info(self):
        src = _src("_poll_datagolf_live")
        # Must fetch the in-play event name, not the bare player list.
        assert "get_in_play_with_info" in src
        assert "in_play_info" in src

    def test_live_poll_skips_future_dated_markets(self):
        src = _src("_poll_datagolf_live")
        assert "market.commence_time > now" in src
        assert "skipped_future" in src

    def test_live_poll_skips_event_mismatch(self):
        src = _src("_poll_datagolf_live")
        assert "_in_play_event_matches" in src
        assert "skipped_event_mismatch" in src

    def test_guard_references_issue(self):
        assert "#191" in _src("_in_play_event_matches")
