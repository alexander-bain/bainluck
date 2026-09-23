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
        n = _extend_win_prob_history_to_live_edge(
            wph, meta, is_live=True, now=NOW, speaking_sources=["stat_model"]
        )
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
        _extend_win_prob_history_to_live_edge(
            a, {}, is_live=True, now=NOW, speaking_sources=["s"]
        )
        _extend_win_prob_history_to_live_edge(
            b, {}, is_live=True, now=NOW + timedelta(seconds=35), speaking_sources=["s"]
        )
        assert b["s"][-1]["timestamp"] > a["s"][-1]["timestamp"]

    def test_no_op_when_not_live(self):
        wph = {"stat_model": _series("2026-06-15T20:13:00+00:00")}
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=False, now=NOW, speaking_sources=["stat_model"]
        )
        assert n == 0
        assert len(wph["stat_model"]) == 2

    def test_no_op_when_edge_is_fresh(self):
        # Last real point already within a poll of now → no synthetic point.
        fresh = (NOW - timedelta(seconds=10)).isoformat()
        wph = {"stat_model": _series(fresh)}
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=True, now=NOW, speaking_sources=["stat_model"]
        )
        assert n == 0
        assert len(wph["stat_model"]) == 2

    def test_empty_series_skipped(self):
        wph = {"stat_model": []}
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=True, now=NOW, speaking_sources=["stat_model"]
        )
        assert n == 0

    def test_naive_timestamp_handled(self):
        wph = {"polymarket": _series("2026-06-15T19:56:00")}  # no tz
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=True, now=NOW, speaking_sources=["polymarket"]
        )
        assert n == 1


class TestOnlyASourceTheHeroCountsIsCarriedForward:
    """#6863 — the chart edge asks the hero's own gate.

    The specimen: `/events/15316643` (Gibson v Anisimova, live, read 07:28Z
    2026-09-23). Hero `home_win_probability: null`, badge "No price"; the served
    history's last point was the request's own wall-clock instant carrying a
    Polymarket 0.495 last actually observed at 04:26Z. The page declined to
    price and the chart asserted anyway.
    """

    def test_the_specimen_a_silent_source_is_not_carried_to_now(self):
        # Hero counts nothing -> "No price" -> the chart may not plant a now-point.
        wph = {"polymarket": _series("2026-06-15T17:26:00+00:00", home=0.495)}
        meta = {"polymarket": {"snapshot_count": 2}}
        n = _extend_win_prob_history_to_live_edge(
            wph, meta, is_live=True, now=NOW, speaking_sources=[]
        )
        assert n == 0
        # The real observations are untouched — this withholds an assertion, it
        # does not delete traded history (the harm #5898 declined to do).
        assert len(wph["polymarket"]) == 2
        assert wph["polymarket"][-1]["timestamp"] == "2026-06-15T17:26:00+00:00"
        assert not any(p.get("live_edge") for p in wph["polymarket"])
        assert meta["polymarket"]["snapshot_count"] == 2

    def test_only_the_unspoken_source_is_withheld(self):
        # The discriminating case: one source speaking, one not, same payload.
        # A gate that skipped the whole call, or none of it, passes neither arm.
        wph = {
            "kalshi": _series("2026-06-15T20:13:00+00:00", home=0.61),
            "polymarket": _series("2026-06-15T17:26:00+00:00", home=0.495),
        }
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=True, now=NOW, speaking_sources=["kalshi"]
        )
        assert n == 1
        assert wph["kalshi"][-1]["live_edge"] is True
        assert len(wph["kalshi"]) == 3
        assert len(wph["polymarket"]) == 2
        assert not any(p.get("live_edge") for p in wph["polymarket"])

    def test_a_folded_event_fails_open(self):
        # None = "cannot say" (the hero may rest on a sibling row's reading this
        # endpoint never loads). Fail OPEN: pre-#6863 behaviour, every series
        # extends. An empty set is NOT the same statement as None.
        wph = {"polymarket": _series("2026-06-15T17:26:00+00:00", home=0.495)}
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=True, now=NOW, speaking_sources=None
        )
        assert n == 1
        assert wph["polymarket"][-1]["live_edge"] is True

    def test_the_gate_is_not_satisfied_by_a_substring_or_a_sibling_name(self):
        # `poly` must not clear `polymarket`, and a different source speaking is
        # not this one speaking.
        wph = {"polymarket": _series("2026-06-15T17:26:00+00:00", home=0.495)}
        n = _extend_win_prob_history_to_live_edge(
            wph, {}, is_live=True, now=NOW, speaking_sources=["poly", "kalshi"]
        )
        assert n == 0
        assert len(wph["polymarket"]) == 2

    def test_speaking_sources_is_required_so_a_call_site_cannot_forget_it(self):
        # The fail-open default is the trap this signature refuses to offer: a
        # new call site must decide, and a half-wired fix raises rather than
        # silently serving the defect.
        import pytest

        wph = {"polymarket": _series("2026-06-15T17:26:00+00:00")}
        with pytest.raises(TypeError):
            _extend_win_prob_history_to_live_edge(wph, {}, is_live=True, now=NOW)
