"""One staged expansion preserves the live shard; ordinary compaction survives."""
import asyncio
import pytest
from app.services import polymarket_ws as service
from tests.test_pm_open_cycle_lifetime_10090 import until

@pytest.mark.asyncio
async def test_first_expansion_retains_small_live_shard_then_normal_compaction_and_empty():
    ws = service.PolymarketWebSocket()
    active, starts, stopped = {}, [], []
    async def shard(ids, index):
        identity = object()
        active[index] = identity
        starts.append((index, tuple(ids), identity))
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(identity)
            if active.get(index) is identity:
                del active[index]
    ws._run_one = shard
    initial = [str(n) for n in range(7)]
    expanded = initial + ["7", "8"]
    owner = asyncio.create_task(ws.run_refreshable(initial))
    try:
        await until(lambda: len(active) == 1)
        first = active[0]
        ws.update_asset_ids(expanded, preserve_existing_shards=True)
        await until(lambda: len(active) == 2)
        assert active[0] is first and not stopped
        assert set().union(*(set(ids) for ids in ws._shard_ids.values())) == set(expanded)
        preserved = set(active.values())
        ws.update_asset_ids(expanded + ["9"])
        await until(lambda: len(active) == 1 and first in stopped)
        assert preserved <= set(stopped)
        assert len(starts) == 3
        assert list(ws._shard_ids.values()) == [expanded + ["9"]]
        ws.update_asset_ids([], preserve_existing_shards=True)
        await until(lambda: not active and not ws._shard_ids)
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
    assert len(stopped) == len(starts)
