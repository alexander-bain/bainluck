"""Remaining startup handover obligations, using the existing CatalogRig seam."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import websockets
from sqlalchemy.sql.dml import Update

from app.services import polymarket_ws as service
from app.tasks import polymarket_ws as task
from app.tasks import polymarket_open_contracts as admission
from app.tasks import live_blend_refresh as blend
from app.tasks import ws_admission
from app.utils.repair_lock_budget import SET_STATEMENT_TIMEOUT_SQL
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig, until
from tests.test_ws_consumer_session_lifetime_2471 import (
    _install, _assert_one_lent_engine, _assert_disposed_once_after_last_session,
)
from tests.test_ws_flush_retry_q491 import _Result
from tests.pm_bulk_test_support import price_writes, statement_params
from tests._kalshi_price_session import is_price_write, returned
from tests._pm_slate_market_read_10663 import answer_slate_market_read
from tests._pm_slate_link_read_10663 import answer_slate_link_read


def slate(markets):
    """mid, event, condition, tokens -> the existing three-query fixture."""
    rows, metadata, outcomes = [], [], []
    for mid, event, condition, tokens in markets:
        metadata.append((mid, condition, {"clob_token_ids": tokens}, "live"))
        for leg, token in enumerate(tokens):
            oid = mid * 10 + leg
            ext = condition + ("_side1" if leg else "")
            outcomes.append((oid, mid, ext))
            rows.append((oid, mid, ext, condition, event))
    return [rows, metadata, outcomes]


LIVE = slate([(7, 907, "0xabc", ["111", "222"]),
              (9, 909, "0xstable", ["555", "666"])])
FULL = slate([(9, 909, "0xstable", ["555", "666"]),
              (10, 910, "0xnew", ["333", "444"])])


class Rig(CatalogRig):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.initial = LIVE if mode == "transfer" else slate([(7, 907, "0xabc", ["111", "222"])])
        self.full = FULL if mode == "transfer" else slate([(7, 907, "0xabc", ["111", "222"]),
                                                         (10, 910, "0xnew", ["333", "444"])])
        if mode in {"open_only", "no_assets"}:
            self.initial = self.full = [[], [], []]
        self.current = self.initial
        self.full_entered, self.full_release = asyncio.Event(), asyncio.Event()
        self.open_entered, self.open_release = asyncio.Event(), asyncio.Event()
        self.write_release, self.refresh = asyncio.Event(), asyncio.Event()
        self.calls_log = []
        if mode not in {"transfer", "db_failure"}:
            self.full_release.set()
        if mode != "transfer":
            self.open_release.set()
        if mode != "transfer":
            self.write_release.set()

    async def read_full(self):
        self.catalog_reads += 1
        self.calls_log.append(f"full:{self.catalog_reads}:entered")
        self.full_entered.set()
        await self.full_release.wait()
        if self.mode == "db_failure" and self.catalog_reads == 1:
            self.calls_log.append("full:db_failure")
            raise RuntimeError("controlled full-slate database failure")
        self.current = self.full
        self.calls_log.append(f"full:{self.catalog_reads}:returned")
        return self.full[0]

    def get_task_session(self, **kwargs):
        original, rig = super().get_task_session(**kwargs), self
        class Context:
            async def __aenter__(inner):
                session = await original.__aenter__()
                execute = session.execute
                async def route(stmt, params=None):
                    if stmt is task.ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL or (
                        stmt is task.ARM_LOCK_AND_DNPL_PRICE_STATEMENT_TIMEOUT_SQL
                    ):
                        # The recording session's writes are immediate; model
                        # its default timeout for the writer's restore step.
                        return SimpleNamespace(scalar_one=lambda: "0")
                    if stmt is SET_STATEMENT_TIMEOUT_SQL or stmt is task.RESTORE_DNPL_PRICE_TIMEOUTS_SQL:
                        return _Result([])
                    sql, bound = str(stmt), stmt.compile().params
                    if isinstance(stmt, Update):
                        values = statement_params(stmt, params)
                        writes = price_writes(stmt, values)
                        if stmt.table.name == "futures_outcomes" and writes:
                            rig.writes.extend(writes)
                            if is_price_write(stmt):
                                return _Result([returned(oid, quote_moved=False) for oid, value in writes])
                            return _Result([])
                        return await execute(stmt, params)
                    if "clock_timestamp()" in sql:
                        return SimpleNamespace(scalar_one=lambda: datetime.now(timezone.utc))
                    if "linked_event_id" in sql:
                        narrow = any(isinstance(v, (list, tuple)) and set(v) == {"live", "suspended"}
                                     for v in bound.values())
                        if narrow:
                            rig.current = rig.initial
                            rig.calls_log.append("stored_live_select")
                            return _Result(answer_slate_link_read(stmt, rig.initial[0]))  # #10663
                        return _Result(answer_slate_link_read(stmt, await rig.read_full()))
                    if sql == str(admission.open_contract_markets_stmt()):
                        rig.open_reads += 1
                        rig.calls_log.append(f"open:{rig.open_reads}:entered")
                        rig.open_entered.set()
                        await rig.open_release.wait()
                        if rig.mode == "no_assets":
                            return _Result([])
                        if rig.mode == "transfer":
                            return _Result([
                                (7, ["111", "222"], None, None, 907, "Alpha vs Beta", "0xabc"),
                                (17, ["111"], None, None, None, "Mirror", "0xabc"),
                            ])
                        return _Result([(17, ["open"], None, None, None, "Independent", "0xopen")])
                    if "= ANY" in sql and "futures_outcomes" in sql:
                        if rig.mode == "transfer":
                            return _Result([(70, 7, "0xabc", False), (71, 7, "0xabc_side1", False),
                                            (170, 17, "0xabc", False)])
                        return _Result([(170, 17, "0xopen", False)])
                    if sql.startswith("SELECT events.id") and "events.completed_at IS NULL" in sql:
                        return SimpleNamespace(scalars=lambda: _Result([907]))
                    if "futures_markets.market_metadata" in sql:
                        return _Result(answer_slate_market_read(stmt, rig.current[1]))
                    if sql.startswith("SELECT futures_outcomes.id, futures_outcomes.market_id, futures_outcomes.external_id"):
                        return _Result(rig.current[2])
                    return _Result([])
                session.execute = route
                return session
            async def __aexit__(inner, *exc):
                return await original.__aexit__(*exc)
        return Context()


class Scope:
    def __init__(self, monkeypatch, mode):
        self.rig, self.stop = Rig(mode), asyncio.Event()
        self.clients, self.sockets, self.updates = [], [], []
        scope = self
        class Client(service.PolymarketWebSocket):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                scope.clients.append(self)
            def update_asset_ids(self, ids, **kwargs):
                scope.updates.append({"client": scope.clients.index(self), "ids": list(ids),
                                      "preserve": kwargs.get("preserve_existing_shards", False)})
                return super().update_asset_ids(ids, **kwargs)
        class Socket:
            def __init__(self):
                self.queue, self.closed, self.ack = asyncio.Queue(), False, None
                self.assets = None
                scope.sockets.append(self)
            async def send(self, payload):
                if payload != "PING":
                    self.assets = tuple(json.loads(payload)["assets_ids"])
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.ack is not None:
                    self.ack.set()
                    self.ack = None
                return await self.queue.get()
            async def quote(self, token, bid, ask):
                ack = self.ack = asyncio.Event()
                self.queue.put_nowait(json.dumps({"event_type": "best_bid_ask", "asset_id": token,
                                                 "best_bid": str(bid), "best_ask": str(ask)}))
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
        async def watch(*args, **kwargs):
            await scope.rig.refresh.wait()
            scope.rig.refresh.clear()
            return {910}
        original_flushing = task._PMCatalogFlushBoundary.flushing
        @asynccontextmanager
        async def gated_flushing(boundary, **kwargs):
            await scope.rig.write_release.wait()
            async with original_flushing(boundary, **kwargs):
                yield
        _install(monkeypatch, self.rig)
        monkeypatch.setattr(service, "PolymarketWebSocket", Client)
        monkeypatch.setattr(websockets, "connect", lambda *a, **kw: Socket())
        monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
        monkeypatch.setattr(ws_admission, "watch_for_unadmitted_live_events", watch)
        monkeypatch.setattr(task._PMCatalogFlushBoundary, "flushing", gated_flushing)
        monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 3600)
        monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 0.01)
        monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
        monkeypatch.delenv("PM_WS_GAME_FLUSH_SECONDS", raising=False)
        monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
        monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
        monkeypatch.setenv("POLYMARKET_WS_OPEN_RECEIVER_PROCESS", "0")
        self.owner = asyncio.create_task(task._run_polymarket_ws_consumer(stop=self.stop))
        self.result = None

    def callback_state(self):
        handler = self.clients[0].on_price
        state = dict(zip(handler.__code__.co_freevars, (c.cell_contents for c in handler.__closure__)))
        mark = state["_mark_input"]
        state.update(dict(zip(mark.__code__.co_freevars, (c.cell_contents for c in mark.__closure__))))
        return state

    async def socket_for(self, token, *, exclude=None):
        await until(lambda: any(s.assets and token in s.assets and not s.closed and s is not exclude
                                for s in self.sockets))
        return next(s for s in self.sockets if s.assets and token in s.assets and not s.closed and s is not exclude)

    async def finish(self):
        self.rig.full_release.set(); self.rig.open_release.set(); self.rig.write_release.set()
        self.stop.set()
        self.result = await asyncio.wait_for(self.owner, 5)
        _assert_one_lent_engine(self.rig, "polymarket")
        _assert_disposed_once_after_last_session(self.rig, "polymarket")
        assert all(s.closed for s in self.sockets)
        assert self.result.get("loops_unreaped", 0) == 0
        assert self.result.get("final_flush_dropped", 0) == 0

    async def cleanup(self):
        self.rig.full_release.set(); self.rig.open_release.set(); self.rig.write_release.set()
        self.stop.set()
        if not self.owner.done(): self.owner.cancel()
        results = await asyncio.gather(self.owner, return_exceptions=True)
        receipts = os.environ.get("ATTEMPT156_RECEIPTS")  # lab receipts only
        receipts and Path(receipts).with_name("receipts-" + self.rig.mode + ".json").write_text(json.dumps({"mode": self.rig.mode, "calls": self.rig.calls_log,
            "subscriptions": [s.assets for s in self.sockets], "updates": self.updates,
            "writes": self.rig.writes, "result": self.result,
            "all_sockets_closed": all(s.closed for s in self.sockets), "open_sessions": self.rig.open,
            "owner_result": str(results[0]) if isinstance(results[0], BaseException) else "completed"}, indent=2) + "\n")


@pytest.mark.asyncio
async def test_accepted_quote_survives_removal_then_open_owner_and_mirror(monkeypatch):
    s = Scope(monkeypatch, "transfer")
    try:
        old = await s.socket_for("111")
        await old.quote("111", .60, .64)
        state = s.callback_state()
        assert state["price_buffer"] == {70: pytest.approx(.62)}
        assert state["event_id_by_outcome"][70] == 907
        s.rig.full_release.set()
        await asyncio.wait_for(s.rig.open_entered.wait(), 5)
        # Full-game maps are installed but open admission is still held.
        assert state["_tick_targets"]("111") == []
        assert state["price_buffer"] == {70: pytest.approx(.62)}
        assert state["event_id_by_outcome"][70] == 907
        assert not old.closed
        await old.quote("111", .88, .92)
        assert state["price_buffer"] == {70: pytest.approx(.62)}
        await old.quote("555", .80, .84)
        assert state["price_buffer"] == {70: pytest.approx(.62), 90: pytest.approx(.82)}
        s.rig.write_release.set()
        await until(lambda: len(s.rig.writes) == 2 and not state["price_buffer"])
        assert sorted(s.rig.writes) == [(70, pytest.approx(.62)), (90, pytest.approx(.82))]
        s.rig.open_release.set()
        opened = await s.socket_for("111", exclude=old)
        assert state["_tick_targets"]("111") == [70, 170]
        assert state["event_id_by_outcome"][70] == 907
        before = list(s.rig.writes)
        await old.quote("111", .88, .92)  # game socket still has it on wire, fenced out
        assert s.rig.writes == before and not state["price_buffer"]
        await opened.quote("111", .70, .74)
        await until(lambda: len(s.rig.writes) == 5 and not state["price_buffer"])
        assert sorted(s.rig.writes[2:]) == [(70, pytest.approx(.72)), (71, pytest.approx(.28)), (170, pytest.approx(.72))]
        await s.finish()
    finally:
        await s.cleanup()


@pytest.mark.asyncio
async def test_startup_db_failure_keeps_live_then_normal_refresh_keeps_open(monkeypatch):
    s = Scope(monkeypatch, "db_failure")
    try:
        old = await s.socket_for("111")
        await old.quote("111", .60, .64)
        await until(lambda: s.rig.writes == [(70, pytest.approx(.62))])
        s.rig.full_release.set()  # actual loader DB execute raises on its first full read
        opened = await s.socket_for("open")
        assert not old.closed and s.rig.catalog_reads == 1
        await old.quote("111", .70, .74)
        await until(lambda: len(s.rig.writes) == 2)
        s.rig.refresh.set()
        await s.socket_for("333")
        assert s.rig.catalog_reads == 2 and s.rig.open_reads == 2
        assert not opened.closed
        assert all(not update["preserve"] for update in s.updates)
        await opened.quote("open", .50, .54)
        await until(lambda: len(s.rig.writes) == 3)
        assert s.rig.writes == [(70, pytest.approx(.62)), (70, pytest.approx(.72)), (170, pytest.approx(.52))]
        await s.finish()
        assert s.result["catalog_refreshes"] == 1
    finally:
        await s.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["open_only", "no_assets"])
async def test_empty_stored_and_full_slate_fallback(monkeypatch, mode):
    s = Scope(monkeypatch, mode)
    try:
        if mode == "open_only":
            opened = await s.socket_for("open")
            assert all(sock.assets == ("open",) for sock in s.sockets)
            await opened.quote("open", .60, .64)
            await until(lambda: s.rig.writes == [(170, pytest.approx(.62))])
            await s.finish()
            assert s.result["open_contract_assets"] == 1
        else:
            s.result = await asyncio.wait_for(s.owner, 5)
            assert s.result == {"status": "no_markets"}
            assert s.sockets == [] and s.rig.writes == []
            _assert_disposed_once_after_last_session(s.rig, "polymarket")
        assert s.rig.catalog_reads == 1
    finally:
        await s.cleanup()
