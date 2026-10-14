"""A stamp started inside the catalog fence never holds a later game. #10090.

Root's 18:42Z counterexample on 117ee0ff3f. The fence let game flushes run
while an unrelated standalone write drained, so game A wrote its price AND
started its blend stamp there. Once the standalone write cleared, the handover
fenced every game flush and only then joined the stamps, closing the running
call's door first. If A's stamp was held, an unrelated game B that arrived
after the standalone write had cleared waited for A's stamp: no row write, no
frame. On 5d39e56bdb (v5719) A itself waited for the standalone write, but B
was admitted into A's call on a free stamp worker and published at once.

Now, once the standalone write clears, the handover waits for the stamp call
running at that instant with games still flowing and that call's door still
open. Only then does it fence games, and under the fence it can join at most
a call started by the one game flush in flight (the game loop is serial).
That is the same residual the parent had at its own fence instant. The
catalog waits for A's held stamp. The games do not.

THE CASES:

    test_a_later_game_publishes_while_a_fence_stamp_is_held ..... THE SHIP:
        Root's exact order, run on the real `_flush_prices` and the real
        `LiveBlendRefresher` with A's stamp parked at its UPDATE. A writes and
        starts its stamp during the standalone drain, B writes AND publishes
        while A's stamp is held, the maps do not change beneath that stamp,
        and everything lands after release. `PM_PARENT_SOURCE` (a file holding
        5d39e56bdb's polymarket_ws.py) runs the parent's boundary and wrappers
        on the same rig.
    test_the_handover_settles_one_call_then_joins_one_successor ... the bound:
        the handover settles only the call running when the standalone
        write cleared, and under the fence joins only its successor. It never
        waits for a later call.
    test_a_cancelled_settle_cancels_and_joins_the_call_keeping_its_debt ...
        cancellation during the settle behaves like a cancel during the
        parent's stamps phase: the call is cancelled and joined, and its
        events stay owed.
"""

import ast
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks import polymarket_ws as task
from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_polymarket_withdrawal_speed_10651 import compile_functions

pytestmark = pytest.mark.asyncio

STANDALONE = 950  # open, no event, no partner: `flush_standalone`'s leg


def _parent_boundary(path):
    source = Path(path)
    node = next(
        n for n in ast.parse(source.read_text()).body
        if isinstance(n, ast.ClassDef) and n.name == "_PMCatalogFlushBoundary"
    )
    namespace = dict(task.__dict__)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["_PMCatalogFlushBoundary"]


def _rig(monkeypatch):
    """Game A = event 1 (legs 1, 2; its stamp parks at its UPDATE until
    `x.release`), game B = event 2 (legs 900, 901), standalone leg 950 whose
    write parks until `standalone_release`."""
    p, x = paired(monkeypatch, blocked=(1,))
    parent = os.environ.get("PM_PARENT_SOURCE")
    if parent:
        p.ns["catalog_boundary"] = _parent_boundary(parent)()
        compile_functions(
            Path(parent),
            ["_flush_prices", "_flush_standalone", "flush_prices", "flush_standalone"],
            p.ns,
        )
    buffer = p.ns["price_buffer"]
    games = {
        "A": {oid: buffer.pop(oid) for oid in (1, 2)},
        "B": {oid: buffer.pop(oid) for oid in (900, 901)},
    }
    p.ns["open_outcome_ids"].add(STANDALONE)
    buffer[STANDALONE] = 0.55
    written, standalone_parked, standalone_release = set(), asyncio.Event(), asyncio.Event()
    inner = p.ns["write_chunk"]

    async def write(chunk, **kwargs):
        if STANDALONE in chunk:
            standalone_parked.set()
            await standalone_release.wait()
        result = await inner(chunk, **kwargs)
        if result:
            written.update(chunk)
        return result

    p.ns["write_chunk"] = write
    return SimpleNamespace(
        p=p, x=x, games=games, written=written,
        standalone_parked=standalone_parked, standalone_release=standalone_release,
    )


async def _turns(seconds):
    await asyncio.sleep(seconds)


