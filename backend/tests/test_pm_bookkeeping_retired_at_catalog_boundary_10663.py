"""#10663 — the PM worker's per-outcome bookkeeping follows the catalog.

``successful_price_write_at`` (last successful write instant, read by the flush
to decide a liveness re-write) and ``input_marks`` (the receipt of the buffered
input) gained an entry for every outcome the process ever priced, and nothing
retired one. The catalog boundary now keeps only the outcomes the installed
catalog owns or a buffered write still carries. The guard drives the real
consumer through timer refreshes and reads both maps where they live.
"""

import asyncio
import json
import sys

import pytest
import websockets

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as task
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig, until
from tests.test_ws_consumer_session_lifetime_2471 import _install

GONE, BUFFERED, OPEN_OUTCOME = 990_001, 990_002, 171


class Socket:
    def __init__(self):
        self.queue = asyncio.Queue()

    async def send(self, payload):
        if payload != "PING":
            json.loads(payload)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.queue.get()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class Refresher(blend.LiveBlendRefresher):
    async def refresh(self, *args, **kwargs):
        return None

    async def refresh_pending(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_a_refresh_retires_bookkeeping_for_outcomes_the_catalog_dropped(monkeypatch):
    rig, stop, seen = CatalogRig(), asyncio.Event(), {}
    _install(monkeypatch, rig)
    original_load = rig.read_slate_rows

    def frame():
        # Called from inside the consumer's own slate read: its state is a
        # caller frame of this hook.
        f = sys._getframe(1)
        while f is not None and "successful_price_write_at" not in f.f_locals:
            f = f.f_back
        assert f is not None, "consumer state frame not found"
        return f.f_locals

    async def reads():
        # Read 2 starts the first timer refresh: seed it. Read 3 starts the
        # second: the first one's catalog boundary has run by then.
        if rig.catalog_reads == 1:
            local = frame()
            for name in ("successful_price_write_at", "input_marks"):
                local[name].update({GONE: 1.0, BUFFERED: 1.0, OPEN_OUTCOME: 1.0})
            local["price_buffer"][BUFFERED] = 0.5
        if rig.catalog_reads == 2:
            local = frame()
            seen.update({name: set(local[name]) for name in
                         ("successful_price_write_at", "input_marks")})
            seen["buffer"] = set(local["price_buffer"])
            stop.set()
        return await original_load()

    rig.read_slate_rows = reads
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.02)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 60)
    await until(lambda: True)

    assert stats["catalog_refreshes"] >= 1
    assert BUFFERED in seen["buffer"]  # still owed when the boundary ran
    for name in ("successful_price_write_at", "input_marks"):
        # Dropped by the catalog, carried by no buffer: retired.
        assert GONE not in seen[name], (name, seen[name])
        # A buffered write keeps its bookkeeping through its drain; an outcome
        # the installed catalog owns keeps it too.
        assert {BUFFERED, OPEN_OUTCOME} <= seen[name], (name, seen[name])
