"""#10090 — a Polymarket chunk's blend stamp runs while the next chunk writes.

Twin of `test_kalshi_pipelined_stamps_10090`. Executes the shipped
`flush_prices` on the #10651 rig with a refresher whose stamp can be held.
Proves ordering and lifetime, not production latency: the next chunk's write
runs while the previous chunk's stamp is still running; refreshes never overlap
each other; withdrawals still follow the stamp before them; no stamp outlives
its flush, on success or on cancellation.
"""

import ast
import asyncio

import pytest

from tests.test_polymarket_withdrawal_speed_10651 import ROOT, rig

pytestmark = pytest.mark.asyncio

PIPELINED = "stamping = asyncio.create_task(blend_refresher.refresh("
SERIAL = "await (blend_refresher.refresh("


def held_refresher(r, hold_ids=(10,)):
    gate = asyncio.Event()
    calls = {"started": [], "finished": [], "cancelled": [], "running": 0,
             "most_running": 0}

    class Refresher:
        async def publish_market_changes(self, session):
            r.trace.append(("publish", None))

        async def refresh(self, ids, **kwargs):
            key = tuple(sorted(ids))
            calls["started"].append(key)
            calls["running"] += 1
            calls["most_running"] = max(calls["most_running"], calls["running"])
            try:
                if key == tuple(hold_ids):
                    await gate.wait()
                else:
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                calls["cancelled"].append(key)
                raise
            finally:
                calls["running"] -= 1
            calls["finished"].append(key)
            r.trace.append(("refresh", list(key)))

        async def refresh_pending(self, **kwargs):
            r.trace.append(("pending", None))

    r.ns["blend_refresher"] = Refresher()
    return gate, calls


def serial_flush(r):
    """The shipped flush with its stamp awaited inline again (the pre-#10090
    shape): installs it in the rig in place of the pipelined one."""
    source = (ROOT / "app/tasks/polymarket_ws.py").read_text()
    assert source.count(PIPELINED) == 1
    tree = ast.parse(source.replace(PIPELINED, SERIAL))
    (node,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "flush_prices"
    ]
    exec(compile(ast.Module(body=[node], type_ignores=[]), "serial", "exec"), r.ns)


async def settle(r, until, turns=50):
    for _ in range(turns):
        if until():
            return
        await asyncio.sleep(0)


async def test_the_next_chunk_writes_while_the_previous_stamp_runs():
    r = rig(books={})
    r.release.set()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await asyncio.wait_for(r.entered.wait(), 2)
    await settle(r, lambda: ("publish", None) in r.trace[r.trace.index(("write", [900])):])
    # Event 10's stamp is still held, and the bridged leg's chunk was written.
    assert calls["started"] == [(10,)] and calls["finished"] == []
    assert ("write", [900]) in r.trace
    assert not flush.done(), "a flush never returns ahead of its stamp"
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    # One refresh at a time, in chunk order, each receipt staged in turn.
    assert calls["started"] == [(10,), (90,)]
    assert calls["finished"] == [(10,), (90,)]
    assert calls["most_running"] == 1
    assert r.marks == [1, 2, 900]
    assert not r.ns["price_buffer"]


async def test_strawman_the_serial_flush_holds_the_next_write():
    """The rig can tell: with the stamp awaited inline, the next chunk is not
    written while event 10's stamp is held."""
    r = rig(books={})
    r.release.set()
    serial_flush(r)
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await settle(r, lambda: False, turns=30)
    assert calls["started"] == [(10,)]
    assert ("write", [900]) not in r.trace
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.trace.index(("refresh", [10])) < r.trace.index(("write", [900]))


async def test_a_tail_withdrawal_still_follows_the_last_stamp():
    # 44 is event 20's leg, not in this batch: the ordinary tail withdraws it.
    r = rig(books={44: (0.2, 0.8)}, mapping={1: 10, 2: 10, 900: 90, 44: 20})
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(90,))
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await settle(r, lambda: calls["started"] == [(10,), (90,)])
    assert calls["running"] == 1
    assert ("withdraw", [44]) not in r.trace
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.trace.index(("refresh", [90])) < r.trace.index(("withdraw", [44]))
    assert calls["started"][-1] == (20,) and calls["most_running"] == 1


async def test_cancellation_cancels_the_running_stamp_before_returning():
    r = rig(books={})
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await asyncio.wait_for(r.entered.wait(), 2)  # 900's write held, 10 stamping
    assert calls["running"] == 1
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["cancelled"] == [(10,)]
    assert calls["running"] == 0, "no stamp outlives its flush"
    assert 900 in r.ns["price_buffer"]


async def test_a_cancel_landing_on_the_last_stamp_join_still_joins_it():
    r = rig(books={})
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(90,))
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await settle(r, lambda: calls["started"] == [(10,), (90,)])
    # Premise: every write committed; only event 90's stamp is still running.
    assert not r.ns["price_buffer"] and calls["running"] == 1
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["cancelled"] == [(90,)]
    assert calls["running"] == 0, "no stamp outlives its flush"