async def _root_order(monkeypatch):
    """Root's order: standalone write active; handover starts; A arrives;
    standalone write clears; B arrives while A's stamp is held; release."""
    r = _rig(monkeypatch)
    p, x = r.p, r.x
    boundary = p.ns["catalog_boundary"]
    out, mapped, maps_beside_stamp = {}, asyncio.Event(), []

    def stamp_running(event_id):
        started = any(event_id in s.event_ids for s in x.sessions)
        return started and event_id not in x.committed

    async def handover():
        async with boundary.updating():
            maps_beside_stamp.append(stamp_running(1))
            mapped.set()

    standalone = asyncio.create_task(p.ns["flush_standalone"](flush_started=999))
    h = a = b = None
    try:
        await asyncio.wait_for(r.standalone_parked.wait(), 2)
        h = asyncio.create_task(handover())
        async with asyncio.timeout(2):
            while not (boundary.changing or getattr(boundary, "standalone_fenced", False)):
                await asyncio.sleep(0)
        p.ns["price_buffer"].update(r.games["A"])
        a = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
        await _turns(0.05)
        out["a_written_during_standalone_drain"] = {1, 2} <= r.written
        out["a_stamp_started_during_standalone_drain"] = stamp_running(1)
        r.standalone_release.set()
        await asyncio.wait_for(standalone, 2)
        await _turns(0.05)
        p.ns["price_buffer"].update(r.games["B"])
        b = asyncio.create_task(p.ns["flush_prices"](flush_started=1001))
        await _turns(0.1)
        out["a_stamp_held"] = stamp_running(1)
        out["b_written_while_a_stamp_held"] = {900, 901} <= r.written
        out["b_published_while_a_stamp_held"] = 2 in x.published
        out["catalog_completed_while_a_stamp_held"] = mapped.is_set()
        x.release.set()
        await asyncio.wait_for(asyncio.gather(h, a, b), 2)
        await boundary.join_stamps()
    finally:
        r.standalone_release.set()
        x.release.set()
        pending = [t for t in (standalone, h, a, b) if t is not None]
        await asyncio.gather(*pending, return_exceptions=True)
        await boundary.join_stamps()
    out["maps_changed_beneath_a_running_stamp"] = any(maps_beside_stamp)
    out["recovered"] = (
        mapped.is_set()
        and {1, 2, 900, 901, STANDALONE} <= r.written
        and x.published.count(1) >= 1 and x.published.count(2) >= 1
        and not x.r.pending_event_ids()
        and not p.ns["price_buffer"]
        and x.r.stats["errors"] == 0
    )
    return out


async def test_a_later_game_publishes_while_a_fence_stamp_is_held(monkeypatch, capsys):
    out = await _root_order(monkeypatch)
    with capsys.disabled():
        print("\nROOT-ORDER " + json.dumps(out, sort_keys=True))
    assert out["a_stamp_held"], "premise: A's stamp is parked at its UPDATE"
    assert out["a_written_during_standalone_drain"], (
        "game A's price waited for the standalone write"
    )
    assert out["a_stamp_started_during_standalone_drain"], (
        "game A's stamp waited for the standalone write"
    )
    assert out["b_written_while_a_stamp_held"], (
        "unrelated game B's price waited for A's held stamp"
    )
    assert out["b_published_while_a_stamp_held"], (
        "unrelated game B's frame waited for A's held stamp"
    )
    assert not out["maps_changed_beneath_a_running_stamp"]
    assert out["recovered"]


class _Owner:
    """A stamp owner whose calls the test holds; records door closes."""

    def __init__(self):
        self.task = None
        self.events = None
        self.closed = 0
        self.adopted = []
        self.refresher = SimpleNamespace(
            stop_admitting=self._close, adopt_pending=self.adopted.extend,
        )

    def _close(self):
        self.closed += 1


async def _owned_boundary():
    boundary = task._PMCatalogFlushBoundary()
    owner = boundary.stamp_owner(SimpleNamespace())
    fake = _Owner()
    owner.refresher = fake.refresher
    return boundary, owner, fake


