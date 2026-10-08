"""Execute the shipped PM write/flush while a committed MARKET ACK is held."""

import ast
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions, rig
from tests.test_pm_pipelined_stamps_10090 import held_refresher, settle

pytestmark = pytest.mark.asyncio


def market_rig(**kwargs):
    r = rig(**kwargs)
    r.ns["market_by_outcome"] = {oid: oid + 100 for oid in r.ns["price_buffer"]}
    r.ns["chunk_price_update_stmt"] = lambda chunk: ("prices", dict(chunk))
    committed, notified = [], []

    class Session:
        rows = ()

        async def execute(self, stmt):
            if isinstance(stmt, tuple) and stmt[0] == "prices":
                self.rows = tuple(stmt[1])
                r.trace.append(("write", list(self.rows)))
                return SimpleNamespace(all=lambda: [
                    SimpleNamespace(id=oid, market_id=oid + 100, ord=i,
                                    quote_moved=True, last_updated=1000 + oid)
                    for i, oid in enumerate(self.rows)
                ])
            return SimpleNamespace(rowcount=1)

    @asynccontextmanager
    async def session():
        s = Session()
        yield s
        committed.extend(s.rows)
        r.trace.append(("commit", list(s.rows)))

    r.ns["get_task_session"] = session
    r.ns["queue_market_change"] = lambda session, **fields: notified.append(fields)
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], r.ns)
    r.committed, r.notified = committed, notified
    return r


def hold_market(r, *, before_wait=None):
    entered, release = asyncio.Event(), asyncio.Event()
    published = []

    async def publish(session):
        published.append(session.rows)
        r.trace.append(("market", list(session.rows)))
        if session.rows == (1, 2):
            entered.set()
            if before_wait is not None:
                before_wait()
            await release.wait()  # the writer's actual awaited MARKET boundary

    r.ns["blend_refresher"].publish_market_changes = publish
    return entered, release, published


async def test_ready_event_finishes_while_committed_market_ack_is_held():
    r = market_rig(books={})
    gate, calls = held_refresher(r)
    gate.set()
    entered, release, published = hold_market(r)
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await settle(r, lambda: calls["finished"] == [(10,)])
        assert calls["finished"] == [(10,)]
        assert r.committed == [1, 2]
        assert set(r.ns["price_buffer"]) == {1, 2, 900}
        assert not flush.done()
        release.set()
        assert await asyncio.wait_for(flush, 1) is True
    finally:
        release.set()
        await asyncio.gather(flush, return_exceptions=True)
    assert published == [(1, 2), (900,)]
    assert calls["started"] == [(10,), (90,)]
    assert calls["most_running"] == 1
    assert r.marks == [1, 2, 900]
    assert not r.ns["price_buffer"]
    assert [x["outcome_observed_at"] for x in r.notified] == [{1: 1001}, {2: 1002}, {900: 1900}]


async def test_control_original_market_first_boundary_holds_event_refresh():
    r = market_rig(books={})
    gate, calls = held_refresher(r)
    gate.set()
    # Put just the callback after the awaited MARKET publication: the original
    # blocking dependency, with transaction/planner/receipt logic unchanged.
    tree = ast.parse((ROOT / "app/tasks/polymarket_ws.py").read_text())
    (node,) = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
               and n.name == "write_chunk"]
    (boundary,) = [n for n in node.body if isinstance(n, ast.Try)
                   and n.finalbody and "publish_market_changes" in ast.unparse(n.finalbody[0])]
    (callback,) = boundary.body
    boundary.body = [ast.Pass()]
    pos = node.body.index(boundary)
    node.body.insert(pos + 1, callback)
    ast.fix_missing_locations(node)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "market_first", "exec"), r.ns)
    entered, release, _ = hold_market(r)
    flush = asyncio.create_task(r.ns["flush_prices"]())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await settle(r, lambda: False, turns=20)
        assert calls["started"] == []
        assert r.committed == [1, 2]
        release.set()
        assert await asyncio.wait_for(flush, 1)
    finally:
        release.set()
        await asyncio.gather(flush, return_exceptions=True)


