"""#10090 — a Polymarket catalog refresh restarts only the sockets it must.

Production, v5644 at 17:42:43Z on 2026-10-11 (worker-ws.1 logs): the timer
refresh of a live NFL slate, on a catalog that mostly shrank (resolved props),
restarted 29 of 40 game sockets and 89 of 92 open-contract sockets. Each
restart re-sends the venue's book for every token on it (+37,876 snapshot
quotes). The live games' prices then waited 24-41 s for their commit and
16-78 s more for their stamp (tail receipts), with 26 lock-timeout flushes.
Those are the stage records of that window. This file tests the restart rule,
not that timing.

The rule: an existing socket restarts when it is empty, or when it is under
half full on both ceilings (token count and subscribe bytes) and either shrank
or has new tokens to absorb. New tokens otherwise open their own shard. A
token a kept socket still carries but its client no longer owns is fenced: its
quotes, trades and books never reach the callbacks (Root's review of
1c98181cc9: the game and open clients share routing maps, so a moved token is
still "mapped").
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


# ── the fence: a kept socket never hands a dropped token to the callbacks ──
#
# Root's review of 1c98181cc9 (ROOT-SOURCE-REVIEW.json): the game and open
# clients share one set of routing maps, so a token that MOVES from one client's
# catalog to the other's is still "mapped" — the kept old socket delivered it a
# second time. These drive the real `_run_one` over a fake transport.

import json as _json

import websockets


class _Transport:
    """`websockets.connect` stand-in: one queue-fed socket per connect."""

    def __init__(self):
        self.sockets = []

    def connect(self, *args, **kwargs):
        socket = _FakeSocket()
        self.sockets.append(socket)
        return socket

    def carrying(self, asset_id, *, exclude=()):
        return [
            s for s in self.sockets
            if s.assets and asset_id in s.assets and not s.closed and s not in exclude
        ]


class _FakeSocket:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.assets = None
        self.closed = False
        self._ack = None

    async def send(self, payload):
        if payload != "PING":
            # Subscribe-all (the resolution-only `run()`) names no ids.
            self.assets = tuple(_json.loads(payload).get("assets_ids") or ("*",))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._ack is not None:
            self._ack.set()
            self._ack = None
        return await self.queue.get()

    async def deliver(self, frame):
        """Put one frame on the wire and wait until the reader has taken it
        AND come back for the next (so its dispatch has finished)."""
        self.queue.put_nowait(_json.dumps(frame))
        await asyncio.sleep(0)
        ack = self._ack = asyncio.Event()
        self.queue.put_nowait(_json.dumps({"event_type": "noop"}))
        await asyncio.wait_for(ack.wait(), 3)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        gate = getattr(self, "exit_gate", None)
        if gate is not None:  # hold a cancelled socket mid-teardown
            self.exit_started.set()
            await gate.wait()
        self.closed = True


def _quote(asset_id):
    return {"event_type": "best_bid_ask", "asset_id": asset_id,
            "best_bid": "0.40", "best_ask": "0.60"}


def _trade(asset_id):
    return {"event_type": "last_trade_price", "asset_id": asset_id, "price": "0.5"}


def _book(*asset_ids):
    return [{"event_type": "book", "asset_id": a,
             "bids": [{"price": "0.40", "size": "1"}],
             "asks": [{"price": "0.60", "size": "1"}]} for a in asset_ids]


@pytest.fixture
def wire(monkeypatch):
    _small_shards(monkeypatch, 4)
    transport = _Transport()
    monkeypatch.setattr(websockets, "connect", transport.connect)
    return transport


def _client(name, received, *, snapshots=False):
    ws = service.PolymarketWebSocket(price_book_snapshots=snapshots)
    # The production callbacks accept any token either client's map owns.
    ws.on_price = lambda msg: received.append((name, "price", msg["asset_id"]))
    ws.on_trade = lambda msg: received.append((name, "trade", msg["asset_id"]))
    return ws


@pytest.mark.asyncio
async def test_a_token_moving_between_clients_is_delivered_only_by_its_new_owner(wire):
    received = []
    game, open_ = _client("game", received), _client("open", received)
    tasks = [
        asyncio.create_task(game.run_refreshable(["mv", "g1", "g2", "g3"])),
        asyncio.create_task(open_.run_refreshable(["o1", "o2", "o3", "back"])),
    ]
    try:
        await until(lambda: len(wire.sockets) == 2 and all(s.assets for s in wire.sockets))
        game_socket = wire.carrying("mv")[0]
        open_socket = wire.carrying("back")[0]
        # "mv" moves game → open and "back" moves open → game, in one refresh.
        game.update_asset_ids(["g1", "g2", "g3", "back"])
        open_.update_asset_ids(["o1", "o2", "o3", "mv"])
        await until(lambda: wire.carrying("mv", exclude=[game_socket])
                    and wire.carrying("back", exclude=[open_socket]))
        assert not game_socket.closed and not open_socket.closed  # reuse kept
        for frame in (_quote("mv"), _trade("mv"), _quote("back"), _trade("back")):
            await game_socket.deliver(frame)
            await open_socket.deliver(frame)
        for socket in (wire.carrying("mv", exclude=[game_socket])[0],
                       wire.carrying("back", exclude=[open_socket])[0]):
            await socket.deliver(_quote(socket.assets[0]))
        assert sorted(received) == [("game", "price", "back"), ("open", "price", "mv")]
        # The raw wire still records what the old sockets were sent (#837).
        assert any("mv" in w for w in game._shard_wire.values())
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_the_fence_narrows_at_update_before_the_owner_loop_runs(wire):
    received = []
    game = _client("game", received)
    task = asyncio.create_task(game.run_refreshable(["mv", "g1", "g2", "g3"]))
    try:
        await until(lambda: wire.sockets and wire.sockets[0].assets)
        socket = wire.sockets[0]
        game.update_asset_ids(["g1", "g2", "g3"])
        # No await between the update and this frame's arrival at the reader.
        assert "mv" not in game._shard_routed[0]
        await socket.deliver(_quote("mv"))
        await socket.deliver(_quote("g1"))
        assert received == [("game", "price", "g1")]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_retired_tokens_book_is_not_priced_and_a_returning_token_is(wire):
    received = []
    game = _client("game", received, snapshots=True)
    task = asyncio.create_task(game.run_refreshable(["r", "g1", "g2", "g3"]))
    try:
        await until(lambda: wire.sockets and wire.sockets[0].assets)
        socket = wire.sockets[0]
        game.update_asset_ids(["g1", "g2", "g3"])  # "r" resolved: gone everywhere
        await _settled(game)
        await socket.deliver(_book("r", "g1"))
        assert received == [("game", "price", "g1")]
        game.update_asset_ids(["r", "g1", "g2", "g3"])  # it returns
        await _settled(game)
        assert len(wire.sockets) == 1  # same socket, no second subscription
        await socket.deliver(_quote("r"))
        assert received[-1] == ("game", "price", "r")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_plain_run_is_unfenced(wire):
    received = []
    ws = _client("shadow", received)
    task = asyncio.create_task(ws.run(None))  # resolution-only subscribe-all
    try:
        await until(lambda: wire.sockets and wire.sockets[0].assets == ("*",))
        await wire.sockets[0].deliver(_quote("anything"))
        assert received == [("shadow", "price", "anything")]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_receiver_parent_drops_pipe_frames_for_a_token_that_left_its_catalog():
    from app.services import polymarket_ws_process as proc

    received = []
    client = proc.PolymarketOpenReceiverProcess()
    client.on_price = lambda msg: received.append(("price", msg["asset_id"]))
    client.on_trade = lambda msg: received.append(("trade", msg["asset_id"]))
    client._wake = asyncio.Event()  # as inside run_refreshable
    client._routed = frozenset(["mv", "o1"])
    client.update_asset_ids(["o1"])  # "mv" moved to the game client

    class _Child:
        pid = 0
        stdout = asyncio.StreamReader()

    for frame in ((proc.PRICE, _quote("mv")), (proc.TRADE, _trade("mv")),
                  (proc.PRICE, _quote("o1"))):
        _Child.stdout.feed_data(proc.encode_frame(frame))
    _Child.stdout.feed_eof()
    with pytest.raises(RuntimeError, match="exited"):
        await client._dispatch(_Child)
    assert received == [("price", "o1")]


@pytest.mark.asyncio
async def test_a_socket_the_byte_ceiling_filled_is_not_taken_for_a_small_one(monkeypatch):
    """Half full is judged on both ceilings: three long ids that fill the
    subscribe bytes are a full socket even though eight would fit by count."""
    longs = [f"{i:03d}" + "x" * 200 for i in range(6)]
    cap = len(service._subscribe_frame(longs[:3]).encode("utf-8"))
    monkeypatch.setattr(service, "MAX_ASSETS_PER_CONNECTION", 8)
    monkeypatch.setattr(service, "MAX_SUBSCRIBE_BYTES", cap)
    split = service._shard_asset_ids
    monkeypatch.setattr(
        service, "_shard_asset_ids",
        lambda ids: split(ids, max_bytes=cap, max_assets=8),
    )
    ws = service.PolymarketWebSocket()
    sockets = _Sockets()
    monkeypatch.setattr(ws, "_run_one", sockets.run_one)
    owner = asyncio.create_task(ws.run_refreshable(longs))
    try:
        await until(lambda: len(sockets.active) == 2)
        before = dict(sockets.active)
        # Socket 0 loses one of three (2 of 8 by count, 2/3 of its bytes) while
        # a new token arrives: by count alone it would be "small" and restart.
        ws.update_asset_ids(longs[1:] + ["new"])
        await until(lambda: len(sockets.active) == 3)
        assert sockets.active[0] is before[0] and sockets.active[1] is before[1]
        assert not sockets.stopped
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner


@pytest.mark.asyncio
async def test_a_catalog_arriving_while_a_refresh_cancels_is_not_reopened_after(wire):
    """Root's review of 8d3ff60e52: refresh A awaits its cancelled sockets; a
    catalog B that drops "mv" narrows the fence meanwhile; A must not then
    restore the fence from its own, older catalog."""
    received = []
    game = _client("game", received)
    task = asyncio.create_task(game.run_refreshable(
        ["mv", "a", "b", "c", "d1", "d2", "d3", "d4"]
    ))
    try:
        await until(lambda: len(wire.sockets) == 2 and all(s.assets for s in wire.sockets))
        kept = wire.carrying("mv")[0]
        emptied = wire.carrying("d1")[0]
        emptied.exit_gate, emptied.exit_started = asyncio.Event(), asyncio.Event()
        game.update_asset_ids(["mv", "a", "b", "c"])  # A: empties socket 1
        await asyncio.wait_for(emptied.exit_started.wait(), 3)
        game.update_asset_ids(["a", "b", "c"])  # B, while A is cancelling
        emptied.exit_gate.set()
        for _ in range(50):
            assert not game._routes(0, {"asset_id": "mv"})
            await asyncio.sleep(0)
        await _settled(game)
        await kept.deliver(_quote("mv"))
        await kept.deliver(_quote("a"))
        assert received == [("game", "price", "a")]
        assert not kept.closed  # B still only shrank it: no restart
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_widened_kept_fence_still_honours_a_catalog_arriving_mid_cancel(wire):
    """Live's review 217 of #11457: once a kept socket's fence is rebuilt only
    when it must widen, the test above no longer reaches the rebuild. Here
    socket 0 must widen ("a" returns) while a catalog arriving during the
    cancel await drops "mv" — the rebuild must still filter by the latest
    catalog."""
    received = []
    game = _client("game", received)
    task = asyncio.create_task(game.run_refreshable(
        ["mv", "a", "b", "c", "d1", "d2", "d3", "d4"]
    ))
    try:
        await until(lambda: len(wire.sockets) == 2 and all(s.assets for s in wire.sockets))
        kept = wire.carrying("mv")[0]
        game.update_asset_ids(["mv", "b", "c", "d1", "d2", "d3", "d4"])  # fence "a" off
        await _settled(game)
        assert not game._routes(0, {"asset_id": "a"})
        emptied = wire.carrying("d1")[0]
        emptied.exit_gate, emptied.exit_started = asyncio.Event(), asyncio.Event()
        game.update_asset_ids(["mv", "a", "b", "c"])  # A: "a" returns, socket 1 empties
        await asyncio.wait_for(emptied.exit_started.wait(), 3)
        game.update_asset_ids(["a", "b", "c"])  # B, while A is cancelling
        emptied.exit_gate.set()
        for _ in range(50):
            assert not game._routes(0, {"asset_id": "mv"})
            await asyncio.sleep(0)
        await _settled(game)
        assert game._routes(0, {"asset_id": "a"})
        await kept.deliver(_quote("mv"))
        await kept.deliver(_quote("a"))
        assert received == [("game", "price", "a")]
        assert not kept.closed
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