async def test_the_handover_settles_one_call_then_joins_one_successor():
    boundary, owner, fake = await _owned_boundary()
    first, second, third = asyncio.Event(), asyncio.Event(), asyncio.Event()
    owner.task = asyncio.create_task(first.wait())
    owner.events = {1}
    mapped, game_ran = asyncio.Event(), []

    async def handover():
        async with boundary.updating():
            mapped.set()

    async def game(body):
        async with boundary.flushing():
            await body()

    async def ran():
        game_ran.append(1)

    async def starts_successor():
        first.set()
        await asyncio.sleep(0)
        owner.task = asyncio.create_task(second.wait())
        owner.events = {2}

    h = asyncio.create_task(handover())
    late = None
    try:
        await asyncio.sleep(0.01)
        # Settling the first call: games still enter, its door stays open.
        await asyncio.wait_for(game(ran), 1)
        assert game_ran == [1] and not boundary.changing and fake.closed == 0
        # The flush in flight when that call returns starts its successor.
        await asyncio.wait_for(game(starts_successor), 1)
        await asyncio.sleep(0.01)
        assert boundary.changing, "the handover fences after the settled call"
        assert fake.closed == 1, "the successor is joined, door closed first"
        # A later call is never waited for: the handover only joins `second`.
        late = asyncio.create_task(third.wait())
        second.set()
        await asyncio.wait_for(mapped.wait(), 1)
        assert not late.done()
    finally:
        for event in (first, second, third):
            event.set()
        h.cancel()
        await asyncio.gather(h, return_exceptions=True)
        if late is not None:
            await asyncio.gather(late, return_exceptions=True)


async def test_a_cancelled_settle_cancels_and_joins_the_call_keeping_its_debt():
    boundary, owner, fake = await _owned_boundary()
    unwinding, unwind = asyncio.Event(), asyncio.Event()

    async def held_stamp():
        try:
            await asyncio.Event().wait()
        finally:
            unwinding.set()
            await unwind.wait()

    owner.task = asyncio.create_task(held_stamp())
    owner.events = {7}
    owner.fresh = {7}
    mapped = asyncio.Event()

    async def handover():
        async with boundary.updating():
            mapped.set()

    h = asyncio.create_task(handover())
    try:
        await asyncio.sleep(0.01)
        h.cancel()
        await asyncio.wait_for(unwinding.wait(), 1)
        h.cancel()  # repeated: recorded, the join still waits for the unwind
        await asyncio.sleep(0)
        assert not h.done()
        unwind.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(h, 1)
        assert not mapped.is_set()
        assert fake.adopted == [7], "the cancelled call's events stay owed"
        assert owner.task is None
        assert not boundary.changing and not boundary.standalone_fenced

        async def standalone():
            async with boundary.flushing(standalone=True):
                pass

        await asyncio.wait_for(standalone(), 1)  # both doors reopened
    finally:
        unwind.set()
        h.cancel()
        await asyncio.gather(h, return_exceptions=True)
        if owner.task is not None:
            owner.task.cancel()
            await asyncio.gather(owner.task, return_exceptions=True)


