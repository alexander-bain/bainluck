"""Tests for futures market-page response cache & singleflight (#13350)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.routes import futures as futures_routes
from app.services import get_db
from app.utils import futures_page_cache as fpc

pytestmark = pytest.mark.anyio


def _route_client():
    app = FastAPI()
    app.include_router(futures_routes.router, prefix="/api/futures")

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestTTLsAndKeys:
    def test_ttl_bounds_match_spec(self):
        assert fpc.DETAIL_TTL == 15.0
        assert fpc.SUBROUTE_TTL == 60.0
        assert fpc.detail_ttl({"id": 1}) == 15.0
        assert fpc.subroute_ttl({"ok": True}) == 60.0
        assert fpc.detail_ttl(None) == 0.0
        assert fpc.subroute_ttl(None) == 0.0

    def test_history_ttl_skips_when_venue_fill_requested(self):
        assert fpc.history_ttl({"venue_history": {"fill": "requested"}}) == 0.0
        assert fpc.history_ttl({"venue_history": {"fill": "already_claimed"}}) == 60.0
        assert fpc.history_ttl({"venue_history": {"fill": "answered_recently"}}) == 60.0
        assert fpc.history_ttl({"outcomes": []}) == 60.0
        assert fpc.history_ttl("bad") == 0.0

    def test_related_events_ttl_caps_at_nearest_scheduled_kickoff(self):
        now = datetime(2026, 11, 21, 22, 0, 0, tzinfo=timezone.utc)
        soon = {
            "events": [
                {"status": "live", "commence_time": (now - timedelta(minutes=10)).isoformat()},
                {"status": "scheduled", "commence_time": (now + timedelta(seconds=25)).isoformat()},
                {"status": "scheduled", "commence_time": (now + timedelta(minutes=10)).isoformat()},
            ]
        }
        assert fpc.related_events_ttl(soon, now_dt=now) == pytest.approx(25.0)

        past_scheduled = {
            "events": [
                {"status": "scheduled", "commence_time": (now - timedelta(seconds=1)).isoformat()},
            ]
        }
        assert fpc.related_events_ttl(past_scheduled, now_dt=now) == 0.0

        far_future = {
            "events": [
                {"status": "scheduled", "commence_time": (now + timedelta(hours=3)).isoformat()},
            ]
        }
        assert fpc.related_events_ttl(far_future, now_dt=now) == 60.0

    def test_query_parameter_keys_are_isolated(self):
        assert fpc.detail_key(10, "source") != fpc.detail_key(10, "verified_title")
        assert fpc.detail_key(10, "bogus") == fpc.detail_key(10, "source")
        assert fpc.history_key(10, None, 168, 10, None, None) != fpc.history_key(
            10, 99, 168, 10, None, None
        )
        assert fpc.history_key(10, None, 168, 10, None, None) != fpc.history_key(
            10, None, 24, 10, None, None
        )
        assert fpc.history_key(10, None, 168, 10, None, None) != fpc.history_key(
            10, None, 168, 50, None, None
        )
        assert fpc.history_key(10, None, 168, 10, "Chiefs", None) != fpc.history_key(
            10, None, 168, 10, None, None
        )
        assert fpc.history_key(10, None, 168, 10, None, "full") != fpc.history_key(
            10, None, 168, 10, None, None
        )
        assert fpc.progression_key(10, 32, None) != fpc.progression_key(10, 40, None)
        assert fpc.progression_key(10, 32, "abc") != fpc.progression_key(10, 32, None)
        assert fpc.group_key("polymarket:1") != fpc.group_key("polymarket:2")
        assert fpc.probability_timeline_key(10, 20, 168, "source", "full") != fpc.probability_timeline_key(
            10, 10, 168, "source", "full"
        )
        assert fpc.probability_timeline_key(10, 20, 168, "source", "full") != fpc.probability_timeline_key(
            10, 20, 24, "source", "full"
        )
        assert fpc.probability_timeline_key(10, 20, 168, "source", "full") != fpc.probability_timeline_key(
            10, 20, 168, "verified_title", "full"
        )
        assert fpc.probability_timeline_key(10, 20, 168, "source", "full") != fpc.probability_timeline_key(
            10, 20, 168, "source", None
        )

    def test_probability_timeline_ttl_and_cap_isolation(self, monkeypatch):
        from app.utils import full_range_live

        assert fpc.RESOLVED_TIMELINE_TTL == 900.0
        assert fpc.probability_timeline_ttl({"timeline": [{"t": 1}]}, resolved_full=True) == 900.0
        assert fpc.probability_timeline_ttl({"timeline": []}, resolved_full=True) == 0.0
        assert fpc.probability_timeline_ttl({"timeline": [{"t": 1}]}, resolved_full=False) == 60.0
        assert fpc.probability_timeline_ttl({"venue_history": {"fill": "requested"}}, resolved_full=True) == 0.0
        assert fpc.probability_timeline_ttl({"venue_history": {"state": "unavailable"}}, resolved_full=True) == 0.0
        assert fpc.probability_timeline_ttl({"archive_history": {"state": "unavailable"}}, resolved_full=True) == 0.0
        assert fpc.probability_timeline_ttl("bad", resolved_full=True) == 0.0

        monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
        k_4000 = fpc.probability_timeline_key(70709343, 20, 168, "source", "full")
        monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
        k_2000 = fpc.probability_timeline_key(70709343, 20, 168, "source", "full")
        assert k_4000 != k_2000


class TestLRUMemoryAndExpiry:
    def test_expiry_honours_exact_ttl_boundaries(self):
        key = fpc.detail_key(42, "source")
        fpc.write(key, b'{"id":42}', 15.0, now=100.0)
        assert fpc.read(key, now=114.9) == b'{"id":42}'
        assert fpc.read(key, now=115.0) is None
        assert fpc.total_bytes() == 0

    def test_memory_cap_evicts_oldest_and_skips_oversized(self, monkeypatch):
        monkeypatch.setattr(fpc, "MAX_BYTES", 10)
        monkeypatch.setattr(fpc, "MAX_ENTRY_BYTES", 6)

        k1 = fpc.group_key("g1")
        k2 = fpc.group_key("g2")
        k3 = fpc.group_key("g3")
        k_big = fpc.group_key("big")

        fpc.write(k_big, b"1234567", 60.0, now=1.0)
        assert fpc.read(k_big, now=2.0) is None
        assert fpc.total_bytes() == 0

        fpc.write(k1, b"aaaaa", 60.0, now=1.0)
        fpc.write(k2, b"bbbbb", 60.0, now=2.0)
        assert fpc.total_bytes() == 10
        # Touch k1 so k2 becomes least-recently-used.
        assert fpc.read(k1, now=3.0) == b"aaaaa"

        fpc.write(k3, b"ccccc", 60.0, now=4.0)
        assert fpc.total_bytes() == 10
        assert fpc.read(k2, now=5.0) is None
        assert fpc.read(k1, now=5.0) == b"aaaaa"
        assert fpc.read(k3, now=5.0) == b"ccccc"


class TestFiveEndpointsSingleflightAndPriceTruth:
    @pytest.mark.parametrize(
        "attr,path,expected_ttl",
        [
            ("get_futures_market", "/api/futures/777", 15.0),
            ("get_futures_history", "/api/futures/777/history", 60.0),
            ("get_progression", "/api/futures/777/progression", 60.0),
            ("get_related_events", "/api/futures/777/related-events", 60.0),
            ("get_group", "/api/futures/groups/polymarket:abc", 60.0),
        ],
    )
    async def test_concurrent_reads_coalesce_to_one_build_and_preserve_price_ages(
        self, monkeypatch, attr, path, expected_ttl
    ):
        clock = {"now": 1000.0}
        monkeypatch.setattr(fpc.time, "monotonic", lambda: clock["now"])

        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        price_stamp = "2026-11-21T20:01:02+00:00"

        async def _fake_handler(**_kwargs):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return {
                "market_id": 777,
                "updated_at": price_stamp,
                "prices_updated_at": price_stamp,
                "outcomes": [
                    {
                        "id": 1,
                        "last_updated": price_stamp,
                        "history": [{"timestamp": price_stamp, "probability": 0.42}],
                    }
                ],
                "events": [],
            }

        monkeypatch.setattr(futures_routes, attr, _fake_handler)

        async with _route_client() as client:
            tasks = [asyncio.create_task(client.get(path)) for _ in range(5)]
            await entered.wait()
            await asyncio.sleep(0)
            release.set()
            responses = await asyncio.gather(*tasks)

            assert calls == 1
            states = sorted(r.headers["X-Feed-Cache"] for r in responses)
            assert states == ["coalesced"] * 4 + ["miss"]
            assert all("cache-control" not in r.headers for r in responses)
            first_body = responses[0].json()
            assert all(r.json() == first_body for r in responses)

            # Just before expiry: served from saved copy, price timestamps unchanged.
            clock["now"] = 1000.0 + expected_ttl - 0.5
            warm = await client.get(path)
            assert calls == 1
            assert warm.headers["X-Feed-Cache"] == "hit"
            warm_body = warm.json()
            assert warm_body == first_body
            assert warm_body["updated_at"] == price_stamp
            assert warm_body["prices_updated_at"] == price_stamp
            assert warm_body["outcomes"][0]["last_updated"] == price_stamp
            assert warm_body["outcomes"][0]["history"][0]["timestamp"] == price_stamp

            # Past expiry: rebuilds cleanly.
            clock["now"] = 1000.0 + expected_ttl + 0.1
            expired = await client.get(path)
            assert calls == 2
            assert expired.headers["X-Feed-Cache"] == "miss"

    async def test_query_variants_isolate_cached_responses(self, monkeypatch):
        seen_hours: list[int] = []

        async def _fake_history(
            market_id,
            outcome_id=None,
            hours=168,
            top_n=10,
            champion=None,
            db=None,
            history_range=None,
        ):
            seen_hours.append(hours)
            return {"market_id": market_id, "hours": hours, "outcomes": []}

        monkeypatch.setattr(futures_routes, "get_futures_history", _fake_history)

        async with _route_client() as client:
            r1 = await client.get("/api/futures/55/history?hours=168")
            r2 = await client.get("/api/futures/55/history?hours=24")
            r3 = await client.get("/api/futures/55/history?hours=168")

        assert seen_hours == [168, 24]
        assert r1.headers["X-Feed-Cache"] == "miss"
        assert r2.headers["X-Feed-Cache"] == "miss"
        assert r3.headers["X-Feed-Cache"] == "hit"
        assert r2.json()["hours"] == 24
        assert r3.json()["hours"] == 168

    async def test_fresh_bypass_does_not_read_or_write_cache(self, monkeypatch):
        calls = 0

        async def _fake_detail(**_kwargs):
            nonlocal calls
            calls += 1
            return {"id": 88, "version": calls, "updated_at": "2026-11-21T20:00:00Z"}

        monkeypatch.setattr(futures_routes, "get_futures_market", _fake_detail)

        async with _route_client() as client:
            r1 = await client.get("/api/futures/88")
            fresh_resp = await client.get("/api/futures/88?fresh=true")
            cached_after = await client.get("/api/futures/88")

        assert calls == 2
        assert r1.headers["X-Feed-Cache"] == "miss"
        assert fresh_resp.headers["X-Feed-Cache"] == "bypass"
        assert fresh_resp.json()["version"] == 2
        assert cached_after.headers["X-Feed-Cache"] == "hit"
        assert cached_after.json()["version"] == 1

    async def test_coalesced_fresh_barrier_starts_after_asked_at(self, monkeypatch):
        clock = {"now": 10.0}
        monkeypatch.setattr(fpc.time, "monotonic", lambda: clock["now"])

        first_entered = asyncio.Event()
        first_release = asyncio.Event()
        calls = 0

        async def _build():
            nonlocal calls
            calls += 1
            if calls == 1:
                first_entered.set()
                await first_release.wait()
            return {"version": calls}

        async def _call_at_t(t_asked: float):
            clock["now"] = t_asked
            return await fpc.serve_cached_or_build(
                key=fpc.detail_key(91, "source"),
                fresh=True,
                build=_build,
                ttl_for=fpc.detail_ttl,
            )

        t1 = asyncio.create_task(_call_at_t(10.0))
        await first_entered.wait()
        # Arrived strictly after build 1 started: waits, then triggers one new build
        # shared by late waiters instead of reading build 1's older snapshot.
        t2 = asyncio.create_task(_call_at_t(11.0))
        await asyncio.sleep(0)
        clock["now"] = 12.0
        first_release.set()
        r1, r2 = await asyncio.gather(t1, t2)

        assert calls == 2
        assert r1.headers["X-Feed-Cache"] == "bypass"
        assert r2.headers["X-Feed-Cache"] == "bypass"
        assert r1.body != r2.body

    async def test_404_errors_coalesce_in_flight_and_are_never_cached(self, monkeypatch):
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def _missing(**_kwargs):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            raise HTTPException(status_code=404, detail="Market not found")

        monkeypatch.setattr(futures_routes, "get_futures_market", _missing)

        async with _route_client() as client:
            tasks = [asyncio.create_task(client.get("/api/futures/404")) for _ in range(3)]
            await entered.wait()
            await asyncio.sleep(0)
            release.set()
            burst = await asyncio.gather(*tasks)
            assert calls == 1
            assert all(r.status_code == 404 for r in burst)

            follow_up = await client.get("/api/futures/404")
            assert follow_up.status_code == 404
            assert calls == 2

    async def test_leader_cancellation_hands_off_cleanly_to_waiter(self):
        first_entered = asyncio.Event()
        calls = 0

        async def _build():
            nonlocal calls
            calls += 1
            if calls == 1:
                first_entered.set()
                await asyncio.sleep(10.0)
            return {"ok": True}

        key = fpc.group_key("cancel-test")
        leader = asyncio.create_task(
            fpc.serve_cached_or_build(
                key=key,
                fresh=False,
                build=_build,
                ttl_for=fpc.subroute_ttl,
            )
        )
        await first_entered.wait()
        waiter = asyncio.create_task(
            fpc.serve_cached_or_build(
                key=key,
                fresh=False,
                build=_build,
                ttl_for=fpc.subroute_ttl,
            )
        )
        await asyncio.sleep(0)
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        resp = await waiter
        assert resp.status_code == 200
        assert calls == 2

    async def test_probability_timeline_route_coalesces_caches_and_respects_fresh(self, monkeypatch):
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def _fake_timeline(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
            meta = kwargs.get("_cache_meta")
            if meta is not None:
                meta["resolved_full"] = True
            return {"market_id": kwargs["market_id"], "timeline": [{"t": calls}], "outcomes": []}

        monkeypatch.setattr(futures_routes, "get_probability_timeline", _fake_timeline)

        async with _route_client() as client:
            path = "/api/futures/70709343/probability-timeline?top=20&hours=168&range=full"
            burst_tasks = [asyncio.create_task(client.get(path)) for _ in range(3)]
            await entered.wait()
            await asyncio.sleep(0)
            release.set()
            burst = await asyncio.gather(*burst_tasks)
            assert calls == 1
            assert [r.headers.get("X-Feed-Cache") for r in burst].count("miss") == 1
            assert [r.headers.get("X-Feed-Cache") for r in burst].count("coalesced") == 2

            hit = await client.get(path)
            assert hit.status_code == 200
            assert hit.headers.get("X-Feed-Cache") == "hit"
            assert calls == 1

            bypass = await client.get(f"{path}&fresh=true")
            assert bypass.status_code == 200
            assert bypass.headers.get("X-Feed-Cache") == "bypass"
            assert calls == 2
