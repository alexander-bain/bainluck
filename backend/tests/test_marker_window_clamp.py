"""#922 follow-up: the game_state_backfill 'Final' marker time must be clamped
to now() so a future/out-of-window snapshot (e.g. a residual bad ESPN-WP-backfill
row) can't push the marker into the future and grow a chart stale tail.
"""

from datetime import datetime, timedelta, timezone

from app.tasks.game_state_backfill import _resolve_marker_window


START = datetime(2026, 6, 24, 17, 10, tzinfo=timezone.utc)
NOW = START + timedelta(hours=3, minutes=14)  # ~real game end / current time


class TestResolveMarkerWindow:
    def test_future_candidate_is_clamped_to_now(self):
        # A bad future-stamped snapshot (the #922 residual) must NOT become the
        # marker time — clamp to now.
        end_candidates = [
            START + timedelta(hours=3),          # real last point
            START + timedelta(hours=6, minutes=39),  # bad future point (23:49Z)
        ]
        end = _resolve_marker_window(end_candidates, START, NOW)
        assert end == NOW
        assert end <= NOW

    def test_normal_completed_game_uses_real_end(self):
        real_end = START + timedelta(hours=3)
        end = _resolve_marker_window([real_end], START, NOW)
        assert end == real_end  # below now → unchanged

    def test_no_candidates_returns_none(self):
        assert _resolve_marker_window([], START, NOW) is None

    def test_too_short_span_returns_none(self):
        # < 30 min after start → implausible, no marker.
        end = _resolve_marker_window([START + timedelta(minutes=20)], START, NOW)
        assert end is None

    def test_future_candidate_still_passes_min_span(self):
        # Even when the only candidate is future, after clamping to now the span
        # is still > 30 min, so a marker is written at now (not the future time).
        end = _resolve_marker_window([NOW + timedelta(hours=2)], START, NOW)
        assert end == NOW