async def test_continuous_readmission_cannot_extend_the_settle(monkeypatch):
    """Root's 19:03Z counterexample on 8b4d3e6860, on the real refresher:
    the settle awaited the call task, and alternating same-event
    re-admissions (each admitted before the previous attempt returned) kept
    that call alive, so the catalog stayed unmapped and standalone writes
    fenced for as long as arrivals continued. Now the settle drains the
    attempts held when it began. Event 2 arriving during the settle is still
    admitted beside held event 1 (the ship). Once event 1's attempt returns
    the handover fences games and joins, door closed first: a re-admission of
    event 1 is refused (its caller keeps it owed), and the catalog maps after
    event 2's attempt, which was admitted before the fence."""
    from tests.test_single_event_commit_10090 import rig as stamp_rig, settle_until

    x = stamp_rig(monkeypatch, count=2)
    boundary = task._PMCatalogFlushBoundary()
    owner = boundary.stamp_owner(x.r)
    gates, starts = [], []
    original = x.r._refresh_batch

    async def controlled(ids, *args, **kwargs):
        gate = asyncio.Event()
        starts.append(tuple(ids))
        gates.append(gate)
        await gate.wait()
        return await original(ids, *args, **kwargs)

    x.r._refresh_batch = controlled
    owner.events, owner.fresh = {1}, {1}
    owner.task = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    mapped = asyncio.Event()

    async def handover():
        async with boundary.updating():
            mapped.set()

    hand = None
    try:
        await settle_until(lambda: len(starts) == 1)
        hand = asyncio.create_task(handover())
        await settle_until(lambda: boundary.standalone_fenced)
        assert x.r.admit_fresh([2], flush_started=1001) == frozenset({2})
        await settle_until(lambda: len(starts) == 2)
        assert not boundary.changing, "event 2 was admitted beside held event 1"
        gates[0].set()  # the frontier's only attempt returns
        await settle_until(lambda: boundary.changing)
        assert not x.r.admitting(), "the join closed the door before waiting"
        assert x.r.admit_fresh([1], flush_started=1002) == frozenset(), (
            "a re-admission extended the handover"
        )
        await asyncio.sleep(0.01)
        assert not mapped.is_set(), "maps changed beneath event 2's attempt"
        gates[1].set()
        await asyncio.wait_for(hand, 2)
        assert mapped.is_set() and not boundary.standalone_fenced
        assert not boundary.changing and owner.task is None
        assert sorted(x.published) == [1, 2]
        assert not x.r.pending_event_ids()
    finally:
        for gate in gates:
            gate.set()
        x.r.stop_admitting()
        if hand is not None:
            hand.cancel()
            await asyncio.gather(hand, return_exceptions=True)
        await boundary.join_stamps()


async def test_alternating_readmissions_do_not_starve_the_catalog(monkeypatch):
    """Root's alternating loop verbatim in shape: each next cohort (events 2,
    1, 2, ...) is admitted before the previous attempt returns. On the
    task-wait settle all ten were admitted and the catalog never mapped
    while they kept coming. The frontier is counted per attempt, so event 1
    re-admitted after its frontier attempt returned does not extend it: the
    handover fences and closes the door within a couple of arrivals."""
    from tests.test_single_event_commit_10090 import rig as stamp_rig, settle_until

    x = stamp_rig(monkeypatch, count=2)
    boundary = task._PMCatalogFlushBoundary()
    owner = boundary.stamp_owner(x.r)
    gates, starts = [], []
    original = x.r._refresh_batch

    async def controlled(ids, *args, **kwargs):
        gate = asyncio.Event()
        starts.append(tuple(ids))
        gates.append(gate)
        await gate.wait()
        return await original(ids, *args, **kwargs)

    x.r._refresh_batch = controlled
    owner.events, owner.fresh = {1}, {1}
    owner.task = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    mapped = asyncio.Event()

    async def handover():
        async with boundary.updating():
            mapped.set()

    hand, accepted = None, 0
    try:
        await settle_until(lambda: len(starts) == 1)
        hand = asyncio.create_task(handover())
        await settle_until(lambda: boundary.standalone_fenced)
        for i in range(10):
            eid = 2 if i % 2 == 0 else 1
            if x.r.admit_fresh([eid], flush_started=1001 + i) != frozenset({eid}):
                break
            accepted += 1
            await settle_until(lambda: len(starts) == i + 2)
            gates[i].set()
            previous = starts[i][0]
            await settle_until(lambda: previous not in x.r.holding_event_ids())
        assert accepted < 10, "continuous re-admission kept the catalog waiting"
        assert boundary.changing, "games were never fenced while arrivals continued"
        for gate in gates:
            gate.set()
        await asyncio.wait_for(hand, 2)
        assert mapped.is_set() and not boundary.standalone_fenced
        assert not x.r.pending_event_ids()
    finally:
        for gate in gates:
            gate.set()
        x.r.stop_admitting()
        if hand is not None:
            hand.cancel()
            await asyncio.gather(hand, return_exceptions=True)
        await boundary.join_stamps()