async def test_cancel_at_market_ack_joins_stamp_and_keeps_committed_debt():
    r = market_rig(books={})
    _, calls = held_refresher(r)
    entered, release, published = hold_market(r)
    flush = asyncio.create_task(r.ns["flush_prices"]())
    await asyncio.wait_for(entered.wait(), 1)
    await settle(r, lambda: calls["started"] == [(10,)])
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 1)
    assert calls["cancelled"] == [(10,)] and calls["running"] == 0
    assert set().union(*calls["adopted"]) == {10}
    assert r.ns["blend_refresher"].pending_event_ids() == frozenset({10})
    assert published == [(1, 2)] and r.committed == [1, 2]
    assert set(r.ns["price_buffer"]) == {1, 2, 900}


async def test_cancel_before_refresh_first_turn_still_adopts_committed_event():
    r = market_rig(books={})
    _, calls = held_refresher(r)
    published = []

    async def cancel_before_yield(session):
        published.append(session.rows)
        raise asyncio.CancelledError

    r.ns["blend_refresher"].publish_market_changes = cancel_before_yield
    with pytest.raises(asyncio.CancelledError):
        await r.ns["flush_prices"]()
    assert calls["started"] == [] and calls["running"] == 0
    assert calls["adopted"] == [{10}]
    assert published == [(1, 2)] and r.committed == [1, 2]
    assert set(r.ns["price_buffer"]) == {1, 2, 900}


async def test_withdrawal_cohort_still_waits_for_its_original_cleanup():
    r = market_rig()  # event10 has a pending held-price withdrawal
    gate, calls = held_refresher(r)
    gate.set()
    entered, release, _ = hold_market(r)
    flush = asyncio.create_task(r.ns["flush_prices"]())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await settle(r, lambda: False, turns=20)
        assert calls["started"] == []
        assert ("withdraw", [1]) not in r.trace
        release.set()
        assert await asyncio.wait_for(flush, 1)
        assert r.trace.index(("withdraw", [1])) < r.trace.index(("refresh", [10]))
        assert calls["most_running"] == 1
    finally:
        release.set()
        await asyncio.gather(flush, return_exceptions=True)


async def test_late_bridge_stages_only_new_event_receipt():
    r = market_rig(books={}, mapping={1: 10, 900: 90})
    gate, calls = held_refresher(r)
    gate.set()
    entered, release, _ = hold_market(r)
    flush = asyncio.create_task(r.ns["flush_prices"]())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await settle(r, lambda: calls["finished"] == [(10,)])
        r.ns["event_id_by_outcome"][2] = 20
        release.set()
        assert await asyncio.wait_for(flush, 1)
        assert calls["started"] == [(10,), (20,), (90,)]
        assert calls["most_running"] == 1
        assert r.marks == [1, 2, 2, 900]
    finally:
        release.set()
        await asyncio.gather(flush, return_exceptions=True)


async def test_standalone_default_keeps_market_wait_and_does_not_refresh():
    r = market_rig(batch={900: 0.1}, books={}, mapping={1: 10})
    _, calls = held_refresher(r)
    entered, release = asyncio.Event(), asyncio.Event()

    async def publish(session):
        assert session.rows == (900,)
        entered.set()
        await release.wait()

    r.ns["blend_refresher"].publish_market_changes = publish
    flush = asyncio.create_task(r.ns["flush_standalone"]())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert calls["started"] == [] and r.ns["price_buffer"] == {900: 0.1}
        release.set()
        assert await asyncio.wait_for(flush, 1)
        assert calls["started"] == [] and r.marks == []
        assert not r.ns["price_buffer"]
    finally:
        release.set()
        await asyncio.gather(flush, return_exceptions=True)


async def test_handback_error_still_awaits_market_then_propagates_real_error():
    r = market_rig(books={})
    held_refresher(r)
    entered, release, published = hold_market(r)

    def broken_handback():
        raise RuntimeError("handback failed")

    write = asyncio.create_task(r.ns["write_chunk"](
        {1: 0.6, 2: 0.4}, after_commit=broken_handback,
    ))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert r.committed == [1, 2] and published == [(1, 2)]
        assert not write.done()
        release.set()
        with pytest.raises(RuntimeError, match="handback failed"):
            await asyncio.wait_for(write, 1)
        assert set(r.ns["price_buffer"]) == {1, 2, 900}
    finally:
        release.set()
        await asyncio.gather(write, return_exceptions=True)
