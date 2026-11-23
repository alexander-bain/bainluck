"""Tests for sanitized User-Agent attribution on slow-request logs/events (#13350)."""

from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import latency as latency_mw
from app.utils.latency_stats import (
    build_slow_event,
    parse_slow_event,
    sanitize_user_agent,
)


def test_sanitize_user_agent_strips_controls_collapses_spaces_and_bounds():
    assert sanitize_user_agent(None) == ""
    assert sanitize_user_agent("   ") == ""
    assert sanitize_user_agent("Bot/1.0\r\nFake-Header: x\t\tfoo") == "Bot/1.0 Fake-Header: x foo"
    assert len(sanitize_user_agent("x" * 300)) == 160


def test_build_slow_event_emits_ua_only_when_present():
    without = parse_slow_event(
        build_slow_event(
            timestamp=1.0,
            path="/api/feed",
            duration_ms=6000.0,
            cache_bucket="none",
        )
    )
    assert without is not None and "ua" not in without

    with_ua = parse_slow_event(
        build_slow_event(
            timestamp=1.0,
            path="/api/futures/{market_id}",
            duration_ms=7000.0,
            cache_bucket="none",
            user_agent="GPTBot/1.0\n(+https://example.com)",
        )
    )
    assert with_ua is not None
    assert with_ua["ua"] == "GPTBot/1.0 (+https://example.com)"


def _scripted_time(values):
    class _ScriptedTime:
        def __init__(self, seq):
            self._it = iter(seq)

        def __getattr__(self, name):
            return getattr(time, name)

        def perf_counter(self):
            return next(self._it)

    return _ScriptedTime(values)


def test_request_timing_logs_ua_on_slow_and_moderate_requests(monkeypatch, caplog):
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "time", _scripted_time([0.0, 1.2, 0.0, 0.65, 0.0, 0.1]))

    client = TestClient(main_mod.app)
    with caplog.at_level(logging.INFO, logger=main_mod.logger.name):
        r1 = client.get("/", headers={"User-Agent": "TestCrawler/2.1\r\ninject"})
        r2 = client.get("/", headers={"User-Agent": ""})
        r3 = client.get("/", headers={"User-Agent": "FastClient/1.0"})

    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200
    slow_logs = [rec.getMessage() for rec in caplog.records if "SLOW " in rec.getMessage()]
    moderate_logs = [rec.getMessage() for rec in caplog.records if "MODERATE " in rec.getMessage()]
    assert len(slow_logs) == 1 and "ua=TestCrawler/2.1 inject" in slow_logs[0]
    assert len(moderate_logs) == 1 and "ua=-" in moderate_logs[0]


def test_latency_middleware_logs_and_records_user_agent(monkeypatch, caplog):
    class _FakePipe:
        def __init__(self, sink):
            self.sink = sink
            self.calls = []

        def lpush(self, key, member):
            self.calls.append(("lpush", key, member))

        def ltrim(self, key, start, stop):
            self.calls.append(("ltrim", key, start, stop))

        def expire(self, key, ttl):
            self.calls.append(("expire", key, ttl))

        def execute(self):
            self.sink.extend(self.calls)
            return [1, True, True]

    class _FakeRedis:
        def __init__(self, sink):
            self.sink = sink

        def pipeline(self, transaction=False):
            return _FakePipe(self.sink)

    sink = []
    monkeypatch.setattr(latency_mw, "_get_redis", lambda: _FakeRedis(sink))
    monkeypatch.setattr(latency_mw, "SLOW_EVENT_MS", 5.0)
    monkeypatch.setattr(latency_mw, "_should_sample", lambda *_a, **_k: False)
    monkeypatch.setattr(latency_mw, "time", _scripted_time([0.0, 5.2]))

    app = FastAPI()
    app.add_middleware(latency_mw.LatencyMiddleware)

    @app.get("/api/slow-probe")
    async def _slow_probe():
        return {"ok": True}

    with caplog.at_level(logging.WARNING, logger=latency_mw.logger.name):
        resp = TestClient(app).get(
            "/api/slow-probe", headers={"User-Agent": "Bytespider/1.0"}
        )
    assert resp.status_code == 200
    warnings = [r.getMessage() for r in caplog.records if "Slow request:" in r.getMessage()]
    assert len(warnings) == 1 and "ua=Bytespider/1.0" in warnings[0]

    pushes = [json.loads(c[2]) for c in sink if c[0] == "lpush"]
    assert len(pushes) == 1
    assert pushes[0]["ua"] == "Bytespider/1.0"
