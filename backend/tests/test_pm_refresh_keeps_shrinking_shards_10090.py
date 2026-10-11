"""#10090 — a Polymarket catalog refresh never restarts a socket for LOSING tokens.

Production, v5644 at 17:42:43Z on 2026-10-11 (worker-ws.1 logs): the timer
refresh of a live NFL slate mostly removed tokens (resolved props), yet
restarted 29 of 40 game sockets and 89 of 92 open-contract sockets. Each
restart re-sends the venue's book for every token on it — snapshot quotes rose
by ~38k — and the live games' prices then waited 24-41 s for their commit and
16-78 s more for their stamp (tail receipts), with 26 lock-timeout flushes.

The rule under test: an existing socket restarts only when it is empty, or
under half full and either shrank or has new tokens to absorb. New tokens
otherwise open their own shard.
"""

import asyncio

import pytest

from app.services import polymarket_ws as service


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait(), 5)


class _Sockets:
    """`_run_one` stand-in: one identity per started socket, and what it subscribed."""

    def __init__(self):
        self.active: dict[int, object] = {}
        self.subscribed: dict[int, tuple] = {}
        self.starts: list[tuple] = []
        self.stopped: list[object] = []

    async def run_one(self, ids, index):
        identity = object()
        self.active[index] = identity
        self.subscribed[index] = tuple(ids)
        self.starts.append((index, tuple(ids)))
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.append(identity)
            if self.active.get(index) is identity:
                del self.active[index]
                del self.subscribed[index]


def _small_shards(monkeypatch, size):
    monkeypatch.setattr(service, "MAX_ASSETS_PER_CONNECTION", size)
    split = service._shard_asset_ids
    monkeypatch.setattr(
        service, "_shard_asset_ids", lambda ids: split(ids, max_assets=size)
    )


async def _settled(ws):
    await until(lambda: not ws._asset_refresh.is_set())
    for _ in range(5):
        await asyncio.sleep(0)


def _tokens(n, prefix="t"):
    return [f"{prefix}{i:03d}" for i in range(n)]


@pytest.fixture
def rig(monkeypatch):
    _small_shards(monkeypatch, 4)
    ws = service.PolymarketWebSocket()
    sockets = _Sockets()
    monkeypatch.setattr(ws, "_run_one", sockets.run_one)
    return ws, sockets


@pytest.mark.asyncio
async def test_a_refresh_that_only_removes_tokens_restarts_no_socket(rig):
    ws, sockets = rig
    catalog = _tokens(24)  # six full sockets of four
    owner = asyncio.create_task(ws.run_refreshable(catalog))
    try:
        await until(lambda: len(sockets.active) == 6)
        before = dict(sockets.active)
        # The production shape: one resolved prop leaves EVERY socket.
        resolved = set(catalog[::4])
        ws.update_asset_ids([a for a in catalog if a not in resolved])
        await _settled(ws)
        assert sockets.active == before, "a shrinking socket must not restart"
        assert not sockets.stopped and len(sockets.starts) == 6
        # Coverage counts the catalog, not the leftover subscription.
        assert {a for ids in ws._shard_ids.values() for a in ids} == (
            set(catalog) - resolved
        )
        assert all(len(ids) == 3 for ids in ws._shard_ids.values())
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner


@pytest.mark.asyncio
async def test_new_tokens_open_their_own_socket_beside_kept_ones(rig):
    ws, sockets = rig
    catalog = _tokens(16)
    owner = asyncio.create_task(ws.run_refreshable(catalog))
    try:
        await until(lambda: len(sockets.active) == 4)
        before = dict(sockets.active)
        # Lose one per socket (3 of 4 left: above half) and gain two.
        removed = set(catalog[::4])
        added = ["new-a", "new-b"]
        ws.update_asset_ids([a for a in catalog if a not in removed] + added)
        await until(lambda: len(sockets.active) == 5)
        assert all(sockets.active[i] is before[i] for i in before)
        assert not sockets.stopped
        assert sockets.subscribed[4] == tuple(added)
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner


@pytest.mark.asyncio
async def test_a_socket_shrunk_below_half_is_repacked_and_only_it_restarts(rig):
    ws, sockets = rig
    catalog = _tokens(12)  # sockets 0,1,2 of four
    owner = asyncio.create_task(ws.run_refreshable(catalog))
    try:
        await until(lambda: len(sockets.active) == 3)
        before = dict(sockets.active)
        # Socket 1 keeps one token of four (below half); socket 0 keeps three.
        keep = [a for a in catalog if a not in {"t000", "t005", "t006", "t007"}]
        ws.update_asset_ids(keep + ["new-a"])
        await until(lambda: before[1] in sockets.stopped and len(sockets.active) == 3)
        assert sockets.active[0] is before[0] and sockets.active[2] is before[2]
        assert sockets.stopped == [before[1]]
        # Its one survivor and the new token share the reused index.
        assert sockets.subscribed[1] == ("t004", "new-a")
        assert {a for ids in ws._shard_ids.values() for a in ids} == set(
            keep + ["new-a"]
        )
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner


@pytest.mark.asyncio
async def test_a_returning_token_resumes_on_its_own_socket_without_a_restart(rig):
    ws, sockets = rig
    catalog = _tokens(8)
    owner = asyncio.create_task(ws.run_refreshable(catalog))
    try:
        await until(lambda: len(sockets.active) == 2)
        before = dict(sockets.active)
        ws.update_asset_ids([a for a in catalog if a != "t001"])
        await _settled(ws)
        ws.update_asset_ids(catalog)
        await _settled(ws)
        assert sockets.active == before and not sockets.stopped
        # Still subscribed on socket 0, so it is not subscribed twice.
        assert ws._shard_ids[0] == ["t000", "t001", "t002", "t003"]
        assert sum(ids.count("t001") for ids in sockets.subscribed.values()) == 1
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner


@pytest.mark.asyncio
async def test_an_emptied_catalog_still_stops_every_socket(rig):
    ws, sockets = rig
    owner = asyncio.create_task(ws.run_refreshable(_tokens(8)))
    try:
        await until(lambda: len(sockets.active) == 2)
        ws.update_asset_ids([])
        await until(lambda: not sockets.active and not ws._shard_ids)
        assert len(sockets.stopped) == 2
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
