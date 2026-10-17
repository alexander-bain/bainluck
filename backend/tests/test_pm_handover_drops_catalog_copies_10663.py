"""#10663 — the PM worker keeps one catalog, not the copies it was built from.

``refresh_catalog`` copies each slate map and the open-contract admission into
the long-lived maps (``clear()`` + ``update()``). The source objects are then
dead weight, but the consumer kept them bound: ``game_slate``/``preread`` for
the whole run, and ``fresh_slate``/``fresh_open`` until the NEXT refresh
rebound them — so while that next refresh read, the worker held the live maps,
the previous refresh's copy, the startup copy and the new one being built.
On production (v5764, 10/17) dyno memory stepped up during each handover read
and the worker sat over its 1 GB quota.

The guard samples the heap at the one point where only the installed catalog
is owed: right after a handover has been installed and before the next read.
"""

import asyncio
import gc
import json

import pytest
import websockets

from app.services import polymarket_ws as service
from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_open_contracts as admission
from app.tasks import polymarket_ws as task
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig, until
from tests.test_ws_consumer_session_lifetime_2471 import _install

_SLATE_KEYS = {"asset_to_outcome", "market_by_outcome", "non_blend_market_ids"}


def _retained_copies():
    gc.collect()
    slates = admissions = 0
    for obj in gc.get_objects():
        if isinstance(obj, dict) and _SLATE_KEYS <= obj.keys():
            slates += 1
        elif isinstance(obj, admission.OpenContractAdmission):
            admissions += 1
    return slates, admissions


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_refresh", [False, True])
@pytest.mark.parametrize("open_only", [False, True])
async def test_installed_handover_leaves_no_source_copy_alive(
    monkeypatch, fail_refresh, open_only
):
    rig = CatalogRig()
    if open_only:
        # No game assets: the startup admission holds a pre-read, which must
        # be released too (CatalogRig's default slate never sets one).
        rig.slate = ([], [], [])
    rig.fail_refresh = fail_refresh
    samples, stop = [], asyncio.Event()
    original_update = service.PolymarketWebSocket.update_asset_ids
    original_load = None

    def sampling_update(self, asset_ids, **kwargs):
        # The game client's bare call follows an installed handover; the open
        # client's keyword call happens inside it, while the slate is owed.
        if not kwargs:
            samples.append(("installed", _retained_copies()))
        return original_update(self, asset_ids, **kwargs)

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

    reads_seen = []

    async def sampling_read_slate_rows():
        # The next slate read begins here: nothing but the installed catalog
        # (and, after a failed refresh, nothing at all extra) may be alive.
        if rig.catalog_reads >= 2:
            reads_seen.append(("read", _retained_copies()))
        if rig.catalog_reads >= 5:
            stop.set()
        return await original_load()

    _install(monkeypatch, rig)
    original_load = rig.read_slate_rows
    rig.read_slate_rows = sampling_read_slate_rows
    monkeypatch.setattr(service.PolymarketWebSocket, "update_asset_ids", sampling_update)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.02)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    # A captured exception record's traceback pins its frames (and every slate
    # they reference) for the test's lifetime; production handlers do not.
    monkeypatch.setattr(task.logger, "disabled", True)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    # A hang guard only: the run ends on its fifth catalog read. Each sample
    # walks the whole heap, which in a CI shard's process made the game-slate
    # arms take 9.9-10.4 s (f68f1ed611, backend-tests (7)) vs ~0.5 s alone.
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 60)

    await until(lambda: True)
    assert rig.catalog_reads >= 4, rig.catalog_reads
    if fail_refresh:
        # Every timer refresh fails at the open read and is discarded.
        assert stats.get("catalog_refreshes", 0) == 0
        assert not samples
    else:
        assert stats["catalog_refreshes"] >= 2
        assert samples
        # The installed catalog lives in the long-lived maps; no slate dict
        # and no admission object it was copied from may still be bound.
        assert all(s == (0, 0) for _, s in samples), samples
    assert reads_seen, "no refresh read was sampled"
    # At the start of each re-read: no previous slate/admission survives.
    assert all(s == (0, 0) for _, s in reads_seen), reads_seen
