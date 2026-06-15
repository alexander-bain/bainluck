"""Live win-prob chart freeze fix (#920 / Queue #50).

`_extend_win_prob_history_to_live_edge` carries each win-prob series forward to
`now` on a live game so the chart's right edge tracks the live clock instead of
freezing at the last value-change (the snapshot dedup only emits a row on a
probability change).
"""

from datetime import datetime, timezone, timedelta

from app.routes.events import _extend_win_prob_history_to_live_edge

NOW = datetime(2026, 6, 15, 20, 30, 0, tzinfo=timezone.utc)


def _series(last_ts_iso, home=0.99):
    return [
        {"timestamp": "2026-06-15T20:00:00+00:00", "home_probability": 0.9,
         "away_probability": 0.1, "game_state": {"period": "T1"}},
        {"timestamp": last_ts_iso, "home_probability": home,
         "away_probability": round(1 - home, 4), "game_state": {"period": "T7"}},
    ]


class TestLiveEdge:
    def test_stale_live_series_gets_now_point(self):
        wph = {"stat_model": _series("2026-06-15T20:13:00+00:00")}
        meta = {"stat_model": {"snapshot_count": 2}}
        n = _extend_win_prob_history_to_live_edge(wph, meta, is_live=True, now=NOW)
        assert n == 1
        last = wph["stat_model"][-1]
        assert last["timestamp"] == NOW.isoformat()
        assert last["live_edge"] is True
        # carries the last known value forward
        assert last["home_probability"] == 0.99
        assert meta["stat_model"]["snapshot_count"] == 3

    def test_advances_across_two_calls(self):
        # Each refetch rebuilds from DB (real points) + one fresh now-point, so the
        # right edge advances across a 35s window — the verify criterion.
        base = _series("2026-06-15T20:13:00+00:00")
        a = {"s": [dict(p) for p in base]}
        b = {"s": [dict(p) for p in base]}
        _extend_win_prob_history_to_live_edge(a, {}, is_live=True, now=NOW)
        _extend_win_prob_history_to_live_edge(b, {}, is_live=True, now=NOW + timedelta(seconds=35))
        assert b["s"][-1]["timestamp"] > a["s"][-1]["timestamp"]

    def test_no_op_when_not_live(self):
        wph = {"stat_model": _series("2026-06-15T20:13:00+00:00")}
        n = _extend_win_prob_history_to_live_edge(wph, {}, is_live=False, now=NOW)
        assert n == 0
        assert len(wph["stat_model"]) == 2

    def test_no_op_when_edge_is_fresh(self):
        # Last real point already within a poll of now → no synthetic point.
        fresh = (NOW - timedelta(seconds=10)).isoformat()
        wph = {"stat_model": _series(fresh)}
        n = _extend_win_prob_history_to_live_edge(wph, {}, is_live=True, now=NOW)
        assert n == 0
        assert len(wph["stat_model"]) == 2

    def test_empty_series_skipped(self):
        wph = {"stat_model": []}
        n = _extend_win_prob_history_to_live_edge(wph, {}, is_live=True, now=NOW)
        assert n == 0

    def test_naive_timestamp_handled(self):
        wph = {"polymarket": _series("2026-06-15T19:56:00")}  # no tz
        n = _extend_win_prob_history_to_live_edge(wph, {}, is_live=True, now=NOW)
        assert n == 1
