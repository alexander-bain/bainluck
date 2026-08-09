"""Guards for the slow-event forensic ring (#1459 / LAT-P011).

The defect being prevented is a MEASUREMENT defect, so the guards are about
whether a tail event survives to be read, not about how fast anything is.
Deliberately no wall-clock assertions — LAT-P005's lesson is that a guard which
goes red on a correct change is pinning the wrong thing, and a timing assertion
in CI is the canonical example.

Context: three consecutive latency queues hand-fired spaced benchmarks to catch
`/api/feed` spikes and measured 9%, 10%, then 0.3% over a full clock hour. At
0.3% the analysis needs thousands of requests to collect eight tail events. The
ring exists so the tail is a read.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from app.utils.latency_stats import (
    build_slow_event,
    dominant_stage,
    parse_slow_event,
    summarize_slow_events,
)


class TestDominantStage:
    """The attribution the rail could not previously give."""

    def test_picks_the_most_expensive_top_level_stage(self):
        stages = "futures=3941.24,concepts=3543.46,events=932.51"
        assert dominant_stage(stages) == ("futures", 3941.24)

    def test_sub_stages_never_win_over_their_own_parent(self):
        # `futures.market_load` is counted INSIDE `futures`. Letting a dotted
        # child compete both double-counts and can crown the child over the
        # parent that contains it — the attribution would name the wrong thing.
        stages = "concepts=900.0,futures=1000.0,futures.market_load=999.0"
        assert dominant_stage(stages) == ("futures", 1000.0)

    def test_a_child_larger_than_every_parent_is_still_not_reported(self):
        stages = "concepts=10.0,futures.canonical_counts=5000.0"
        assert dominant_stage(stages) == ("concepts", 10.0)

    @pytest.mark.parametrize("bad", ["", None, "garbage", "futures=", "=123", "futures=abc"])
    def test_unparseable_is_none_not_a_fabricated_stage(self, bad):
        assert dominant_stage(bad) is None

    @pytest.mark.parametrize("bad", ["futures=nan", "futures=inf", "futures=-inf"])
    def test_non_finite_is_refused(self, bad):
        # Mirrors parse_sample_member's r329-B1 guard: a NaN makes ordering
        # undefined and an inf raises at render time, so it must never enter.
        assert dominant_stage(bad) is None


class TestBuildAndParseRoundTrip:
    def test_round_trip_preserves_the_forensic_fields(self):
        raw = build_slow_event(
            timestamp=1_700_000_000.5,
            path="/api/feed",
            duration_ms=8513.57,
            cache_bucket="miss",
            stages="futures=3941.24,concepts=3543.46",
            rss_mb=512.0,
        )
        rec = parse_slow_event(raw)
        assert rec is not None
        assert rec["path"] == "/api/feed"
        assert rec["ms"] == 8513.6
        assert rec["cache"] == "miss"
        # The whole point: an absolute timestamp AND stage attribution, the two
        # things LAT-P009 could not recover after the fact.
        assert rec["t"] == 1_700_000_000.5
        assert rec["top_stage"] == "futures"
        assert rec["top_stage_ms"] == 3941.2

    def test_stage_string_is_bounded(self):
        rec = parse_slow_event(
            build_slow_event(
                timestamp=1.0, path="/api/feed", duration_ms=9000.0,
                cache_bucket="miss", stages="s=1," * 5000,
            )
        )
        assert len(rec["stages"]) <= 400

    def test_path_is_bounded(self):
        rec = parse_slow_event(
            build_slow_event(
                timestamp=1.0, path="/api/" + "x" * 5000,
                duration_ms=9000.0, cache_bucket="none",
            )
        )
        assert len(rec["path"]) <= 120

    def test_missing_stages_records_no_attribution_rather_than_a_guess(self):
        rec = parse_slow_event(
            build_slow_event(
                timestamp=1.0, path="/api/events/{event_id}",
                duration_ms=6000.0, cache_bucket="none",
            )
        )
        assert "top_stage" not in rec

    def test_build_refuses_non_finite_latency(self):
        with pytest.raises(ValueError):
            build_slow_event(
                timestamp=1.0, path="/api/feed", duration_ms=math.inf,
                cache_bucket="miss",
            )

    @pytest.mark.parametrize(
        "bad", ["", "not json", "[1,2,3]", '"a string"', '{"no_ms": 1}', '{"ms": "abc"}']
    )
    def test_corrupt_entries_drop_out_rather_than_render_as_rows(self, bad):
        assert parse_slow_event(bad) is None

    def test_bytes_entries_parse(self):
        raw = build_slow_event(
            timestamp=1.0, path="/api/feed", duration_ms=6000.0, cache_bucket="miss"
        ).encode()
        assert parse_slow_event(raw) is not None


class TestSummarize:
    def test_groups_by_dominant_stage(self):
        events = [
            parse_slow_event(build_slow_event(
                timestamp=t, path="/api/feed", duration_ms=ms,
                cache_bucket="miss", stages=stages))
            for t, ms, stages in [
                (10.0, 6000.0, "concepts=5500,futures=200"),
                (20.0, 9000.0, "concepts=8000,futures=300"),
                (30.0, 7000.0, "futures=6500,concepts=100"),
            ]
        ]
        summary = summarize_slow_events(events)
        assert summary["n"] == 3
        assert summary["by_top_stage"]["concepts"]["n"] == 2
        assert summary["by_top_stage"]["concepts"]["max_ms"] == 9000.0
        assert summary["by_top_stage"]["futures"]["n"] == 1
        assert summary["oldest_ts"] == 10.0 and summary["newest_ts"] == 30.0
        assert summary["max_ms"] == 9000.0

    def test_unattributed_events_are_labelled_not_dropped(self):
        events = [parse_slow_event(build_slow_event(
            timestamp=1.0, path="/api/teams/{identifier}",
            duration_ms=6000.0, cache_bucket="none"))]
        assert summarize_slow_events(events)["by_top_stage"]["unattributed"]["n"] == 1

    def test_empty_is_zero_not_a_crash(self):
        summary = summarize_slow_events([])
        assert summary["n"] == 0 and summary["max_ms"] is None


class _FakePipe:
    def __init__(self, sink, fail=False):
        self.sink, self.calls, self._fail = sink, [], fail

    def lpush(self, key, member):
        self.calls.append(("lpush", key, member))

    def ltrim(self, key, start, stop):
        self.calls.append(("ltrim", key, start, stop))

    def expire(self, key, ttl):
        self.calls.append(("expire", key, ttl))

    def execute(self):
        if self._fail:
            raise RuntimeError("redis down")
        self.sink.extend(self.calls)
        return [1, True, True]


class _FakeRedis:
    def __init__(self, sink, fail=False):
        self.sink, self._fail = sink, fail

    def pipeline(self, transaction=False):
        return _FakePipe(self.sink, self._fail)


class _FakeResponse:
    def __init__(self, headers=None):
        self.headers = headers or {}


class TestMiddlewareRecording:
    """The ring must capture the tail, stay bounded, and never break a request."""

    def _record(self, monkeypatch, *, ms, headers=None, fail=False):
        from app.middleware import latency as mod

        sink = []
        monkeypatch.setattr(mod, "_get_redis", lambda: _FakeRedis(sink, fail))
        asyncio.run(mod._record_slow_event(
            "/api/feed", ms, "miss", _FakeResponse(headers), None,
        ))
        return sink, mod

    def test_a_tail_event_is_written_with_its_stage_breakdown(self, monkeypatch):
        sink, mod = self._record(
            monkeypatch, ms=8513.57,
            headers={"x-feed-stages": "futures=3941.24,concepts=3543.46"},
        )
        pushes = [c for c in sink if c[0] == "lpush"]
        assert len(pushes) == 1
        rec = json.loads(pushes[0][2])
        assert rec["ms"] == 8513.6
        assert rec["top_stage"] == "futures"
        assert pushes[0][1] == mod.SLOW_EVENT_KEY

    def test_the_ring_is_capped_so_it_cannot_grow_unbounded(self, monkeypatch):
        # Redis here is Premium-0 / 50 MB / allkeys-lru at ~62%: an unbounded
        # key evicts COLD keys regardless of TTL (r320 lost the grid-sentinel
        # verdict exactly that way).
        sink, mod = self._record(monkeypatch, ms=6000.0)
        trims = [c for c in sink if c[0] == "ltrim"]
        assert trims == [("ltrim", mod.SLOW_EVENT_KEY, 0, mod.SLOW_EVENT_MAX - 1)]
        assert [c for c in sink if c[0] == "expire"][0][2] == mod.SLOW_EVENT_TTL_SECONDS

    def test_a_dead_redis_never_propagates_out_of_the_recorder(self, monkeypatch):
        # Observability must never fail a user's request.
        sink, _ = self._record(monkeypatch, ms=9000.0, fail=True)
        assert sink == []

    def test_no_redis_client_is_survivable(self, monkeypatch):
        from app.middleware import latency as mod

        monkeypatch.setattr(mod, "_get_redis", lambda: None)
        asyncio.run(mod._record_slow_event("/api/feed", 9000.0, "miss", _FakeResponse(), None))

    def test_a_response_with_hostile_headers_is_survivable(self, monkeypatch):
        class _Boom:
            @property
            def headers(self):
                raise RuntimeError("no headers")

        from app.middleware import latency as mod
        sink = []
        monkeypatch.setattr(mod, "_get_redis", lambda: _FakeRedis(sink))
        asyncio.run(mod._record_slow_event("/api/feed", 9000.0, "miss", _Boom(), None))
        assert len([c for c in sink if c[0] == "lpush"]) == 1


class TestRecordingIsNotGatedBySampling:
    """The anti-recurrence guard, and the reason this is worth a test at all.

    `/api/feed` is always-sampled today, so putting the recorder after the
    sampling gate would look fine in production and silently discard 9 of every
    10 tail events on every OTHER endpoint — including `/api/events/typeahead`,
    whose 12.9 s p100 is on the record (ops r324). The ordering is the fix, so
    the ordering is what gets pinned.
    """

    def test_the_recorder_runs_before_the_sampling_gate(self):
        import inspect

        from app.middleware import latency as mod

        src = inspect.getsource(mod.LatencyMiddleware.dispatch)
        assert "_record_slow_event" in src and "_should_sample" in src
        assert src.index("_record_slow_event") < src.index("if not _should_sample"), (
            "the slow-event write must precede the sampling early-return, or "
            "1-in-N endpoints lose 9 of every 10 tail events"
        )

    def test_threshold_is_env_overridable_without_a_deploy(self):
        from app.middleware import latency as mod

        # A tail hunt needs to widen the net (e.g. to 3s) on a quiet night
        # without shipping code — 0.3% of requests crossed 5s in the LAT-P011
        # hour, and 13 crossed 3s.
        assert mod.SLOW_EVENT_MS == 5000.0
        assert mod.SLOW_EVENT_MAX == 500
