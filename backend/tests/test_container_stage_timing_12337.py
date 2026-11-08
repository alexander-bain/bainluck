"""The NFL week latency gate uses its normal reader and request-local clocks."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

from app.routes import containers as route
from app.routes import events as event_route
from app.services import database
from app.utils import request_cache
from tests.test_container_compact_week_12337 import CompactSession, long_week
from tests.test_container_hydrated_reader_9636 import _Session
from tests.test_container_read_cache_9982 import _FakeRedis, _drain_background


@pytest.fixture(autouse=True)
async def enabled(monkeypatch):
    class ReferenceSession(_Session):
        async def connection(self):
            return object()

    @asynccontextmanager
    async def reference_session():
        yield ReferenceSession()

    redis = _FakeRedis()

    async def client():
        return redis

    monkeypatch.setattr(database, "async_session_maker", reference_session)
    monkeypatch.setattr(request_cache, "get_shared_async_redis", client)
    monkeypatch.setattr(event_route, "_ei_cache", {})
    monkeypatch.setattr(event_route, "_team_cache", {})
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    route._reset_read_cache_for_tests()
    request_cache._reset_inflight_for_tests()
    yield redis
    await _drain_background()
    route._reset_read_cache_for_tests()
    request_cache._reset_inflight_for_tests()


def session():
    hub, events, markets = long_week()
    return CompactSession(hub, events=events, markets=markets)


async def read(db, *, debug_timing=False):
    return await route.get_container(
        slug=db.hub.slug, include_children=True, compact=True,
        debug_timing=debug_timing, db=db,
    )


def timing_fields(response):
    return dict(
        field.split("=", 1)
        for field in response.headers["X-Container-Timing"].split(";")
    )


async def test_opt_in_cold_and_hit_headers_keep_the_normal_bytes():
    db = session()
    cold = await read(db, debug_timing=True)
    cold_fields = timing_fields(cold)

    assert cold.headers["X-Feed-Cache"] == "miss"
    assert {
        "published_read", "event_cards", "reference_checkout", "reference_reads",
        "linked_market_lookup", "market_cards", "render", "cache_store", "cache_lookup", "total",
    } <= cold_fields.keys()
    assert cold_fields["basis"] == "overlapping_wall_ms"
    assert cold_fields["shared_publish"] == "background"
    assert all(float(value) >= 0 for name, value in cold_fields.items() if name not in {"basis", "shared_publish"})

    hit = await read(db, debug_timing=True)
    assert hit.body == cold.body
    assert hit.headers["X-Feed-Cache"] == "hit"
    assert set(timing_fields(hit)) == {"published_read", "cache_lookup", "total", "basis", "shared_publish"}

    ordinary = await read(db)
    assert ordinary.body == cold.body
    assert "X-Container-Timing" not in ordinary.headers
    assert route._stage_timings.get() is None


async def test_shared_cache_stores_the_body_without_request_timings(enabled):
    cold = await read(session(), debug_timing=True)
    await _drain_background()
    route._reset_read_cache_for_tests()
    hit = await read(session(), debug_timing=True)

    assert hit.headers["X-Feed-Cache"] == "shared_hit"
    assert hit.body == cold.body
    assert "event_cards" not in timing_fields(hit)
    assert all(b"X-Container-Timing" not in value for value in enabled.store.values())


async def test_uncached_debug_response_matches_the_existing_serializer(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    db = session()
    ordinary = await read(db)
    traced = await read(db, debug_timing=True)

    assert traced.body == route._render(ordinary)
    assert json.loads(traced.body)["related_summary"] == {"count": 13, "unclassified_count": 11}
    assert "cache_store" not in timing_fields(traced)


async def test_http_boolean_flag_and_body_through_the_normal_route():
    app = FastAPI()

    async def db():
        yield session()

    app.dependency_overrides[route.get_db] = db
    app.include_router(route.router, prefix="/api/containers")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        traced = await client.get("/api/containers/nfl-2026-week-5?compact=true&debug_timing=1")
        ordinary = await client.get("/api/containers/nfl-2026-week-5?compact=true")

    assert traced.status_code == ordinary.status_code == 200
    assert traced.content == ordinary.content
    assert "published_read" in timing_fields(traced)
    assert "X-Container-Timing" not in ordinary.headers


async def test_reference_checkout_is_measured_before_its_readers(monkeypatch):
    clock = [0.0]
    operations = []

    class ReferenceSession:
        async def connection(self):
            operations.append("checkout")
            clock[0] += 0.03

    @asynccontextmanager
    async def references():
        yield ReferenceSession()

    async def percentiles(db):
        operations.append("percentiles")
        clock[0] += 0.02
        return {"nfl": 2}

    async def teams(db, names):
        operations.append("teams")
        clock[0] += 0.01
        return {"team": "snapshot"}

    monkeypatch.setattr(route, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(database, "async_session_maker", references)
    monkeypatch.setattr(event_route, "_load_gei_percentiles", percentiles)
    monkeypatch.setattr(event_route, "_build_team_lookup", teams)
    timings = {}
    token = route._stage_timings.set(timings)
    try:
        result = await route._read_event_card_references(["team"])
    finally:
        route._stage_timings.reset(token)

    assert result == ({"nfl": 2}, {"team": "snapshot"})
    assert operations == ["checkout", "percentiles", "teams"]
    assert timings == pytest.approx({"reference_checkout": 30, "reference_reads": 30})

    operations.clear()
    await route._read_event_card_references(["team"])
    assert operations == ["percentiles", "teams"]


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_error_and_cancellation_reset_request_timing(monkeypatch, failure):
    async def fail(*args):
        with route._time_stage("published_read"):
            raise failure("representative failed read")

    monkeypatch.setattr(route, "_get_container", fail)
    with pytest.raises(failure):
        await read(session(), debug_timing=True)
    assert route._stage_timings.get() is None


async def test_concurrent_requests_have_separate_accumulators(monkeypatch):
    active = []
    both_started = asyncio.Event()

    async def payload(*args):
        active.append(route._stage_timings.get())
        if len(active) == 2:
            both_started.set()
        await both_started.wait()
        with route._time_stage("published_read"):
            await asyncio.sleep(0)
        return {"state": "published"}

    monkeypatch.setattr(route, "_get_container", payload)
    first, second = await asyncio.gather(
        read(session(), debug_timing=True), read(session(), debug_timing=True)
    )

    assert active[0] is not active[1]
    assert set(timing_fields(first)) == set(timing_fields(second)) == {
        "published_read", "render", "total", "basis", "shared_publish",
    }
    assert route._stage_timings.get() is None
