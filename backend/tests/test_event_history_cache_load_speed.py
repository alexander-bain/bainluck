"""Event chart history cache — Alex Oct 8 load-speed push (#10090, #1469).

The route wrapper `get_event_odds_history_cached` answers a repeat reader from
memory instead of rebuilding the chart; the build itself is unchanged.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.routes import events as events_route
from app.utils import event_history_cache as ehc

NOW = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


def _payload(status, completed_at=None, marker=0):
    return {
        "event_id": 7,
        "status": status,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "aggregate_line": [{"t": "2026-10-08T13:00:00+00:00", "p": 0.5}],
        "marker": marker,
    }


class TestLease:
    def test_live_is_short(self):
        assert ehc.lease_for(_payload("live"), NOW.timestamp()) == ehc.LIVE_TTL

    def test_settled_long_ago_is_long(self):
        p = _payload("completed", NOW - timedelta(hours=2))
        assert ehc.lease_for(p, NOW.timestamp()) == ehc.SETTLED_TTL

    def test_freshly_settled_is_short(self):
        p = _payload("closed", NOW - timedelta(minutes=3))
        assert ehc.lease_for(p, NOW.timestamp()) == ehc.FRESHLY_SETTLED_TTL

    def test_settled_without_finish_time_is_short(self):
        assert ehc.lease_for(_payload("completed"), NOW.timestamp()) == ehc.FRESHLY_SETTLED_TTL

    def test_scheduled_is_default(self):
        assert ehc.lease_for(_payload("scheduled"), NOW.timestamp()) == ehc.DEFAULT_TTL


class TestStore:
    def test_expires_at_lease(self):
        k = ehc.cache_key(1, 48, "since_start")
        ehc.write(k, b"{}", None, 10.0, now=100.0)
        assert ehc.read(k, now=109.9) == (b"{}", None)
        assert ehc.read(k, now=110.0) is None
        assert ehc.total_bytes() == 0

    def test_byte_bound_evicts_oldest(self, monkeypatch):
        monkeypatch.setattr(ehc, "MAX_BYTES", 10)
        ehc.write(ehc.cache_key(1, 1, "all"), b"123456", None, 60, now=0)
        ehc.write(ehc.cache_key(2, 1, "all"), b"123456", None, 60, now=0)
        assert ehc.read(ehc.cache_key(1, 1, "all"), now=1) is None
        assert ehc.read(ehc.cache_key(2, 1, "all"), now=1) == (b"123456", None)
        assert ehc.total_bytes() == 6

    def test_oversized_body_not_cached(self, monkeypatch):
        monkeypatch.setattr(ehc, "MAX_ENTRY_BYTES", 3)
        ehc.write(ehc.cache_key(1, 1, "all"), b"1234", None, 60, now=0)
        assert ehc.read(ehc.cache_key(1, 1, "all"), now=1) is None


def _install_build(monkeypatch, payloads, cache_control=None, delay=0.0):
    calls = []

    async def fake_build(event_id, *, hours, chart_range, response, db, fresh):
        calls.append((event_id, hours, chart_range, fresh))
        if delay:
            await asyncio.sleep(delay)
        if cache_control:
            response.headers["Cache-Control"] = cache_control
        item = payloads[min(len(calls) - 1, len(payloads) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(events_route, "get_event_odds_history", fake_build)
    return calls


async def _get(event_id=7, hours=48, chart_range="since_start", fresh=False):
    return await events_route.get_event_odds_history_cached(
        event_id, hours=hours, chart_range=chart_range, response=None, db=None, fresh=fresh
    )


class TestRoute:
    @pytest.mark.asyncio
    async def test_second_reader_is_served_from_memory(self, monkeypatch):
        done = NOW - timedelta(hours=3)
        calls = _install_build(
            monkeypatch,
            [_payload("completed", done, 1), _payload("completed", done, 2)],
            cache_control="public, max-age=3600, stale-while-revalidate=300",
        )
        first = await _get()
        second = await _get()
        assert len(calls) == 1
        assert first.body == second.body
        assert json.loads(second.body)["marker"] == 1
        assert first.headers["x-feed-cache"] == "miss"
        assert second.headers["x-feed-cache"] == "hit"
        assert second.headers["cache-control"].startswith("public, max-age=3600")

    @pytest.mark.asyncio
    async def test_params_are_part_of_the_key(self, monkeypatch):
        calls = _install_build(monkeypatch, [_payload("live", marker=1), _payload("live", marker=2)])
        await _get(chart_range="since_start")
        other = await _get(chart_range="all")
        assert len(calls) == 2
        assert json.loads(other.body)["marker"] == 2

    @pytest.mark.asyncio
    async def test_fresh_bypasses_read_and_publishes(self, monkeypatch):
        calls = _install_build(
            monkeypatch,
            [_payload("live", marker=1), _payload("live", marker=2), _payload("live", marker=3)],
        )
        await _get()
        fresh = await _get(fresh=True)
        after = await _get()
        assert [c[3] for c in calls] == [False, True]
        assert json.loads(fresh.body)["marker"] == 2
        assert json.loads(after.body)["marker"] == 2

    @pytest.mark.asyncio
    async def test_concurrent_readers_share_one_build(self, monkeypatch):
        calls = _install_build(monkeypatch, [_payload("live", marker=1)], delay=0.05)
        results = await asyncio.gather(*[_get() for _ in range(5)])
        assert len(calls) == 1
        assert {r.body for r in results} == {results[0].body}
        assert sorted(r.headers["x-feed-cache"] for r in results) == ["coalesced"] * 4 + ["miss"]

    @pytest.mark.asyncio
    async def test_404_is_not_cached(self, monkeypatch):
        calls = _install_build(
            monkeypatch, [HTTPException(status_code=404, detail="Event not found")]
        )
        for _ in range(2):
            with pytest.raises(HTTPException):
                await _get()
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_body_is_what_fastapi_would_have_serialized(self, monkeypatch):
        p = _payload("live")
        _install_build(monkeypatch, [p])
        resp = await _get()
        assert json.loads(resp.body) == p
        assert resp.media_type == "application/json"
