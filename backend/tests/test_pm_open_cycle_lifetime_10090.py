"""PM open quotes retain sockets/buffers across the game catalog refresh."""

import asyncio
import json
import pytest
import websockets
from sqlalchemy.sql.dml import Update
from app.services import polymarket_ws as service
from app.tasks import polymarket_ws as task
from app.tasks import polymarket_open_contracts as admission
from app.tasks import live_blend_refresh as blend
from tests.test_ws_consumer_session_lifetime_2471 import (
    _Rig,
    _install,
    _assert_one_lent_engine,
    _assert_disposed_once_after_last_session,
)
from tests.test_ws_flush_retry_q491 import POLY_SLATE, _Result


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait(), 5)


@pytest.mark.asyncio
async def test_refresh_preserves_unchanged_shards_and_closes_removed_tokens(
    monkeypatch,
):
    monkeypatch.setattr(service, "MAX_ASSETS_PER_CONNECTION", 2)
    split = service._shard_asset_ids
    monkeypatch.setattr(
        service, "_shard_asset_ids", lambda ids: split(ids, max_assets=2)
    )
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

    monkeypatch.setattr(ws, "_run_one", shard)
    owner = asyncio.create_task(ws.run_refreshable(["a", "b", "c", "d"]))
    try:
        await until(lambda: len(active) == 2)
        original = active.copy()
        ws.update_asset_ids(["d", "c", "b", "a"])
        await until(lambda: not ws._asset_refresh.is_set())
        assert active == original and len(starts) == 2
        ws.update_asset_ids(["a", "c", "d", "e", "f"])
        await until(lambda: len(active) == 3 and active[0] is not original[0])
        assert active[1] is original[1]
        assert {a for ids in ws._shard_ids.values() for a in ids} == {
            "a",
            "c",
            "d",
            "e",
            "f",
        }
        assert original[0] in stopped and original[1] not in stopped
        ws.update_asset_ids([])
        await until(lambda: not active and not ws._shard_ids)
        assert ws._shard_ids == {}
        assert all(
            ids for _, ids, _ in starts
        ), "empty must never subscribe to all markets"
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
    assert len(stopped) == len(starts)


@pytest.mark.asyncio
async def test_catalog_handover_waits_for_both_disjoint_flushes_and_their_stamps():
    boundary = task._PMCatalogFlushBoundary()
    entered, seen, owners = [], [], {1: 900}
    release, handed_over, next_flush = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def flushing(name):
        async with boundary.flushing():
            entered.append(name)
            await release.wait()
            seen.append(owners[1])

    async def handover():
        async with boundary.updating():
            owners[1] = 901
            handed_over.set()

    async def later():
        async with boundary.flushing():
            next_flush.set()
            seen.append(owners[1])

    first, second = asyncio.create_task(flushing("game")), asyncio.create_task(
        flushing("standalone")
    )
    await until(lambda: len(entered) == 2)
    update = asyncio.create_task(handover())
    await until(lambda: boundary.changing)
    third = asyncio.create_task(later())
    await asyncio.sleep(0)
    assert not handed_over.is_set() and not next_flush.is_set()
    release.set()
    await asyncio.gather(first, second, update, third)
    assert seen == [900, 900, 901]


