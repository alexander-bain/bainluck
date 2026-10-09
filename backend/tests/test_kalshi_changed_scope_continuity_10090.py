"""#10090 — a changed Kalshi scope is applied in place, not by a full teardown.

Production v5612 (07:04Z): full-scope continuity engaged 0/2 refreshes because
routine populations changed, so every refresh still tore down the game socket
and every open-contract shard. Here one refresh adds a game, removes one open
contract (with a price still buffered for it) and adds another, and the run
keeps streaming: the unaffected shard keeps its exact connection, the emptied
shard retires, the game connection is replaced make-before-break with one
writer per ticker, a settlement both game connections deliver is written once,
and the removed contract's buffered price is still written.
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


GAME_A = "KXNFLGAME-26OCT08SFLAR-SF"
GAME_B = "KXNFLGAME-26OCT09DALPHI-DAL"
OPEN_1 = "KXNFLGAME-26OCT12NYGBUF-NYG"
OPEN_2 = "KXNBAGAME-26OCT20BOSNYK-BOS"
OPEN_3 = "KXNHLGAME-26OCT21TORMTL-TOR"
STORED = datetime(2026, 10, 9, tzinfo=timezone.utc)
MARKET_BY_OUTCOME = {71: 7, 73: 9, 81: 8, 82: 10, 83: 11}


def _event(ticker):
    return ticker.rsplit("-", 1)[0]


class Result:
    rowcount = 0

    def __init__(self, rows=()):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def first(self):
        return None

    def scalars(self):
        return self


class Scope:
    """The DB double: version 1 is the startup scope, version 2 the change."""

    def __init__(self):
        self.version = 1
        self.written = {}
        self.market_settlements = []
        self.active = 0

    @asynccontextmanager
    async def session(self):
        self.active += 1
        try:
            yield self
        finally:
            self.active -= 1

    async def execute(self, statement, *_args):
        text = str(statement)
        if text.startswith("UPDATE futures_markets"):
            self.market_settlements.append(text)
            return Result()
        columns = [str(c) for c in getattr(statement, "selected_columns", ())]
        if columns and "win_probability_sources" in " ".join(columns):
            return Result([(900, 7, None)] if len(columns) == 3 else [])
        if columns == ["futures_markets.external_id", "futures_markets.id",
                       "futures_markets.event_id"]:
            rows = [(_event(GAME_A), 7, 900)]
            if self.version == 2:
                rows.append((_event(GAME_B), 9, 904))
            return Result(rows)
        if columns == ["futures_outcomes.external_id", "futures_outcomes.market_id",
                       "futures_outcomes.id"]:
            rows = [(GAME_A, 7, 71)]
            if self.version == 2:
                rows.append((GAME_B, 9, 73))
            return Result(rows)
        if columns and columns[0] == "futures_outcomes.external_id":
            rows = [(OPEN_1, 8, 81, 901, _event(OPEN_1))]
            rows.append((OPEN_2, 10, 82, None, None) if self.version == 1
                        else (OPEN_3, 11, 83, None, None))
            return Result(rows)
        if columns == ["events.id"]:
            return Result([901])
        return Result()


class Prices:
    def __init__(self, scope):
        self.scope = scope
        self.lock_retry_until = {}
        self.committed_outcome_ids = set()

    async def phase(self, session, values, *, force_observation=False):
        self.scope.written.update(values)
        rows = [SimpleNamespace(id=oid, market_id=MARKET_BY_OUTCOME[oid],
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

    async def close(self):
        if not self.closed:
            self.closed = True
            await self.inbox.put(None)

    def tickers(self):
        return set(self.commands[0]["params"]["market_tickers"])

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.previous:
            self.processed.set()
        raw = await self.inbox.get()
        if raw is None:
            raise StopAsyncIteration
        self.previous = True
        return raw

    async def deliver(self, kind, payload):
        self.processed.clear()
        await self.inbox.put(json.dumps({"type": kind, "msg": payload}))
        await asyncio.wait_for(self.processed.wait(), 10)


async def _until(predicate, what):
    for _ in range(1000):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.mark.asyncio
async def test_changed_scope_keeps_unaffected_connections_and_one_writer_per_ticker(
    monkeypatch,
):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "control")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "control")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "1")
    monkeypatch.delenv("WS_KALSHI_TRACE_TICKERS", raising=False)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
    monkeypatch.setattr(task, "SUCCESSOR_OVERLAP_SECONDS", 1000)
    monkeypatch.setattr(task, "kalshi_flush_cadence", lambda: (1000, 2, None, 4))
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 0.01)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", 0)
    monkeypatch.setattr(service, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(service, "_sign_ws_request", lambda *_: {})
    monkeypatch.setattr("app.tasks.ws_liveness.report", lambda *_args, **_kw: None)
    # One ticker per open connection, so a removal could re-deal every shard.
    original_shards = opened.shard_tickers
    monkeypatch.setattr(opened, "OPEN_CONTRACT_TICKERS_PER_CONNECTION", 1)
    monkeypatch.setattr(opened, "shard_tickers",
                        lambda tickers, per_connection=1: original_shards(tickers, 1))
    sockets = []

    @asynccontextmanager
    async def connect(*_args, **_kwargs):
        socket = Socket()
        sockets.append(socket)
        try:
            yield socket
        finally:
            socket.closed = True

    async def publish(_self, _session):
        return 0

    monkeypatch.setattr(websockets, "connect", connect)
    monkeypatch.setattr(blend.LiveBlendRefresher, "publish_market_changes", publish)
    scope = Scope()
    running = asyncio.create_task(task._run_kalshi_ws_consumer.__wrapped__.__wrapped__(
        sessions=scope, prices=Prices(scope),
    ))

    def socket_for(tickers):
        return next(s for s in sockets if s.commands and s.tickers() == tickers)

    try:
        await _until(lambda: sum(bool(s.commands) for s in sockets) == 3, "startup sockets")
        game_1 = socket_for({GAME_A})
        open_1 = socket_for({OPEN_1})
        open_2 = socket_for({OPEN_2})
        subscribed_1 = list(open_1.commands)
        await game_1.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.60"})
        # Buffered when its contract leaves scope: debt the run still owes.
        await open_2.deliver("ticker", {"market_ticker": OPEN_2, "price_dollars": "0.40"})

        scope.version = 2
        await _until(lambda: sum(bool(s.commands) for s in sockets) == 5, "changed scope")
        assert not running.done()
        game_2 = socket_for({GAME_A, GAME_B})
        open_3 = socket_for({OPEN_3})
        await _until(lambda: open_2.closed, "the emptied shard to retire")
        # The unaffected shard keeps its exact connection and subscription.
        assert not open_1.closed and open_1.commands == subscribed_1
        # Make-before-break: the predecessor keeps its connection meanwhile.
        assert not game_1.closed and not game_2.closed and not open_3.closed

        # The predecessor writes GAME_A until the successor's first frame for it.
        await game_1.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.61"})
        await game_2.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.62"})
        # A late predecessor frame can no longer overwrite the successor's.
        await game_1.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.55"})
        await game_2.deliver("ticker", {"market_ticker": GAME_B, "price_dollars": "0.30"})
        await open_3.deliver("ticker", {"market_ticker": OPEN_3, "price_dollars": "0.20"})
        await open_1.deliver("ticker", {"market_ticker": OPEN_1, "price_dollars": "0.75"})

        # Both game connections deliver the settlement; it is written once.
        settlement = {"market_ticker": GAME_A, "status": "determined", "result": "yes"}
        await game_1.deliver("market_lifecycle_v2", dict(settlement))
        await game_2.deliver("market_lifecycle_v2", dict(settlement))
        await _until(lambda: len(scope.market_settlements) >= 1, "the settlement write")

        monkeypatch.setattr(task, "SUCCESSOR_OVERLAP_SECONDS", 0)
        await _until(lambda: game_1.closed, "the predecessor to retire")
        assert not game_2.closed and not open_1.closed and not open_3.closed

        # A policy switch still takes the full rebuild, and returns stats.
        monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        stats = await asyncio.wait_for(running, 10)
        assert stats["status"] == "resubscribe" and stats["recycle_reason"] == "scope"
        assert stats["scope_in_place"] == 1
        assert (stats["clients_kept"], stats["clients_replaced"],
                stats["clients_started"], stats["clients_retired"]) == (1, 1, 1, 1)
        assert stats["settlements"] == 1 and len(scope.market_settlements) == 1
        assert stats["final_flush_dropped"] == stats["errors"] == stats["loops_unreaped"] == 0
        assert scope.written[71][0] == 0.62
        assert scope.written[73][0] == 0.30
        assert scope.written[82][0] == 0.40  # removed contract's buffered price
        assert scope.written[83][0] == 0.20
        assert scope.written[81][0] == 0.75
        assert all(s.closed for s in sockets) and scope.active == 0
        assert not any(
            t.get_name().startswith("kalshi-") for t in asyncio.all_tasks() if not t.done()
        )
    finally:
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)


@pytest.mark.parametrize("current, scope, per, extra, busy, expected", [
    # Removal only: every connection with a live ticker is kept as it is.
    ([{"A", "B"}, {"C"}], {"A", "C"}, 2, 1, (), ([0, 1], {}, [], [])),
    # ...within the bound: fragmentation past the packed minimum rebuilds.
    ([{"A", "B"}, {"C"}], {"A", "C"}, 2, 0, (), None),
    # One removal does not re-deal: additions fill ONE client with room.
    ([{"A", "B"}, {"C", "D"}], {"A", "C", "D", "E"}, 2, 0, (),
     ([1], {0: frozenset({"A", "E"})}, [], [])),
    # No room: a new connection; an emptied one retires.
    ([{"A"}, {"B"}], {"A", "C"}, 1, 0, (), ([0], {}, [frozenset({"C"})], [1])),
    # The game client takes every addition (and sheds its dead tickers).
    ([{"A", "B"}], {"A", "C"}, None, 0, (), ([], {0: frozenset({"A", "C"})}, [], [])),
    ([], {"A"}, None, 0, (), ([], {}, [frozenset({"A"})], [])),
    # Mid-handoff clients are never replaced or retired: rebuild instead.
    ([{"A"}], {"A", "B"}, None, 0, {0}, None),
    ([{"A"}], {"B"}, None, 0, {0}, None),
    # Beyond the packed minimum plus `extra`: rebuild instead.
    ([{"A"}, {"B"}, {"C"}], {"A", "B", "C", "D"}, 3, 0, (), None),
])
def test_plan_stable_shards(current, scope, per, extra, busy, expected):
    assert task.plan_stable_shards(
        [frozenset(c) for c in current], scope, per, extra, busy,
    ) == expected
