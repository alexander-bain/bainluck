"""#10090 — a Polymarket chunk's blend stamp runs while the next chunk writes.

Twin of `test_kalshi_pipelined_stamps_10090`. Executes the shipped
`flush_prices` on the #10651 rig with a refresher whose stamp can be held.
Proves ordering and lifetime, not production latency: the next chunk's write
runs while the previous chunk's stamp is still running; refreshes never overlap
each other; withdrawals still follow the stamp before them; persistent stamps
join at catalog/final boundaries and on interrupted-batch cancellation.
"""

import ast
import asyncio

import pytest

from tests.test_polymarket_withdrawal_speed_10651 import ROOT, rig

pytestmark = pytest.mark.asyncio

# The chunk loop's pipelined stamp. #10090: a committed bridged cohort's stamp
# starts through the same owner earlier in the flush (`refresh(start_events`),
# so the anchor names the chunk's own cohort.
PIPELINED = (
    "stamp_owner.fresh = set(refresh_events)\n"
    "                        stamp_owner.task = asyncio.create_task(blend_refresher.refresh("
)
SERIAL = (
    "stamp_owner.fresh = set(refresh_events)\n"
    "                        await (blend_refresher.refresh("
)


def held_refresher(r, hold_ids=(10,), pending_events=()):
    gate = asyncio.Event()
    calls = {"started": [], "finished": [], "cancelled": [], "running": 0,
             "most_running": 0, "admitted": []}
    pending = set(pending_events)

    class Refresher:
        def pending_event_ids(self):
            return frozenset(pending)

        def admit_fresh(self, ids, **kwargs):
            return frozenset()

        def adopt_pending(self, ids):
            pending.update(ids)

        async def publish_market_changes(self, session):
            r.trace.append(("publish", None))

        async def refresh(self, ids, **kwargs):
            key = tuple(sorted(ids))
            admitted = (set(ids) | pending).difference(kwargs.get("defer_event_ids", ()))
            calls["admitted"].append(tuple(sorted(admitted)))
            # The real refresher takes due debt before its first DB await.
            pending.difference_update(admitted)
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
    nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
        and n.name in {"_flush_prices", "flush_prices"}
    ]
    assert {node.name for node in nodes} == {"_flush_prices", "flush_prices"}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "serial", "exec"), r.ns)


async def settle(r, until, turns=50):
    for _ in range(turns):
        if until():
            return
        await asyncio.sleep(0)


async def test_the_next_chunk_writes_while_the_previous_stamp_runs():
    # Covers the write/stamp overlap only: chunk 900's price write commits while
    # event 10's stamp is held, and its refused cohort then joins that older
    # owner (one refresh at a time, below). #10090: market notifications go
    # through the shared withdrawal market publisher, not a per-chunk join, and
    # this rig's sessions commit no market change, so notification order is not
    # observed here.
    r = rig(books={})
    r.release.set()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await asyncio.wait_for(r.entered.wait(), 2)
    # The rig's write retires its inputs only once that write returned True.
    await settle(r, lambda: 900 not in r.ns["price_buffer"])
    assert 900 not in r.ns["price_buffer"], "chunk 900's write never committed"
    # Event 10's stamp is still held, and the bridged leg's chunk was written.
    assert calls["started"] == [(10,)] and calls["finished"] == []
    assert ("write", [900]) in r.trace
    assert not flush.done(), "the refused next cohort must join the older owner"
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    await r.ns["catalog_boundary"].join_stamps()
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


async def test_another_events_tail_withdrawal_goes_beside_the_last_stamp():
    # 44 is event 20's leg, not in this batch: the ordinary tail withdraws it.
    # #10090: event 20 is no part of event 90's running stamp, so its
    # withdrawal no longer waits for that stamp; its own stamp still follows.
    r = rig(books={44: (0.2, 0.8)}, mapping={1: 10, 2: 10, 900: 90, 44: 20})
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(90,))
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await settle(r, lambda: ("withdraw", [44]) in r.trace)
    assert ("withdraw", [44]) in r.trace, "an unrelated stamp held the withdrawal"
    assert calls["started"] == [(10,), (90,)] and calls["running"] == 1
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.trace.index(("refresh", [90])) < r.trace.index(("refresh", [20]))
    assert calls["started"][-1] == (20,) and calls["most_running"] == 1