class CatalogRig(_Rig):
    def __init__(self):
        super().__init__([])
        self.catalog_reads = self.open_reads = 0
        self.fail_refresh = False
        self.slate = POLY_SLATE

    async def read_slate_rows(self):
        self.catalog_reads += 1
        return self.slate[0]

    def get_task_session(self, **kwargs):
        original, rig = super().get_task_session(**kwargs), self

        class Context:
            async def __aenter__(self):
                session = await original.__aenter__()
                execute = session.execute

                async def route(stmt, params=None):
                    if isinstance(stmt, Update):
                        return await execute(stmt, params)
                    sql = str(stmt)
                    if sql == str(admission.open_contract_markets_stmt()):
                        rig.open_reads += 1
                        if rig.fail_refresh and rig.open_reads > 1:
                            raise RuntimeError("bounded transient admission failure")
                        return _Result(
                            [(17, ["open"], None, None, None, "Independent", "0xopen")]
                        )
                    if sql == str(admission.open_contract_outcomes_stmt()):
                        return _Result([(171, 17, "0xopen", False)])
                    if "linked_event_id" in sql:
                        return _Result(await rig.read_slate_rows())
                    if "futures_markets.market_metadata" in sql:
                        return _Result(rig.slate[1])
                    if sql.startswith(
                        "SELECT futures_outcomes.id, futures_outcomes.market_id, futures_outcomes.external_id"
                    ):
                        return _Result(rig.slate[2])
                    return _Result([])

                session.execute = route
                return session

            async def __aexit__(self, *exc):
                return await original.__aexit__(*exc)

        return Context()


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_refresh", [False, True])
@pytest.mark.parametrize("hard_stop", [False, True])
async def test_real_consumer_keeps_open_quotes_and_drains_once_after_refresh(
    monkeypatch, fail_refresh, hard_stop
):
    rig = CatalogRig()
    rig.fail_refresh = fail_refresh
    sockets, subscribed, stop = [], [], asyncio.Event()
    senders = []

    class Socket:
        def __init__(self):
            self.queue, self.closed = asyncio.Queue(), False
            sockets.append(self)

        async def send(self, payload):
            if payload == "PING":
                return
            assets = json.loads(payload)["assets_ids"]
            subscribed.append(tuple(assets))
            if "open" in assets:
                frame = json.dumps(
                    {
                        "event_type": "best_bid_ask",
                        "asset_id": "open",
                        "best_bid": "0.60",
                        "best_ask": "0.64",
                    }
                )

                async def after_refreshes():
                    await until(
                        lambda: (
                            rig.open_reads >= 3
                            if fail_refresh
                            else rig.catalog_reads >= 4
                        )
                    )
                    self.queue.put_nowait(frame)
                    # The real reader handles this already-delivered frame
                    # before stop closes its socket and drains the buffer.
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)
                    stop.set()

                senders.append(asyncio.create_task(after_refreshes()))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.closed = True

    class Refresher(blend.LiveBlendRefresher):
        async def refresh(self, *args, **kwargs):
            return None

        async def refresh_pending(self, **kwargs):
            return None

    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.04)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    if hard_stop:
        owner = asyncio.create_task(task._run_polymarket_ws_consumer())
        await asyncio.wait_for(stop.wait(), 5)
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
        stats = None
    else:
        stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 5)
    await asyncio.gather(*senders)
    assert subscribed.count(("open",)) == 1
    assert rig.catalog_reads >= 3
    if fail_refresh:
        if stats is not None:
            assert stats.get("catalog_refreshes", 0) == 0
    else:
        if stats is not None:
            assert stats["catalog_refreshes"] >= 2
        assert subscribed.count(("111", "222")) == 1
    assert rig.writes == [(171, pytest.approx(0.62))]
    if stats is not None:
        assert stats["final_flush_dropped"] == 0
    assert all(sock.closed for sock in sockets)
    _assert_one_lent_engine(rig, "polymarket")
    _assert_disposed_once_after_last_session(rig, "polymarket")


