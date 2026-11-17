"""The NFL week latency gate uses its normal reader and request-local clocks."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

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
        "published_read", "header", "event_cards", "event_rows", "references", "percentiles", "teams", "reference_wait",
        "bookmaker_odds", "recent_lines", "folded_numbers", "venue_settlement", "pregame",
        "market_descriptors", "market_cards", "market_rows", "withheld_prices", "render", "cache_lookup", "total",
    } <= cold_fields.keys()
    assert cold_fields["basis"] == "overlapping_wall_ms"
    assert len(cold.headers["X-Container-Timing"]) < 1024
    assert all(float(value) >= 0 for name, value in cold_fields.items() if name not in {"basis"})

    hit = await read(db, debug_timing=True)
    assert hit.body == cold.body
    assert hit.headers["X-Feed-Cache"] == "hit"
    assert set(timing_fields(hit)) == {"published_read", "cache_lookup", "total", "basis"}

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
    statements = list(db.statements)
    db.statements.clear()
    traced = await read(db, debug_timing=True)
    assert db.statements == statements

    assert traced.body == route._render(ordinary)
    assert json.loads(traced.body)["related_summary"] == {"count": 11, "unclassified_count": 11}
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


async def test_timings_do_not_force_an_extra_pool_checkout(monkeypatch):
    clock = [0.0]
    operations = []

    class ReferenceSession:
        async def connection(self):
            pytest.fail("timing must not acquire a connection")

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
    assert operations == ["percentiles", "teams"]
    assert timings == pytest.approx({"percentiles": 20, "teams": 10, "references": 30})

    operations.clear()
    await route._read_event_card_references(["team"])
    assert operations == ["percentiles", "teams"]


async def test_reference_wait_measures_the_part_after_primary_reads(monkeypatch):
    clock = [1.0]
    monkeypatch.setattr(route, "perf_counter", lambda: clock[0])
    db = session()

    async def references():
        await asyncio.sleep(0)
        clock[0] += 0.025
        return {}, {}

    timings = {}
    token = route._stage_timings.set(timings)
    try:
        cards, _ = await route._assemble_event_cards(
            db, db.events, references=asyncio.create_task(references())
        )
    finally:
        route._stage_timings.reset(token)

    assert cards
    assert timings["reference_wait"] == pytest.approx(25)


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
        "published_read", "render", "total", "basis",
    }
    assert route._stage_timings.get() is None


async def test_background_rebuild_never_mutates_the_response_timings(monkeypatch):
    await read(session(), debug_timing=True)
    entry = next(iter(route._local_entries.values()))
    contexts = []

    async def published(*args):
        contexts.append(route._stage_timings.get())
        with route._time_stage("background_read"):
            return SimpleNamespace(state="published", slug="nfl-2026-week-5", revision=1)

    async def build(*args, **kwargs):
        contexts.append(route._stage_timings.get())
        with route._time_stage("background_build"):
            return entry

    monkeypatch.setattr(route, "read_published", published)
    monkeypatch.setattr(route, "_build_entry", build)
    timings = {"total": 5.0}
    token = route._stage_timings.set(timings)
    _, future = request_cache.begin_build("isolated-background")
    try:
        await route._refresh_in_background(
            "nfl-2026-week-5", True, "isolated-background", future, 1, True
        )
        assert route._stage_timings.get() is timings
    finally:
        route._stage_timings.reset(token)

    assert contexts == [None, None]
    assert timings == {"total": 5.0}
    assert future.done()


async def test_continuation_keeps_the_same_page_and_skips_event_hydration():
    app = FastAPI()

    async def db():
        yield session()

    app.dependency_overrides[route.get_db] = db
    app.include_router(route.router, prefix="/api/containers")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/api/containers/nfl-2026-week-5")
        next_url = first.json()["page"]["next_url"]
        ordinary = await client.get(next_url)
        traced = await client.get(next_url + "&debug_timing=true")

    assert ordinary.status_code == traced.status_code == 200
    assert ordinary.content == traced.content
    assert "event_rows" not in timing_fields(traced)
    assert {"market_descriptors", "market_rows", "render"} <= timing_fields(traced).keys()
    assert "X-Container-Timing" not in ordinary.headers
