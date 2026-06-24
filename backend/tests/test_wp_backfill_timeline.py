"""#922: the ESPN win-prob backfill must spread synthetic points across the real
game window, never past the game end / now (the chart 'stale tail' bug).

Regression for `_backfill_espn_win_probability`: the old `commence + i*30s`
stamping assumed a fixed 30s cadence and overran long games by hours — late-game
points (≈100% in a blowout) landed in the future, drawing a flat 100% tail.
"""

from datetime import datetime, timedelta, timezone

from app.tasks.espn_sync import (
    _wp_backfill_snap_time,
    _WP_BACKFILL_DURATION_HOURS,
)


COMMENCE = datetime(2026, 6, 24, 17, 10, tzinfo=timezone.utc)


class TestWpBackfillSnapTime:
    def test_no_point_is_stamped_in_the_future(self):
        # Reproduce the Cubs–Mets case: ~800 WP points, game commenced 17:10,
        # backfill runs at 20:24 (game already complete). The OLD code stamped
        # the last point at commence + 800*30s = +6.6h = 23:50 (future).
        now = COMMENCE + timedelta(hours=3, minutes=14)  # 20:24, ~real end
        total = 800
        for i in range(total):
            ts = _wp_backfill_snap_time(COMMENCE, i, total, "baseball_mlb", now)
            assert ts <= now, f"point {i} stamped in the future: {ts}"
            assert ts >= COMMENCE

    def test_timeline_is_monotonic_and_spans_the_window(self):
        now = COMMENCE + timedelta(hours=6)  # ran well after the game
        total = 400
        times = [
            _wp_backfill_snap_time(COMMENCE, i, total, "baseball_mlb", now)
            for i in range(total)
        ]
        assert times == sorted(times)  # monotonic non-decreasing
        # Last point lands at the realistic baseball end (commence + 3.5h),
        # NOT now+ (no stale tail extending to/ past the present).
        cap = _WP_BACKFILL_DURATION_HOURS["baseball"]
        assert times[-1] == COMMENCE + timedelta(hours=cap)

    def test_recent_game_clamps_to_now_not_full_window(self):
        # Game commenced 1h ago, backfill runs now → window can't exceed now.
        now = COMMENCE + timedelta(hours=1)
        ts_last = _wp_backfill_snap_time(COMMENCE, 199, 200, "basketball_nba", now)
        assert ts_last <= now

    def test_missing_commence_returns_now(self):
        now = COMMENCE + timedelta(hours=2)
        assert _wp_backfill_snap_time(None, 5, 100, "baseball_mlb", now) == now

    def test_single_point_sits_at_commence(self):
        now = COMMENCE + timedelta(hours=5)
        assert _wp_backfill_snap_time(COMMENCE, 0, 1, "soccer_epl", now) == COMMENCE

    def test_unknown_sport_uses_default_duration(self):
        now = COMMENCE + timedelta(hours=10)
        ts_last = _wp_backfill_snap_time(COMMENCE, 99, 100, "quidditch_x", now)
        assert ts_last == COMMENCE + timedelta(hours=3.0)  # default
