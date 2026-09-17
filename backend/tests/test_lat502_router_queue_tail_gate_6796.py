"""Guards for the reader-observed gate on the slow-request tail (#6796).

The specimen, production, 2026-09-17: `GET /api/events/15313771` took **16.4 s**
client-side and carried `wall=62.5;db=28.1;app=34.4;q=5;router=16005.1`. The
request sat 16 s in the Heroku router queue and was then served in 62 ms.

Every tail gate read `duration_ms` — the handler clock — so that request was
recorded nowhere: not in the ring, not in the `Slow request:` warning, and in
`/latency-stats` it is a 62 ms request. The consequence is not just a missing
row. `request_timing`'s header comment states a HALT condition ("router queue
> 30 % ⇒ the bottleneck is web-dyno capacity") and `_summarize_layers` computes
the share to evaluate it, but the only events it could ever be computed over
were the ones the handler clock selected — which are, by construction, the ones
the router did NOT dominate. The rail could refute "the router is cheap" only
with evidence it refused to collect.

So these guards pin the GATE and the LEGIBILITY of what it admits, and — as the
rest of this rail's tests do — never a wall-clock duration.
"""

from __future__ import annotations

import time

import pytest

from app.utils.latency_stats import (
    ROUTER_DOMINATED_SHARE,
    build_slow_event,
    parse_slow_event,
    summarize_slow_events,
)
from app.utils.request_timing import REQUEST_START_HEADER, build_split


def _split(*, wall_ms: float, router_ms: float | None) -> dict:
    """The real `build_split`, never a hand-written dict.

    A fixture that spells the split out itself would keep passing after
    `build_split` stopped emitting `edge_ms`, which is the one field the gate
    reads.
    """
    return build_split(wall_ms=wall_ms, db=None, router_ms=router_ms)


class TestTheGateFiresOnTheWaitAReaderExperienced:
    """The fix itself, driven end to end through Starlette."""

    @staticmethod
    def _client(monkeypatch, *, handler_ms: float = 0.0):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.middleware import latency as mod

        recorded: list[dict] = []

        async def _capture(normalized, duration_ms, cache_bucket, response, rss_mb, split):
            recorded.append(
                {
                    "path": normalized,
                    "ms": duration_ms,
                    "split": split,
                }
            )

        monkeypatch.setattr(mod, "_record_slow_event", _capture)
        # The sampled zset is a different rail and must not reach Redis here.
        monkeypatch.setattr(mod, "_should_sample", lambda *_a, **_k: False)

        app = FastAPI()
        app.add_middleware(mod.LatencyMiddleware)

        @app.get("/api/probe")
        async def _probe():  # pragma: no cover - exercised through the client
            if handler_ms:
                time.sleep(handler_ms / 1000.0)
            return {"ok": True}

        return TestClient(app), recorded

    @staticmethod
    def _queued_stamp(seconds_ago: float) -> str:
        return str(int((time.time() - seconds_ago) * 1000))

    def test_a_long_router_queue_in_front_of_a_fast_handler_is_recorded(
        self, monkeypatch
    ):
        # The #6796 specimen's shape: the handler is trivial, the person waited.
        client, recorded = self._client(monkeypatch)
        resp = client.get(
            "/api/probe", headers={REQUEST_START_HEADER: self._queued_stamp(16.0)}
        )

        assert resp.status_code == 200
        assert len(recorded) == 1, (
            "a request whose reader waited 16 s must reach the tail ring even "
            "though the handler was fast — that is the whole of #6796"
        )
        # The RECORDED duration is still the handler clock: `ms` must not change
        # meaning under consumers that have been reading it since #1459.
        assert recorded[0]["ms"] < 5000
        assert recorded[0]["split"]["router_queue_ms"] > 5000

    def test_the_same_fast_request_without_a_router_stamp_is_not_recorded(
        self, monkeypatch
    ):
        # Fail-closed: with no usable `X-Request-Start` the gate is exactly the
        # handler clock it always was. Without this, the change would widen the
        # ring on every fast request the moment `edge_ms` defaulted to a number.
        client, recorded = self._client(monkeypatch)
        resp = client.get("/api/probe")

        assert resp.status_code == 200
        assert recorded == []

    def test_an_unusable_router_stamp_does_not_admit_a_fast_request(
        self, monkeypatch
    ):
        # `router_queue_ms` returns None — meaning UNUSABLE — for a stamp that
        # is unparseable or implausibly old. None must not read as a large
        # queue any more than it reads as a zero one.
        client, recorded = self._client(monkeypatch)
        for stamp in ("garbage", self._queued_stamp(4000.0)):
            resp = client.get("/api/probe", headers={REQUEST_START_HEADER: stamp})
            assert resp.status_code == 200
        assert recorded == []

    def test_a_slow_handler_is_still_recorded_when_the_router_was_quick(
        self, monkeypatch
    ):
        # The pre-existing behaviour, pinned so the new term cannot displace it.
        from app.middleware import latency as mod

        monkeypatch.setattr(mod, "SLOW_EVENT_MS", 5.0)
        client, recorded = self._client(monkeypatch, handler_ms=25)
        resp = client.get(
            "/api/probe", headers={REQUEST_START_HEADER: self._queued_stamp(0.01)}
        )

        assert resp.status_code == 200
        assert len(recorded) == 1