@pytest.mark.asyncio
@pytest.mark.parametrize("client_exit_during_refresh", [False, True])
async def test_game_socket_retains_reordered_catalog_then_restarts_and_drains(
    monkeypatch, client_exit_during_refresh,
):
    def slate(mid, yes_oid, no_oid, condition, tokens, event):
        return [
            [
                (yes_oid, mid, f"{condition}_yes", condition, event),
                (no_oid, mid, f"{condition}_no", condition, event),
            ],
            [(mid, condition, {"clob_token_ids": tokens})],
            [(yes_oid, mid, f"{condition}_yes"), (no_oid, mid, f"{condition}_no")],
        ]

    class Rig(CatalogRig):
        def __init__(self):
            super().__init__()
            self.gates = {n: asyncio.Event() for n in (4, 5, 6)}

        async def read_slate_rows(self):
            self.catalog_reads += 1
            n = self.catalog_reads
            if n in self.gates:
                await self.gates[n].wait()
            if n <= 2:
                self.slate = POLY_SLATE
            elif n == 3 or (n == 4 and client_exit_during_refresh):
                self.slate = slate(7, 81, 82, "0xabc", ["222", "111"], 900)
            elif n == 4:
                self.slate = slate(8, 91, 92, "0xnew", ["333", "444"], 901)
            else:
                self.slate = [[], [], []]
            return self.slate[0]

    rig, sockets, stop = Rig(), [], asyncio.Event()

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.closed = False
            self.assets, self.owner, self.ack = None, None, None
            sockets.append(self)

        async def send(self, payload):
            if payload != "PING":
                self.assets = tuple(json.loads(payload)["assets_ids"])
                self.owner = asyncio.current_task()

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.ack is not None:
                self.ack.set()
                self.ack = None
            return await self.queue.get()

        async def quote(self, token, bid, ask):
            ack = self.ack = asyncio.Event()
            self.queue.put_nowait(json.dumps({
                "event_type": "best_bid_ask", "asset_id": token,
                "best_bid": bid, "best_ask": ask,
            }))
            await asyncio.wait_for(ack.wait(), 5)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.closed = True

    class Refresher(blend.LiveBlendRefresher):
        async def refresh(self, *args, **kwargs):
            return None

        async def refresh_pending(self, **kwargs):
            return None

    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.02)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    owner = asyncio.create_task(task._run_polymarket_ws_consumer(stop=stop))
    try:
        # Read 4 is held: both the unchanged and reordered refresh completed.
        await until(lambda: rig.catalog_reads == 4)
        games = [sock for sock in sockets if sock.assets != ("open",)]
        assert len(games) == 1
        first = games[0]
        assert first.assets == ("111", "222")
        assert not first.closed and not first.owner.done()
        # The retained reader uses the NEW outcome routing, not its initial map.
        await first.quote("111", "0.60", "0.64")
        if client_exit_during_refresh:
            first.owner.cancel()
            await asyncio.gather(first.owner, return_exceptions=True)
            rig.gates[4].set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(owner, 5)
            stats = None
        else:
            rig.gates[4].set()
            await until(lambda: rig.catalog_reads == 5)
            await until(lambda: any(sock.assets == ("333", "444") for sock in sockets))
            second = next(sock for sock in sockets if sock.assets == ("333", "444"))
            assert first.closed and first.owner.done()
            assert second.owner is not first.owner and not second.closed
            await second.quote("333", "0.70", "0.74")
            rig.gates[5].set()
            await until(lambda: rig.catalog_reads == 6)
            assert second.closed and second.owner.done()
            assert len(sockets) == 3  # two game subscriptions plus one retained open
            assert all(sock.assets for sock in sockets)  # empty never means all markets
            stop.set()
            rig.gates[6].set()
            stats = await asyncio.wait_for(owner, 5)
    finally:
        owner.cancel()
        await asyncio.gather(owner, return_exceptions=True)
    expected = [(82, pytest.approx(0.62))]
    if client_exit_during_refresh:
        assert len(sockets) == 2  # a dead game client is never silently retained
    else:
        expected.append((91, pytest.approx(0.72)))
        assert stats["final_flush_dropped"] == 0
    assert sorted(rig.writes) == expected
    assert all(sock.closed and sock.owner.done() for sock in sockets)
    _assert_one_lent_engine(rig, "polymarket")
    _assert_disposed_once_after_last_session(rig, "polymarket")
