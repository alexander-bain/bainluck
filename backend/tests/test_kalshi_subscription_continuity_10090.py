"""Healthy Kalshi clients retain quotes/callbacks across full routine refreshes.

#10090 changed-scope continuity: a mapping-only change (event, outcome, open
contract or bridge) is now applied in place on the same connections; policy
switches, ended clients, admission misses and stops keep their old paths.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import websockets

import app.services.kalshi_ws as service
import app.tasks.kalshi_ws as task
import app.tasks.live_blend_refresh as blend
import app.tasks.ws_admission as admission
import app.tasks.ws_open_contracts as opened


GAME = "KXNFLGAME-26OCT08SFLAR-SF"
OPEN = "KXNFLGAME-26OCT09NYGBUF-NYG"
STORED = datetime(2026, 10, 8, tzinfo=timezone.utc)
IN_PLACE = {"event_map", "outcome_map", "open_map", "bridge"}


class Result:
    rowcount = 0

    def __init__(self, rows=()):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def scalars(self):
        return self


class Scope:
    def __init__(self):
        self.change = None
        self.fail_next = False
        self.failed = asyncio.Event()
        self.refreshed = asyncio.Queue()
        self.linked_reads = self.open_reads = self.bridge_reads = 0
        self.active = 0
        self.written = {}
        self.pending_started = asyncio.Event()
        self.pending_cancelled = False

    @asynccontextmanager
    async def session(self):
        self.active += 1
        try:
            yield self
        finally:
            self.active -= 1

    async def execute(self, statement, *_args):
        columns = [str(c) for c in getattr(statement, "selected_columns", ())]
        if columns and "win_probability_sources" in " ".join(columns):
            if len(columns) == 3:
                rows = [(900, 7, None)]
                if self.change == "admission":
                    rows.append((902, 9, None))
                return Result(rows)
            return Result()  # blend's DB is outside this socket lifetime control
        if columns == ["futures_markets.external_id", "futures_markets.id", "futures_markets.event_id"]:
            self.linked_reads += 1
            if self.fail_next:
                self.fail_next = False
                self.failed.set()
                raise RuntimeError("one failed scope reread")
            return Result([(GAME.rsplit("-", 1)[0], 7,
                            903 if self.change == "event_map" else 900)])
        if columns == ["futures_outcomes.external_id", "futures_outcomes.market_id", "futures_outcomes.id"]:
            return Result([(GAME, 7, 72 if self.change == "outcome_map" else 71)])
        if columns and columns[0] == "futures_outcomes.external_id":
            self.open_reads += 1
            if self.change == "initial_pending":
                self.pending_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.pending_cancelled = True
                    raise
            return Result([(OPEN, 8, 82 if self.change == "open_map" else 81,
                            901, OPEN.rsplit("-", 1)[0])])
        if columns == ["events.id"]:
            self.bridge_reads += 1
            self.refreshed.put_nowait(self.bridge_reads)
            return Result([] if self.change == "bridge" else [901])
        return Result()  # same existing lock/rank statements, no unrelated DB work


class Prices(task._KalshiPriceOwner):
    # #10090: the run's stamp state and `join_stamp` are the real owner's.
    def __init__(self, scope):
        super().__init__()
        self.scope = scope
        self.lock_retry_until = {}
        self.committed_outcome_ids = set()

    async def phase(self, session, values, *, force_observation=False):
        self.scope.written.update(values)
        rows = [SimpleNamespace(id=oid, market_id=7 if oid in (71, 72) else 8,
                                quote_moved=False, last_updated=STORED)
                for oid in values]
        yield SimpleNamespace(attempted=len(rows), rowcount=len(rows), all=lambda: rows)


class Socket:
    def __init__(self):
        self.inbox = asyncio.Queue()
        self.processed = asyncio.Event()
        self.commands = []
        self.closed = False
        self.previous = False

    async def send(self, raw):
        self.commands.append(json.loads(raw))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.previous:
            self.processed.set()
        raw = await self.inbox.get()
        self.previous = True
        return raw

    async def deliver(self, kind, payload):
        self.processed.clear()
        await self.inbox.put(json.dumps({"type": kind, "msg": payload}))
        await asyncio.wait_for(self.processed.wait(), 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "event_map", "outcome_map", "open_map", "bridge", "channels",
    "open_prices", "open_ended", "admission", "stop", "initial_pending",
])
async def test_real_clients_keep_latest_inputs_until_scope_change_or_final_stop(monkeypatch, change):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "control")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "control")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "1")
    monkeypatch.delenv("WS_KALSHI_TRACE_TICKERS", raising=False)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 2 if change == "initial_pending" else 0.02)
    monkeypatch.setattr(task, "kalshi_flush_cadence", lambda: (1000, 2, None, 4))
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 0.01)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", 0)
    monkeypatch.setattr(service, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(service, "_sign_ws_request", lambda *_: {})
    monkeypatch.setattr("app.tasks.ws_liveness.report", lambda *_args, **_kw: None)
    clients, sockets = [], []
    connected = asyncio.Event()

    class TrackingClient(service.KalshiWebSocket):
        async def run(self, *args, **kwargs):
            self.owner = asyncio.current_task()
            self.targets = kwargs["market_tickers"]
            clients.append(self)
            return await super().run(*args, **kwargs)

    @asynccontextmanager
    async def connect(*_args, **_kwargs):
        socket = Socket()
        sockets.append(socket)
        if len(sockets) == (1 if change == "initial_pending" else 2):
            connected.set()
        try:
            yield socket
        finally:
            socket.closed = True

    monkeypatch.setattr(service, "KalshiWebSocket", TrackingClient)
    monkeypatch.setattr(websockets, "connect", connect)
    graded = asyncio.Event()

    async def grade(_session, **kwargs):
        assert kwargs["outcome_id"] == 81
        graded.set()
        return None, None

    async def publish(_self, _session):
        return 0

    monkeypatch.setattr(opened, "grade_open_contract_leg", grade)
    monkeypatch.setattr(blend.LiveBlendRefresher, "publish_market_changes", publish)
    scope = Scope()
    if change == "initial_pending":
        scope.change = change
    # Run the actual consumer body/service/dispatch. Only external resources and
    # the price driver's RETURNING rows are doubled; ownership wrappers are separate.
    running = asyncio.create_task(task._run_kalshi_ws_consumer.__wrapped__.__wrapped__(
        sessions=scope, prices=Prices(scope),
    ))
    try:
        await asyncio.wait_for(connected.wait(), 10)
        game = next(s for s in sockets if s.commands[0]["params"]["market_tickers"] == [GAME])
        if change == "initial_pending":
            await asyncio.wait_for(scope.pending_started.wait(), 30)
            await game.deliver("ticker", {"market_ticker": GAME, "price_dollars": "0.80"})
            stats = await asyncio.wait_for(running, 30)
            assert stats["status"] == "resubscribe"
            assert stats["recycle_reason"] == "scope"
            assert stats["final_flush_dropped"] == stats["errors"] == stats["loops_unreaped"] == 0
            assert scope.pending_cancelled and scope.active == 0
            assert scope.written[71][0] == 0.8
            assert len(clients) == len(sockets) == 1
            assert all(socket.closed for socket in sockets)
            assert all(client.owner.done() for client in clients)
            assert not any(t.get_name() in {
                "kalshi-flush-loop", "kalshi-stats-loop", "kalshi-subscription-lifetime",
            } for t in asyncio.all_tasks() if not t.done())
            return
        other = next(s for s in sockets if s is not game)
        await game.deliver("ticker", {"market_ticker": GAME, "price_dollars": "0.60"})
        assert await asyncio.wait_for(scope.refreshed.get(), 10) == 1  # initial admission
        assert await asyncio.wait_for(scope.refreshed.get(), 10) == 2  # full periodic scope
        assert len(clients) == len(sockets) == 2 and not running.done()
        assert all(not socket.closed for socket in sockets)
        scope.fail_next = True
        await asyncio.wait_for(scope.failed.wait(), 10)
        assert await asyncio.wait_for(scope.refreshed.get(), 10) >= 3  # failure recovered
        assert len(clients) == 2 and all(not socket.closed for socket in sockets)
        await game.deliver("ticker", {"market_ticker": GAME, "price_dollars": "0.80"})
        await other.deliver("ticker", {"market_ticker": OPEN, "price_dollars": "0.75"})
        await other.deliver("market_lifecycle_v2", {
            "market_ticker": OPEN, "status": "determined", "result": "yes",
        })
        await asyncio.wait_for(graded.wait(), 10)
        if change == "channels":
            monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        elif change == "open_prices":
            monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
        elif change == "open_ended":
            next(c for c in clients if c.targets == [OPEN]).owner.cancel()
        elif change == "stop":
            running.cancel()
        elif change in IN_PLACE:
            scope.change = change
            reads = scope.bridge_reads
            for _ in range(1000):  # one refresh applies it, the next keeps it
                if scope.bridge_reads >= reads + 2:
                    break
                await asyncio.sleep(0.01)
            assert not running.done()
            assert len(clients) == len(sockets) == 2
            assert all(not socket.closed for socket in sockets)
            if change == "outcome_map":
                await game.deliver("ticker", {"market_ticker": GAME, "price_dollars": "0.85"})
            elif change == "open_map":
                await other.deliver("ticker", {"market_ticker": OPEN, "price_dollars": "0.77"})
            # A policy switch still ends the run through the full rebuild.
            monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        else:
            scope.change = change
        if change == "stop":
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(running, 10)
        else:
            stats = await asyncio.wait_for(running, 10)
            assert stats["status"] == "resubscribe"
            assert stats["recycle_reason"] == ("admission" if change == "admission" else "scope")
            assert stats["final_flush_dropped"] == stats["errors"] == stats["loops_unreaped"] == 0
            if change in IN_PLACE:
                assert stats["scope_in_place"] == 1
                assert (stats["clients_kept"], stats["clients_replaced"],
                        stats["clients_started"], stats["clients_retired"]) == (2, 0, 0, 0)
        if change == "outcome_map":
            assert scope.written[72][0] == 0.85  # the new mapping, same connection
        if change == "open_map":
            assert scope.written[82][0] == 0.77
        assert scope.written[71][0] == 0.8  # no buffer reset during unchanged refreshes
        assert scope.written[81][0] == 0.75
        assert all(socket.closed for socket in sockets) and scope.active == 0
        assert all(client.owner.done() for client in clients)
        assert not any(t.get_name() in {
            "kalshi-flush-loop", "kalshi-stats-loop", "kalshi-subscription-lifetime",
        } for t in asyncio.all_tasks() if not t.done())
    finally:
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)
