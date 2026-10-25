"""Actual PM consumer startup sequencing; no network, no source mutation."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import websockets
from app.tasks import polymarket_ws as task
from app.tasks import polymarket_token_topup as topup
from app.services import polymarket_ws as service
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig, until
from tests.test_ws_consumer_session_lifetime_2471 import (
    _install, _assert_one_lent_engine, _assert_disposed_once_after_last_session,
)
from tests.test_ws_flush_retry_q491 import _Result
from tests._pm_slate_market_read_10663 import answer_slate_market_read
from tests._pm_slate_link_read_10663 import answer_slate_link_read


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["normal", "gamma_failure", "cancel_full", "cancel_market", "cancel_outcome", "buffered", "no_stored_live", "unaddressable", "mixed_stored_sibling"])
async def test_stored_live_startup_pair(monkeypatch, mode):
    arm = os.environ.get("ATTEMPT156_ARM", "candidate")  # the lab can still run the parent arm
    candidate = arm.startswith("candidate")
    expect_early = candidate and mode != "no_stored_live"
    marks = []
    gates = {name: (asyncio.Event(), asyncio.Event()) for name in
             ("full_slate", "market_gamma", "outcome_gamma")}
    subscribed = asyncio.Event()
    subscriptions, clients, sockets = [], [], []
    # Lower binary id is side1: orientation cannot be inferred from row order.
    outcomes = [(70, 7, "0xabc_side1"), (71, 7, "0xabc"),
                (80, 8, "0xpa"), (81, 8, "0xpb"), (82, 8, "0xpc"),
                (90, 9, "0xscheduled"), (91, 9, "0xscheduled_side1"),
                (100, 10, "0xmissing"), (110, 11, "0xnew"),
                (120, 12, "0xsuspended"), (121, 12, "0xsuspended_side1")]
    parent_metadata = {"clob_yes_token_by_outcome": {"80": "pa", "81": "pb", "82": "pc"}}
    metadata = [(7, "0xabc", {"clob_token_ids": ["111", "222"]}, "live"),
                (8, "917153", parent_metadata, "live"),
                (9, "0xscheduled", {"clob_token_ids": ["s1", "s2"]}, "scheduled"),
                (10, "917154", {}, "live"),
                (11, "0xnew", {}, "scheduled"),
                (12, "0xsuspended", {"clob_token_ids": ["u1", "u2"]}, "suspended")]
    if mode == "mixed_stored_sibling":
        outcomes.append((83, 8, "not-a-condition"))
        parent_metadata["clob_yes_token_by_outcome"]["83"] = "pd"
    if mode == "unaddressable":
        outcomes.append((130, 13, "not-a-condition"))
        metadata.append((13, "917155", {"clob_yes_token_by_outcome": {"130": "invalid"}}, "live"))
    if mode == "no_stored_live":
        metadata = [(mid, ext, data, "scheduled") for mid, ext, data, status in metadata]
    live_markets = {mid for mid, ext, data, status in metadata if status in {"live", "suspended"}}
    market_ext = {mid: ext for mid, ext, *_ in metadata}
    slate = [[(oid, mid, ext, market_ext[mid], 900 + mid) for oid, mid, ext in outcomes],
             metadata, outcomes]

    async def gate(name):
        entered, release = gates[name]
        marks.append(name + ":entered")
        entered.set()
        await release.wait()
        marks.append(name + ":released")

    class Rig(CatalogRig):
        async def read_slate_rows(self):
            self.catalog_reads += 1
            assert self.catalog_reads == 1, "no catalog recycle belongs in this startup test"
            await gate("full_slate")
            return self.slate[0]

        def get_task_session(self, **kwargs):
            original = super().get_task_session(**kwargs)
            class Context:
                async def __aenter__(inner):
                    session = await original.__aenter__()
                    execute = session.execute
                    async def route(stmt, params=None):
                        sql = str(stmt)
                        bound = stmt.compile().params
                        selected = next((set(value) for value in bound.values()
                                         if isinstance(value, (list, tuple))
                                         and all(isinstance(v, int) for v in value)), None)
                        if "linked_event_id" in sql and any(
                            isinstance(value, (list, tuple)) and set(value) == {"live", "suspended"}
                            for value in bound.values()):
                            marks.append("stored_live_select")
                            return _Result(answer_slate_link_read(  # #10663
                                stmt, [row for row in slate[0] if row[1] in live_markets]))
                        if "linked_event_id" in sql:
                            return await execute(stmt, params)
                        # UPDATE RETURNING also contains this function; only
                        # the standalone clock read returns a scalar result.
                        if sql.startswith("SELECT clock_timestamp()"):
                            return SimpleNamespace(scalar_one=lambda: datetime.now(timezone.utc))
                        if "futures_markets.market_metadata" in sql and "LEFT OUTER JOIN" in sql:
                            return _Result([(8, parent_metadata, datetime.now(timezone.utc), "live"),
                                            (10, {}, datetime.now(timezone.utc), "live"),
                                            (11, {}, datetime.now(timezone.utc), "scheduled")])
                        if sql.startswith("SELECT futures_outcomes.id, futures_outcomes.name"):
                            return _Result([(100, "Missing"), (110, "New")])
                        if "futures_markets.market_metadata" in sql:
                            assert selected is not None
                            return _Result(answer_slate_market_read(
                                stmt, [row for row in metadata if row[0] in selected]))
                        if sql.startswith("SELECT futures_outcomes.id, futures_outcomes.market_id, futures_outcomes.external_id"):
                            assert selected is not None
                            return _Result([row for row in outcomes if row[1] in selected])
                        return await execute(stmt, params)
                    session.execute = route
                    return session
                async def __aexit__(inner, *exc):
                    return await original.__aexit__(*exc)
            return Context()

    class Gamma:
        async def get_markets_by_conditions(self, ids):
            assert set(ids) == {"0xmissing", "0xnew"}, "stored parent legs must not be re-asked"
            await gate("outcome_gamma")
            if mode == "gamma_failure":
                raise RuntimeError("controlled Gamma failure")
            return []  # The missing token remains missing; all known legs survive.

    class MarketGamma:
        async def get_markets_by_conditions(self, ids):
            assert ids == ["0xnew"], "only the unstored addressable market reaches Gamma"
            await gate("market_gamma")
            if mode == "gamma_failure":
                raise RuntimeError("controlled Gamma failure")
            return []

    original_outcome_topup = topup.topup_outcome_clob_tokens
    original_market_topup = topup.topup_clob_tokens
    async def market_topup(session, markets, **kwargs):
        return await original_market_topup(session, markets, service=MarketGamma(), **kwargs)
    async def outcome_topup(session, targets):
        return await original_outcome_topup(session, targets, service=Gamma())

    class Client(service.PolymarketWebSocket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            clients.append(self)

    class Socket:
        def __init__(self):
            self.queue, self.closed = asyncio.Queue(), False
            sockets.append(self)
        async def send(self, payload):
            if payload == "PING":
                return
            subscriptions.append(json.loads(payload)["assets_ids"])
            marks.append("subscribe")
            subscribed.set()
        def __aiter__(self):
            return self
        async def __anext__(self):
            return await self.queue.get()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            self.closed = True

    rig, stop = Rig(), asyncio.Event()
    rig.slate = slate
    _install(monkeypatch, rig)
    monkeypatch.setattr(service, "PolymarketWebSocket", Client)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(topup, "topup_clob_tokens", market_topup)
    monkeypatch.setattr(topup, "topup_outcome_clob_tokens", outcome_topup)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 3600)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 3600)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.delenv("PM_WS_GAME_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "0")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
    write_release = asyncio.Event()
    if mode == "buffered":
        original_flushing = task._PMCatalogFlushBoundary.flushing
        @asynccontextmanager
        async def gated_flushing(boundary, **kwargs):
            await write_release.wait()
            async with original_flushing(boundary, **kwargs):
                yield
        monkeypatch.setattr(task._PMCatalogFlushBoundary, "flushing", gated_flushing)
    owner = asyncio.create_task(task._run_polymarket_ws_consumer(stop=stop))
    result = mapping = initial_socket_retained = None
    initial_tokens = {"111", "222", "pa", "pb", "pc", "u1", "u2"}
    if mode == "mixed_stored_sibling":
        initial_tokens.add("pd")
    final_tokens = initial_tokens | {"s1", "s2"}
    def received():
        return set().union(*(set(s) for s in subscriptions)) if subscriptions else set()
    try:
        for name in ("full_slate", "market_gamma", "outcome_gamma"):
            await asyncio.wait_for(gates[name][0].wait(), 5)
            if expect_early:
                await asyncio.wait_for(subscribed.wait(), 5)
                assert received() == initial_tokens, (name, subscriptions)
                marks.append(name + ":stored_live_subscribed")
            else:
                assert not subscribed.is_set(), name
                assert not subscriptions, name
                marks.append(name + ":subscribe_absent")
            assert not owner.done(), name
            if expect_early and mode == "buffered" and name == "full_slate":
                await clients[0].on_price({"asset_id": "111", "best_bid": "0.60", "best_ask": "0.64"})
                marks.append("accepted_price_before_full_slate")
                assert rig.writes == []
            if mode == "cancel_" + name.split("_")[0]:
                owner.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(owner, 5)
                marks.append("cancelled_at:" + name)
                assert all(s.closed for s in sockets)
                _assert_disposed_once_after_last_session(rig, "polymarket")
                return
            gates[name][1].set()
        await until(lambda: received() == final_tokens)
        assert len(subscriptions) == (2 if expect_early else 1)
        initial_socket_retained = not sockets[0].closed
        handler = clients[0].on_price
        closure = dict(zip(handler.__code__.co_freevars, (c.cell_contents for c in handler.__closure__)))
        targets = closure["_tick_targets"]
        mapping = {token: targets(token)[0] for token in final_tokens}
        expected_mapping = {"111": 71, "222": 70, "pa": 80, "pb": 81, "pc": 82,
                            "s1": 90, "s2": 91, "u1": 120, "u2": 121}
        if mode == "mixed_stored_sibling":
            expected_mapping["pd"] = 83
        assert mapping == expected_mapping
        assert initial_socket_retained, "stored live socket must survive full game handover"
        if mode == "buffered":
            if not expect_early:
                await clients[0].on_price({"asset_id": "111", "best_bid": "0.60", "best_ask": "0.64"})
            assert closure["price_buffer"] == {71: pytest.approx(0.62)}
            mark_input = closure["_mark_input"]
            mark_closure = dict(zip(mark_input.__code__.co_freevars, (c.cell_contents for c in mark_input.__closure__)))
            assert mark_closure["event_id_by_outcome"][71] == 907
            marks.append("accepted_price_and_owner_retained_after_handover")
            write_release.set()
        stop.set()
        result = await asyncio.wait_for(owner, 5)
        assert result["assets_mapped"] == len(final_tokens)
        assert result["moneyline_legs_subscribed"] == (4 if mode == "mixed_stored_sibling" else 3)
        assert result["final_flush_dropped"] == 0
        assert rig.writes == ([(71, pytest.approx(0.62))] if mode == "buffered" else [])
        assert all(s.closed for s in sockets)
        _assert_one_lent_engine(rig, "polymarket")
        _assert_disposed_once_after_last_session(rig, "polymarket")
    finally:
        write_release.set()
        for entered, release in gates.values():
            release.set()
        stop.set()
        if not owner.done():
            owner.cancel()
        await asyncio.gather(owner, return_exceptions=True)
        receipts = os.environ.get("ATTEMPT156_RECEIPTS")  # lab receipts only
        receipts and Path(receipts).with_name("receipts-" + mode + ".json").write_text(json.dumps({
            "arm": arm, "mode": mode, "ordered_receipts": marks, "subscriptions": subscriptions,
            "price_writes": rig.writes, "final_mapping": mapping, "initial_socket_retained": initial_socket_retained,
            "stats": result, "all_sockets_closed": all(s.closed for s in sockets),
            "owner_done": owner.done(), "open_sessions": rig.open,
        }, indent=2) + "\n")