class TestTheRecordSaysHowLongSomebodyWaited:
    def test_edge_ms_is_persisted_beside_the_handler_clock(self):
        raw = build_slow_event(
            timestamp=1_700_000_000.0,
            path="/api/events/{event_id}",
            duration_ms=62.5,
            cache_bucket="none",
            split=_split(wall_ms=62.5, router_ms=16005.1),
        )
        rec = parse_slow_event(raw)

        assert rec is not None
        assert rec["ms"] == 62.5
        assert rec["router_queue_ms"] == 16005.1
        # Without this field the ring records the #6796 specimen as a 62.5 ms
        # event and every reader concludes the window was quiet.
        assert rec["edge_ms"] == pytest.approx(16067.6)

    def test_an_unusable_router_term_writes_edge_as_null_not_a_number(self):
        rec = parse_slow_event(
            build_slow_event(
                timestamp=1_700_000_000.0,
                path="/api/feed",
                duration_ms=9000.0,
                cache_bucket="miss",
                split=_split(wall_ms=9000.0, router_ms=None),
            )
        )

        assert rec is not None
        assert "edge_ms" in rec and rec["edge_ms"] is None, (
            "gotcha #53: 'could not measure the wait' and 'the wait was the "
            "handler time' are different claims"
        )


class TestTheRollupMakesTheCapacityQuestionAnswerable:
    @staticmethod
    def _rec(*, ms, router, t=1_700_000_000.0):
        return parse_slow_event(
            build_slow_event(
                timestamp=t,
                path="/api/probe",
                duration_ms=ms,
                cache_bucket="none",
                split=_split(wall_ms=ms, router_ms=router),
            )
        )

    def test_max_edge_ms_reports_the_wait_that_max_ms_hides(self):
        summary = summarize_slow_events([self._rec(ms=62.5, router=16005.1)])

        assert summary["max_ms"] == 62.5
        assert summary["max_edge_ms"] == pytest.approx(16067.6)

    def test_a_router_dominated_event_is_counted(self):
        summary = summarize_slow_events(
            [
                self._rec(ms=62.5, router=16005.1),  # 99.6 % router
                self._rec(ms=9000.0, router=3.0),  # 0.03 % router
            ]
        )

        assert summary["n_router_dominated"] == 1
        # And the layer rollup now has an event that can actually answer the
        # HALT question, which it never could while the gate selected on the
        # handler clock alone.
        assert summary["by_layer"]["dominant"] == "router_queue_ms"

    def test_the_share_boundary_is_inclusive_at_the_documented_threshold(self):
        # 30 % of a 1,000 ms wait, exactly. An exclusive `>` here would make the
        # stated threshold unreachable at its own value.
        router = ROUTER_DOMINATED_SHARE * 1000.0
        summary = summarize_slow_events(
            [self._rec(ms=1000.0 - router, router=router)]
        )

        assert summary["n_router_dominated"] == 1

    def test_an_unusable_router_term_is_not_counted_as_dominated(self):
        summary = summarize_slow_events([self._rec(ms=9000.0, router=None)])

        assert summary["n_router_dominated"] == 0
        assert summary["max_edge_ms"] is None

    def test_records_written_before_this_field_shipped_are_not_read_as_zeros(self):
        legacy = parse_slow_event(
            build_slow_event(
                timestamp=1_700_000_000.0,
                path="/api/feed",
                duration_ms=8513.6,
                cache_bucket="miss",
            )
        )
        summary = summarize_slow_events([legacy])

        assert "edge_ms" not in legacy
        assert summary["max_edge_ms"] is None
        assert summary["n_router_dominated"] == 0

    def test_the_empty_ring_still_carries_both_keys(self):
        summary = summarize_slow_events([])

        assert summary["max_edge_ms"] is None
        assert summary["n_router_dominated"] == 0