async def test_the_held_events_own_tail_withdrawal_waits_buffered():
    # Control: a book on event 90, whose stamp is still running, is neither
    # withdrawn under it nor holds the flush; it stays for a later flush.
    r = rig(books={}, mapping={1: 10, 2: 10, 900: 90, 44: 90})
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(90,))
    try:
        assert await asyncio.wait_for(r.ns["flush_prices"](flush_started=100), 2)
        assert calls["started"] == [(10,), (90,)] and calls["running"] == 1
        r.books[44] = (0.2, 0.8)  # arrives while event 90's stamp runs
        assert await asyncio.wait_for(r.ns["flush_prices"](flush_started=100.25), 2)
        assert calls["running"] == 1 and ("withdraw", [44]) not in r.trace
        assert r.books == {44: (0.2, 0.8)} and r.ns["stats"]["stamp_fenced"] == 1
    finally:
        gate.set()
        await r.ns["catalog_boundary"].join_stamps()
    assert await r.ns["flush_prices"](flush_started=100.5)
    assert r.trace.index(("refresh", [90])) < r.trace.index(("withdraw", [44]))
    assert calls["most_running"] == 1


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


async def test_a_cancel_landing_on_the_persistent_stamp_join_still_joins_it():
    r = rig(books={})
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(90,))
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    await settle(r, lambda: calls["started"] == [(10,), (90,)])
    # Premise: every write committed; only event 90's stamp is still running.
    assert not r.ns["price_buffer"] and calls["running"] == 1
    assert await asyncio.wait_for(flush, 2) is True
    joined = asyncio.create_task(r.ns["catalog_boundary"].join_stamps())
    await asyncio.sleep(0)  # enter the actual persistent-owner join before cancel
    joined.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(joined, 2)
    assert calls["cancelled"] == [(90,)]
    assert calls["running"] == 0, "no stamp outlives its interrupted owner join"


@pytest.mark.parametrize("future_event", [90, 20])
async def test_unfinished_pending_cohort_stays_owed_while_independent_stamp_overlaps_write(future_event):
    # Event90 spans two later chunks and has a withdrawal. It also enters the
    # first refresh as debt; admission must leave it owed until coherent.
    r = rig(
        batch={1: 0.6, 2: 0.4, 900: 0.1, 901: 0.9},
        mapping={1: 10, 2: 10, 900: future_event, 901: future_event, 44: 90},
        books={44: (0.2, 0.8)},
    )
    r.ns["FLUSH_CHUNK_ROWS"] = 1  # binary1+2 stays atomic;900 and901 separate
    r.release.set()
    gate, calls = held_refresher(r, pending_events=(90,))
    flush = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    try:
        await settle(r, lambda: calls["started"] == [(10,)])
        await settle(r, lambda: ("write", [900]) in r.trace)
        assert calls["admitted"] == [(10,)]
        assert r.ns["blend_refresher"].pending_event_ids() == frozenset({90})
        assert ("write", [900]) in r.trace, "independent stamp must not stop price progress"
        # #10090: the chunk loop no longer joins each chunk's market notification
        # before the next price write, so 901 may be written while stamp 10 is
        # held. The loop at 4a10d5f01f also wrote it, three loop turns after 900.
        # Writing event 90's rows is not reading them. Held-state invariant at
        # 901: stamp 10 admitted only event 10, event 90 stays owed, one refresh
        # runs, and nothing has refreshed event 90.
        await settle(r, lambda: ("write", [901]) in r.trace)
        assert ("write", [901]) in r.trace, "independent stamp must not stop price progress"
        assert not gate.is_set() and calls["finished"] == []
        assert calls["admitted"] == [(10,)]
        assert r.ns["blend_refresher"].pending_event_ids() == frozenset({90})
        assert calls["running"] == 1
        assert ("refresh", [90]) not in r.trace
        gate.set()
        assert await asyncio.wait_for(flush, 2) is True
        assert r.trace.index(("write", [900])) < r.trace.index(("refresh", [10]))
        assert r.trace.index(("write", [900])) < r.trace.index(("write", [901]))
        assert r.trace.index(("write", [901])) < r.trace.index(("withdraw", [44]))
        if future_event == 20:
            # Debt90 only overlaps an unfinished withdrawal; next writes are
            # independent. No refresh reads event 90 before its withdrawal.
            assert [a for a in calls["admitted"] if 90 in a] == [calls["admitted"][-1]]
        assert r.trace.index(("withdraw", [44])) < r.trace.index(("refresh", [90]))
        assert calls["most_running"] == 1
        assert r.marks == [1, 2, 900, 901]
        assert not r.ns["price_buffer"]
    finally:
        gate.set()
        await asyncio.gather(flush, return_exceptions=True)
