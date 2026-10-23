"""#10090 — an unrelated event-bridged open write no longer holds the next game quote.

PILLARS: TRUTH / FORMATTING. SHIP: a held event page receives its next correct
probability without waiting for unrelated open-market work, while bridged
events keep their own updates.

Root's bridged-tail rig (test_pm_bridged_tail_off_game_cadence_10090.py) is the
failing parent case. Membership is by WHOLE event over the full catalog: only a
pure bridged event goes to the bridged writer, and one slate leg anywhere in the
catalog keeps the event on the game flush. These guards cover what the writer
must keep: the bridge's own pair commits in one transaction and is stamped by
its own event after commit, before (not after) its market notification; no
stamp reads its event while the write is in flight, and no write starts beneath
a running stamp of that event; a full queue, a fenced flush or a cooling lock
leaves the cohort buffered and never restores the game flush's own write; its
book waits for it; a completion taken by a flush that is then cancelled stays
owed; cancellation before or after COMMIT (including in write_chunk's buffer
cleanup, before a held notification), a twice-cancelled catalog handover and
shutdown lose neither the buffered prices nor the owed stamp; a continuously
ticking event's committed cohort is stamped before its next write; and
retry-held events are written apart and take turns for the queue. Executed
shipped closures and the real stamp owner; fake database and publication
boundaries — control flow, not production latency (the real-PG twin is in
tests/integration/test_pm_stamp_release_wake_10090_pg.py).
"""
import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from tests.test_pm_event_before_notification_10090 import committed_rig
from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions
from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig
from tests.test_single_event_commit_10090 import rig as stamp_rig, settle_until
from tests.test_pm_cross_batch_fresh_admission_10090 import preview_redis, redis_kwargs

pytestmark = pytest.mark.asyncio
PERIOD = 0.25
#: Flush clocks are anchored on the refresher's own clock seam (production:
#: `time.monotonic()`), in the past: a fixed 1000 s anchor was in the FUTURE
#: of a freshly booted CI runner's clock, so the final drain's stamp was
#: never due there (Hot List #44).
_T0 = blend._mono() - 30.0


def _mark(oid, event_id, value, seq):
    return blend.InputMark(
        seq=seq, event_id=event_id, outcome_id=oid, probability=value,
        kind="price", recv_wall=time.time(), recv_mono=time.monotonic(),
        venue_ts_ms=None, event_ordinal=seq,
    )


def _held_bridge(p):
    """Hold any write carrying leg 900 until released; record values in order."""
    entered, release = asyncio.Event(), asyncio.Event()
    original = p.ns["write_chunk"]
    inner = []

    async def held_write(chunk, **kwargs):
        p.trace.append(("values", dict(chunk)))
        if 900 in chunk and not release.is_set():
            entered.set()
            inner.append("enter")
            await release.wait()
            inner.append("exit")
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = held_write
    return entered, release


def _watch_bridged_overlap(p, x):
    """Count event-2 stamp sessions opened while a write carrying 900 runs;
    mark its return in the trace."""
    original = p.ns["write_chunk"]
    overlap = []

    async def watch(chunk, **kwargs):
        before = _stamp_sessions(x, 2)
        try:
            return await original(chunk, **kwargs)
        finally:
            if 900 in chunk:
                overlap.append(_stamp_sessions(x, 2) - before)
                p.trace.append(("bridge_returned", dict(chunk)))

    p.ns["write_chunk"] = watch
    return overlap


def _loops(p):
    boundary = p.ns["catalog_boundary"]
    stop = asyncio.Event()
    game = asyncio.create_task(blend.run_flush_cadence(
        lambda started: p.ns["flush_prices"](flush_started=started), PERIOD,
        stop=stop, wake=boundary.flush_wake,
        work_count=lambda: boundary.flush_work, wake_coalesce_s=0.005,
    ))
    return stop, game


async def _stop(p, stop, game, *releases):
    boundary = p.ns["catalog_boundary"]
    for event in releases:
        event.set()
    stop.set()
    boundary.flush_wake.set()
    try:
        await asyncio.wait_for(game, 2)
    finally:
        if not game.done():
            game.cancel()
        await asyncio.gather(game, return_exceptions=True)
        await asyncio.wait_for(boundary.bridges.join(), 2)
        await asyncio.wait_for(boundary.join_stamps(cancel=True), 2)


def _new_selected_quote(p, values=((1, 0.65), (2, 0.35))):
    for seq, (oid, value) in enumerate(values, 10):
        p.ns["price_buffer"][oid] = value
        p.ns["input_marks"][oid] = _mark(oid, 1, value, seq)
    p.ns["catalog_boundary"].wake_for_outcomes(
        [oid for oid, _ in values], p.ns["open_outcome_ids"],
        p.ns["event_id_by_outcome"], p.ns["non_blend_outcome_ids"],
    )


def _stamp_sessions(x, event_id):
    return sum(event_id in s.event_ids for s in x.sessions)


def _plain_frames(p, x):
    """Record event frames without `paired`'s committed-cohort assertion, for
    a test whose writes bypass its wrapper (an injected completion, a
    replaced writer) or whose event has a silent catalog sibling."""
    async def publish(frames):
        for frame in frames:
            p.trace.append(("event_frame", frame["event_id"]))
        await x.publish(frames)

    x.r._publish = publish


@pytest.mark.parametrize("debt", [False, True], ids=["fresh", "owed-debt"])
async def test_held_bridge_lets_the_selected_game_advance_then_stamps_its_own_pair(
    monkeypatch, debt,
):
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})  # event 2's pair: bridged open
    if debt:
        # Event 2 already owes a stamp: no admission or refresh may take that
        # debt while its bridged write is uncommitted (`unstamped`).
        x.r.keep_owed({2})
    entered, release_bridge = _held_bridge(p)
    overlap = _watch_bridged_overlap(p, x)
    stop, game = _loops(p)
    boundary = p.ns["catalog_boundary"]
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert boundary.bridges.reserved == boundary.bridges.unstamped == {2}
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        _new_selected_quote(p)
        x.release.set()  # event 1's first stamp returns
        await settle_until(lambda: 1 in x.published and not x.r.holding_event_ids())
        deadline = time.monotonic() + 4 * PERIOD
        while not any(kind == "values" and v.get(1) == 0.65 for kind, v in p.trace):
            assert time.monotonic() < deadline, "the selected quote waited for the bridge"
            await asyncio.sleep(0.01)
        # The bridge has not committed, so its event has no frame and no stamp.
        assert 2 not in x.published and _stamp_sessions(x, 2) == 0
        assert 900 in p.ns["price_buffer"] and 901 in p.ns["price_buffer"]
        release_bridge.set()
        await settle_until(lambda: 2 in x.published and not boundary.bridges.reserved)
        await settle_until(lambda: not p.ns["price_buffer"])
    finally:
        await _stop(p, stop, game, release_bridge, x.release)
    # Complements in one transaction; the bridge's own event stamped once.
    assert ("write", [900, 901]) in p.trace
    assert x.published.count(2) == 1
    assert p.trace.index(("write", [900, 901])) < p.trace.index(("event_frame", 2))
    assert overlap == [0], "an event-2 stamp ran during its bridged write"
    assert x.r.stats["errors"] == p.ns["stats"]["errors"] == 0
    assert p.ns["stats"]["bridged_handed_off"] == 2


@pytest.mark.parametrize("sibling", ["buffered", "silent"])
async def test_mixed_event_stays_whole_on_the_game_flush(monkeypatch, sibling):
    """Membership is by WHOLE event over the full catalog: one slate leg of
    event 2 anywhere in the catalog — buffered or silent — keeps its bridged
    pair on the game flush, so no event is written by two writers."""
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})
    p.ns["event_id_by_outcome"][3] = 2
    p.ns["market_by_outcome"][3] = 3
    if sibling == "buffered":
        p.ns["price_buffer"][3] = 0.55
        p.ns["input_marks"][3] = _mark(3, 2, 0.55, 5)
    _plain_frames(p, x)
    x.release.set()
    boundary = p.ns["catalog_boundary"]
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 0), 2) is True
    await asyncio.wait_for(boundary.join_stamps(), 2)
    assert boundary.bridges.task is None and "bridged_handed_off" not in p.ns["stats"]
    writes = [ids for kind, ids in p.trace if kind == "write"]
    assert [900, 901] in writes
    assert x.published.count(2) == 1
    last_write = max(i for i, (kind, ids) in enumerate(p.trace)
                     if kind == "write" and (900 in ids or 3 in ids))
    assert last_write < p.trace.index(("event_frame", 2))
    assert not p.ns["price_buffer"]


async def test_pure_bridged_cohort_waits_buffered_while_side_flushes_are_fenced(monkeypatch):
    """No fallback: a fenced (catalog-changing) flush leaves the pure bridged
    pair buffered — never written by the game flush — and the next unfenced
    flush hands it to the bridged writer."""
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})
    boundary = p.ns["catalog_boundary"]
    boundary.standalone_fenced = True
    x.release.set()
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 0), 2) is True
    await asyncio.wait_for(boundary.join_stamps(), 2)
    assert not any(kind == "write" and 900 in ids for kind, ids in p.trace)
    assert p.ns["price_buffer"] == {900: 0.7, 901: 0.3}
    assert p.ns["stats"]["bridge_waiting"] == 1 and not boundary.bridges.busy()
    boundary.standalone_fenced = False
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 1), 2) is True
    await asyncio.wait_for(boundary.bridges.join(), 2)
    assert ("write", [900, 901]) in p.trace and not p.ns["price_buffer"]
    assert p.ns["stats"]["bridged_handed_off"] == 2


async def test_cooling_lock_retry_waits_buffered_and_final_drain_writes_serially(monkeypatch):
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})
    boundary = p.ns["catalog_boundary"]
    x.release.set()
    p.ns["lock_retry_until"][900] = time.monotonic() + 60  # still cooling down
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 0), 2) is True
    assert not any(kind == "write" and 900 in ids for kind, ids in p.trace)
    assert not boundary.bridges.busy() and 900 in p.ns["price_buffer"]
    p.ns["lock_retry_until"][900] = 0  # cooldown passed: the writer probes it
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 1), 2) is True
    await asyncio.wait_for(boundary.bridges.join(), 2)
    await asyncio.wait_for(boundary.join_stamps(), 2)
    assert ("write", [900, 901]) in p.trace and p.ns["stats"]["bridged_handed_off"] == 2

    q, y = paired(monkeypatch)
    q.ns["open_outcome_ids"].update({900, 901})
    y.release.set()
    await asyncio.wait_for(q.ns["_flush_prices"](final=True), 2)
    await asyncio.wait_for(q.ns["catalog_boundary"].join_stamps(), 2)
    assert q.ns["catalog_boundary"].bridges.task is None
    assert "bridged_handed_off" not in q.ns["stats"]
    assert ("write", [900, 901]) in q.trace


def _many_bridges(monkeypatch, events=(2, 3, 4)):
    """`paired`, with each of ``events`` a pure bridged open pair."""
    x = stamp_rig(monkeypatch, count=max(events), block=True, blocked=(1,))
    batch = {1: 0.6, 2: 0.4}
    mapping = {1: 1, 2: 1}
    complements = {1: 2, 2: 1}
    for n, eid in enumerate(events):
        yes, no = 900 + 2 * n, 901 + 2 * n
        batch.update({yes: 0.7, no: 0.3})
        mapping.update({yes: eid, no: eid})
        complements.update({yes: no, no: yes})
    p = pm_rig(batch=batch, mapping=mapping, books={})
    p.release.set()
    p.ns["open_complement_of"].update(complements)
    p.ns["open_outcome_ids"].update(oid for oid in batch if oid >= 900)
    p.ns["input_marks"] = {
        oid: _mark(oid, mapping[oid], value, n)
        for n, (oid, value) in enumerate(batch.items(), 1)
    }
    x.r.receipts = p.ns["tail_receipts"] = blend.TailReceipts("polymarket")
    p.ns["blend_refresher"] = x.r
    p.ns["logger"] = blend.logger
    original_publish = x.r._publish

    async def publish(frames):
        for frame in frames:
            p.trace.append(("event_frame", frame["event_id"]))
        await original_publish(frames)

    x.r._publish = publish
    return p, x


async def test_more_bridged_cohorts_than_the_cap_stay_buffered_while_the_game_advances(
    monkeypatch,
):
    """Saturation never restores the synchronous write: with the first bridge
    held, cohorts past ``PM_BRIDGE_QUEUE_LIMIT`` stay buffered (oldest first)
    and the selected game still advances; every bridge lands afterwards."""
    p, x = _many_bridges(monkeypatch)
    p.ns["FLUSH_CHUNK_ROWS"] = 2  # one event per cohort
    entered, release_bridge = _held_bridge(p)
    stop, game = _loops(p)
    boundary = p.ns["catalog_boundary"]
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        assert boundary.bridges.reserved == {2, 3}
        assert len(boundary.bridges.queue) == pm.PM_BRIDGE_QUEUE_LIMIT - 1
        _new_selected_quote(p)
        x.release.set()
        deadline = time.monotonic() + 4 * PERIOD
        while not any(kind == "values" and v.get(1) == 0.65 for kind, v in p.trace):
            assert time.monotonic() < deadline, "the selected quote waited for the bridges"
            await asyncio.sleep(0.01)
        # Event 4 is still buffered: neither the game flush nor the writer
        # wrote it while the first bridge holds.
        assert not any(kind == "values" and 904 in v for kind, v in p.trace)
        assert {904, 905} <= set(p.ns["price_buffer"])
        assert p.ns["stats"]["bridge_waiting"] >= 1
        assert not any(e in x.published for e in (2, 3, 4))
        release_bridge.set()
        await settle_until(lambda: all(e in x.published for e in (2, 3, 4)))
        await settle_until(lambda: not p.ns["price_buffer"] and not boundary.bridges.reserved)
    finally:
        await _stop(p, stop, game, release_bridge, x.release)
    order = [v for kind, v in p.trace if kind == "values" and min(v) >= 900]
    assert [sorted(v) for v in order] == [[900, 901], [902, 903], [904, 905]]
    assert all(x.published.count(e) == 1 for e in (2, 3, 4))
    assert x.r.stats["errors"] == p.ns["stats"]["errors"] == 0


async def test_committed_bridge_stamps_its_event_while_its_market_notification_is_held(
    monkeypatch,
):
    """Twin of `test_pm_event_before_notification_10090`: the bridged event's
    frame does not wait for its independent market notification; the sender
    is still owned (the event stays reserved, so its next write follows the
    sender) and joined on shutdown, through repeated cancellation."""
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})
    entered, release = asyncio.Event(), asyncio.Event()
    finished = []
    calls = []

    async def held_publish(session):
        name = asyncio.current_task().get_name()
        calls.append(name)
        if name != "polymarket-bridged-market-publish":
            return  # the game flush's own chunk
        entered.set()
        await release.wait()
        finished.append(True)

    x.r.publish_market_changes = held_publish
    x.release.set()
    boundary = p.ns["catalog_boundary"]
    stop, game = _loops(p)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await settle_until(lambda: 2 in x.published)
        assert boundary.bridges.reserved == {2} and not finished
        stop.set()
        boundary.flush_wake.set()
        await asyncio.wait_for(game, 2)
        joiner = asyncio.create_task(boundary.bridges.join())
        for _ in range(2):
            await asyncio.sleep(0.01)
            joiner.cancel()
        await asyncio.sleep(0.02)
        assert not joiner.done() and boundary.bridges.busy()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(joiner, 2)
        assert finished == [True] and not boundary.bridges.reserved
    finally:
        release.set()
        await _stop(p, stop, game, x.release)
    assert x.published.count(2) == 1


class _GatedLock(asyncio.Lock):
    """`buffer_lock` whose Nth acquisition parks until ``gate`` is set."""

    def __init__(self, nth):
        super().__init__()
        self.nth, self.count = nth, 0
        self.parked, self.gate = asyncio.Event(), asyncio.Event()

    async def acquire(self):
        self.count += 1
        if self.count == self.nth:
            self.parked.set()
            await self.gate.wait()
        return await super().acquire()


@pytest.mark.parametrize("where", ["untimed-withdrawal", "timed-before-its-stamp"])
async def test_taken_completion_is_still_owed_after_the_game_flush_is_cancelled(
    monkeypatch, where,
):
    """A flush that took a committed bridged cohort and is cancelled before
    its stamp started (an untimed flush in an unrelated withdrawal; a timed
    one before the stamp it starts) leaves it owed; the next quiet flush
    stamps it with no new tick."""
    p, x = paired(monkeypatch)
    p.ns["price_buffer"].clear()
    _plain_frames(p, x)
    boundary = p.ns["catalog_boundary"]
    boundary.bridges._complete([900, 901], {}, {2})
    entered = asyncio.Event()
    flush_withdrawals = p.ns["flush_withdrawals"]
    if where == "untimed-withdrawal":
        async def held_withdrawal(**kwargs):
            entered.set()
            await asyncio.Event().wait()

        p.ns["flush_withdrawals"] = held_withdrawal
        started = None
    else:
        gated = p.ns["buffer_lock"] = _GatedLock(2)  # the stamp-start read
        entered = gated.parked
        started = time.monotonic()
    flush = asyncio.create_task(p.ns["_flush_prices"](flush_started=started))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        flush.cancel()
        await asyncio.gather(flush, return_exceptions=True)
        assert 2 in x.r.pending_event_ids() and not boundary.bridges.completed
        assert 2 not in x.published
        p.ns["flush_withdrawals"] = flush_withdrawals
        p.ns["buffer_lock"] = asyncio.Lock()
        x.release.set()
        await asyncio.wait_for(p.ns["_flush_prices"](flush_started=time.monotonic()), 2)
        await asyncio.wait_for(boundary.join_stamps(), 2)
        assert 2 in x.published and 2 not in x.r.pending_event_ids()
    finally:
        flush.cancel()
        await asyncio.gather(flush, return_exceptions=True)
        x.release.set()
        await boundary.join_stamps(cancel=True)


async def test_a_flush_with_only_a_bridged_completion_never_awaits_its_stamp(monkeypatch):
    """The completion's stamp starts through the stamp owner: a held stamp of
    the bridged event does not hold the flush that took it (it returns), so
    the cadence keeps writing unrelated games."""
    p, x = paired(monkeypatch, blocked=(2,))
    p.ns["price_buffer"].clear()
    _plain_frames(p, x)
    boundary = p.ns["catalog_boundary"]
    boundary.bridges._complete([900, 901], {}, {2})
    try:
        assert await asyncio.wait_for(
            p.ns["_flush_prices"](flush_started=time.monotonic()), 1,
        ) is True
        await asyncio.wait_for(x.second_stamp.wait(), 1)  # event 2's stamp holds
        assert 2 not in x.published
        p.ns["price_buffer"].update({1: 0.65, 2: 0.35})
        assert await asyncio.wait_for(
            p.ns["_flush_prices"](flush_started=time.monotonic()), 1,
        ) is True
        assert ("write", [1, 2]) in p.trace
        x.release.set()
        await asyncio.wait_for(boundary.join_stamps(), 2)
        assert 2 in x.published and 1 in x.published
    finally:
        x.release.set()
        await boundary.join_stamps(cancel=True)


async def test_failed_bridged_write_reads_no_partial_board_then_recovers(monkeypatch):
    """Existing debt + a failing bridged pair. The pair is one transaction, so
    no board is ever half-written: no event-2 stamp runs while the write is
    in flight, the failed pair stays buffered (failure hold, no retry storm),
    the healthy game progresses, and the recovered write is followed by an
    event-2 stamp of the new pair, after which nothing is owed."""
    p, x = paired(monkeypatch, fail_last=True)  # 901's write fails
    p.ns["open_outcome_ids"].update({900, 901})
    _plain_frames(p, x)
    x.r.keep_owed({2})
    overlap = _watch_bridged_overlap(p, x)
    x.release.set()
    boundary = p.ns["catalog_boundary"]
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 0), 2) is True
    await asyncio.wait_for(boundary.bridges.join(), 2)
    await asyncio.wait_for(boundary.join_stamps(), 2)
    assert 1 in x.published
    assert p.ns["price_buffer"] == {900: 0.7, 901: 0.3}
    assert not boundary.bridges.accepting() and not boundary.bridges.take_completed()
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 3), 2) is True
    assert not boundary.bridges.busy(), "a failure hold leaves the pair buffered"
    boundary.bridges.hold_until = 0
    p.ns["write_chunk"] = _recovered(p, overlap, x)
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 6), 2) is True
    await asyncio.wait_for(boundary.bridges.join(), 2)
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 9), 2) is True
    await asyncio.wait_for(boundary.join_stamps(), 2)
    recovered = p.trace.index(("write", [900, 901]))
    frames = [i for i, entry in enumerate(p.trace) if entry == ("event_frame", 2)]
    assert frames and frames[-1] > recovered
    assert overlap == [0, 0], "an event-2 stamp ran during a bridged write"
    assert 2 not in x.r.pending_event_ids() and not p.ns["price_buffer"]


async def test_a_reserved_events_book_waits_for_its_bridge(monkeypatch):
    """A wide book on a leg whose bridged write is still in flight (no new
    price, so the flush has nothing of that event to hand off) is not
    withdrawn until the bridge returns: a withdrawal judges the final stored
    price and must not reorder ahead of the write that sets it."""
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})
    entered, release_bridge = _held_bridge(p)
    _watch_bridged_overlap(p, x)
    x.release.set()
    boundary = p.ns["catalog_boundary"]
    stop, game = _loops(p)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        p.ns["withdraw_buffer"][900] = (0.1, 0.9)
        _new_selected_quote(p)
        await settle_until(lambda: any(
            kind == "values" and v.get(1) == 0.65 for kind, v in p.trace
        ))
        await settle_until(lambda: boundary.active == 0)
        await asyncio.sleep(2 * PERIOD)
        assert not any(kind == "withdraw" and 900 in ids for kind, ids in p.trace)
        release_bridge.set()
        await settle_until(lambda: not p.ns["withdraw_buffer"])
    finally:
        await _stop(p, stop, game, release_bridge, x.release)
    returned = p.trace.index(("bridge_returned", {900: 0.7, 901: 0.3}))
    withdrawn = next(i for i, (kind, ids) in enumerate(p.trace)
                     if kind == "withdraw" and 900 in ids)
    assert returned < withdrawn


async def test_an_untimed_flush_neither_writes_nor_withdraws_a_reserved_event(monkeypatch):
    """Defence for the only flush that does not partition (untimed, not
    final; production's cadence always passes its start): legs and books of
    an event the bridged writer still owns stay buffered."""
    p, x = paired(monkeypatch)
    p.ns["open_outcome_ids"].update({900, 901})
    entered, release_bridge = _held_bridge(p)
    x.release.set()
    boundary = p.ns["catalog_boundary"]
    assert await asyncio.wait_for(p.ns["_flush_prices"](flush_started=_T0 + 0), 2) is True
    try:
        await asyncio.wait_for(entered.wait(), 2)
        p.ns["price_buffer"].update({900: 0.72, 901: 0.28})
        p.ns["withdraw_buffer"][900] = (0.1, 0.9)
        # A later chunk of the same flush (event 1's newer quote) reaches the
        # point where event 2's planned writes look complete.
        p.ns["price_buffer"].update({1: 0.65, 2: 0.35})
        await asyncio.wait_for(p.ns["_flush_prices"](), 2)
        assert ("values", {1: 0.65, 2: 0.35}) in p.trace
        assert not any(kind == "values" and v.get(900) == 0.72 for kind, v in p.trace)
        assert not any(kind == "withdraw" and 900 in ids for kind, ids in p.trace)
        assert boundary.bridges.reserved == {2}
    finally:
        release_bridge.set()
        await asyncio.wait_for(boundary.bridges.join(), 2)
        await asyncio.wait_for(boundary.join_stamps(cancel=True), 2)


async def test_a_new_bridged_pair_waits_while_its_events_stamp_is_running(monkeypatch):
    """No bridged write starts beneath a stamp still reading its event: the
    newer pair stays buffered (fenced) until that stamp returns, then the
    bridged writer takes it."""
    p, x = paired(monkeypatch, blocked=(2,))
    p.ns["open_outcome_ids"].update({900, 901})
    _plain_frames(p, x)
    boundary = p.ns["catalog_boundary"]
    stop, game = _loops(p)
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 2)  # event 2's stamp holds
        p.ns["price_buffer"].update({900: 0.72, 901: 0.28})
        p.ns["input_marks"].update({900: _mark(900, 2, 0.72, 20), 901: _mark(901, 2, 0.28, 21)})
        boundary.wake_for_outcomes(
            [900, 901], p.ns["open_outcome_ids"], p.ns["event_id_by_outcome"],
            p.ns["non_blend_outcome_ids"],
        )
        _new_selected_quote(p)  # an unrelated game keeps the cadence flushing
        await settle_until(lambda: p.trace.count(("write", [1, 2])) == 2)
        await asyncio.sleep(2 * PERIOD)
        assert p.trace.count(("write", [900, 901])) == 1, "written beneath its stamp"
        assert p.ns["price_buffer"] == {900: 0.72, 901: 0.28}
        assert p.ns["stats"]["bridge_waiting"] >= 1
        x.release.set()
        await settle_until(lambda: p.trace.count(("write", [900, 901])) == 2)
        await settle_until(lambda: not p.ns["price_buffer"])
    finally:
        await _stop(p, stop, game, x.release)
    first_frame = p.trace.index(("event_frame", 2))
    second_write = [i for i, e in enumerate(p.trace) if e == ("write", [900, 901])][1]
    assert first_frame < second_write


async def test_repeated_cancellation_of_a_catalog_handover_keeps_the_bridged_stamp_owed(
    monkeypatch, preview_redis,
):
    """Composition with the real refresher (Root's coverage #2, bridged): a
    committed bridged cohort's stamp is running and held in its session
    cleanup; a catalog handover is cancelled twice. The handover never
    enters before that cleanup ends, no second writer or refresh starts, the
    debt survives with no admission or reservation left, and the final drain
    writes the newer pair and publishes it."""
    # Periodic flushes and final drain share one deterministic clock. An
    # import-time anchor plus the runner's current clock can age game 1 into
    # a heartbeat during earlier tests and append it after the newer pair.
    monkeypatch.setattr(blend, "_mono", lambda: _T0 + 2)
    p, x = paired(monkeypatch, blocked=(2,))
    p.ns["open_outcome_ids"].update({900, 901})
    unwinding, finish_unwind, handed_over = asyncio.Event(), asyncio.Event(), asyncio.Event()
    factory = x.r._session_factory

    @asynccontextmanager
    async def slow_unwind():
        async with factory() as session:
            try:
                yield session
            finally:
                if 2 in getattr(session, "event_ids", ()) and asyncio.current_task().cancelling():
                    unwinding.set()
                    await finish_unwind.wait()

    x.r._session_factory = slow_unwind
    boundary = p.ns["catalog_boundary"]

    async def handover():
        async with boundary.updating():
            handed_over.set()

    update = None
    try:
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=_T0 + 0), 2) is True
        await asyncio.wait_for(boundary.bridges.join(), 2)  # the pair committed
        writer = boundary.bridges.task
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=_T0 + 1), 2) is True
        await asyncio.wait_for(x.second_stamp.wait(), 2)  # its stamp holds
        # Establish that only the bridged game's publication remains owed.
        # Default DNPL's ledger I/O can leave game 1's sender still running
        # after game 2 enters its held transaction.
        await settle_until(lambda: 1 in x.published)
        p.ns["price_buffer"].update({900: 0.72, 901: 0.28})
        update = asyncio.create_task(handover())
        await asyncio.sleep(0)
        update.cancel()
        await asyncio.wait_for(unwinding.wait(), 2)
        update.cancel()
        await asyncio.sleep(0)
        assert not update.done() and not handed_over.is_set()
        assert 2 not in x.published
        finish_unwind.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(update, 2)
        assert not handed_over.is_set()
        assert 2 in x.r.pending_event_ids()
        assert x.r._admission is None
        assert boundary.active == 0 and not boundary.changing
        assert boundary.bridges.task is writer and not boundary.bridges.busy()
        assert not boundary.bridges.reserved and not boundary.bridges.unstamped
        x.release.set()
        assert await asyncio.wait_for(p.ns["flush_prices"](final=True), 2) is True
        await asyncio.wait_for(boundary.join_stamps(), 2)
    finally:
        finish_unwind.set()
        x.release.set()
        if update is not None:
            await asyncio.gather(update, return_exceptions=True)
        await boundary.join_stamps(cancel=True)
    assert 2 in x.published and not x.r.pending_event_ids()
    # The bridged writer's pair, then the final drain's newer pair.
    assert p.trace.count(("write", [900, 901])) == 2
    assert not p.ns["price_buffer"]
    assert x.frames[-1]["event_id"] == 2


def _recovered(p, overlap, x):
    async def write(chunk, *, final=False, start_market_publish=None):
        before = _stamp_sessions(x, 2)
        p.trace.append(("write", list(chunk)))
        await asyncio.sleep(0.01)
        if start_market_publish is not None:
            start_market_publish(None)
        for oid, value in chunk.items():
            if p.ns["price_buffer"].get(oid) == value:
                p.ns["price_buffer"].pop(oid)
        if 900 in chunk:
            overlap.append(_stamp_sessions(x, 2) - before)
        return pm._PMPriceWriteResult(list(chunk))

    return write


# ── the writer's own lifecycle ────────────────────────────────────────────


def _writer_deps(write, published=None):
    async def publish(session):
        if published is not None:
            published.append(session)

    return dict(
        write=write, publish=publish, side_writer=asyncio.Lock(),
        buffer_lock=asyncio.Lock(), price_buffer={900: 0.7, 901: 0.3},
        input_marks={900: "m900", 901: "m901"},
    )


async def test_writer_cancelled_before_commit_keeps_prices_and_owes_nothing():
    entered = asyncio.Event()

    async def write(chunk, *, start_market_publish=None):
        entered.set()
        await asyncio.Event().wait()

    wake = asyncio.Event()
    w = pm._PMBridgeWriter(wake)
    deps = _writer_deps(write)
    w.offer([900, 901], {2}, **deps)
    await asyncio.wait_for(entered.wait(), 1)
    assert w.reserved == w.unstamped == {2}
    wake.clear()
    w.task.cancel()
    await asyncio.wait_for(asyncio.gather(w.task, return_exceptions=True), 1)
    assert deps["price_buffer"] == {900: 0.7, 901: 0.3}
    assert w.take_completed() == []
    assert not w.reserved and not w.unstamped and wake.is_set()
    assert not deps["side_writer"].locked()


async def test_committed_cohort_is_owed_before_its_market_notification_returns():
    """Root's control: the completion is visible while the notification is
    held; the sender is still joined before the event is released."""
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(chunk, *, start_market_publish):
        start_market_publish(object())
        return pm._PMPriceWriteResult(chunk)

    async def publish(session):
        entered.set()
        await release.wait()

    deps = _writer_deps(write)
    deps["publish"] = publish
    wake = asyncio.Event()
    w = pm._PMBridgeWriter(wake)
    w.offer([900, 901], {2}, **deps)
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        assert w.completed == [([900, 901], {900: "m900", 901: "m901"}, {2})]
        assert wake.is_set() and w.unstamped == set() and w.reserved == {2}
    finally:
        release.set()
        await asyncio.wait_for(w.join(), 1)
    assert not w.reserved and len(w.take_completed()) == 1


async def test_writer_cancelled_after_commit_still_owes_the_whole_chunk():
    committed, hold = asyncio.Event(), asyncio.Event()
    published = []

    async def write(chunk, *, start_market_publish=None):
        start_market_publish("session")
        committed.set()
        await hold.wait()  # buffer cleanup interrupted
        return pm._PMPriceWriteResult([900])

    w = pm._PMBridgeWriter(asyncio.Event())
    w.offer([900, 901], {2}, **_writer_deps(write, published))
    await asyncio.wait_for(committed.wait(), 1)
    # COMMIT landed: no stamp defers the event any more, writes still skip it.
    assert w.unstamped == set() and w.reserved == {2}
    w.task.cancel()
    await asyncio.wait_for(asyncio.gather(w.task, return_exceptions=True), 1)
    (ids, marks, events), = w.take_completed()
    assert sorted(ids) == [900, 901] and events == {2}
    assert marks == {900: "m900", 901: "m901"}
    assert not w.reserved


async def test_writer_owes_only_returned_rows_and_holds_after_a_failure():
    calls = []

    async def write(chunk, *, start_market_publish=None):
        calls.append(dict(chunk))
        if len(calls) == 2:
            return False
        start_market_publish("session")
        return pm._PMPriceWriteResult([901])

    w = pm._PMBridgeWriter(asyncio.Event())
    deps = _writer_deps(write)
    w.offer([900, 901], {2}, **deps)
    await asyncio.wait_for(w.join(), 1)
    assert w.take_completed() == [([901], {901: "m901"}, {2})]
    assert w.accepting()
    w.offer([900, 901], {2}, **deps)
    await asyncio.wait_for(w.join(), 1)
    # A failed write owes nothing (its prices stay buffered), and later
    # cohorts stay buffered until the retry interval passes.
    assert w.take_completed() == []
    assert deps["price_buffer"] == {900: 0.7, 901: 0.3}
    assert not w.accepting() and not w.reserved


async def test_writer_cancelled_before_its_first_turn_releases_queued_cohorts():
    async def write(chunk, *, start_market_publish=None):
        raise AssertionError("never reached")

    w = pm._PMBridgeWriter(asyncio.Event())
    deps = _writer_deps(write)
    w.offer([900], {2}, **deps)
    w.offer([901], {4}, **deps)
    assert not w.accepting()  # bounded: two cohorts outstanding
    w.task.cancel()
    await asyncio.wait_for(asyncio.gather(w.task, return_exceptions=True), 1)
    assert w.take_completed() == []
    assert not w.reserved and not w.unstamped and not w.queue
    assert deps["price_buffer"] == {900: 0.7, 901: 0.3}


async def test_catalog_handover_waits_for_the_writer_and_keeps_its_stamp_as_debt():
    boundary = pm._PMCatalogFlushBoundary()
    kept = []

    class Refresher:
        def keep_owed(self, events, *, marks=()):
            kept.append((set(events), list(marks)))

        def adopt_pending(self, events):
            raise AssertionError("keep_owed carries the marks")

    boundary.stamps = pm._PMStampOwner(Refresher())
    hold = asyncio.Event()

    async def write(chunk, *, start_market_publish=None):
        await hold.wait()
        start_market_publish("session")
        return pm._PMPriceWriteResult(list(chunk))

    boundary.bridges.offer([900, 901], {2}, **_writer_deps(write))
    entered = asyncio.Event()

    async def handover():
        async with boundary.updating():
            entered.set()
            assert kept == [({2}, ["m900", "m901"])]
            assert not boundary.bridges.take_completed()

    task = asyncio.create_task(handover())
    await asyncio.sleep(0.02)
    assert boundary.standalone_fenced and not entered.is_set()
    assert not boundary.bridges.accepting() or boundary.standalone_fenced
    hold.set()
    await asyncio.wait_for(task, 1)
    assert entered.is_set() and not boundary.standalone_fenced


@pytest.mark.parametrize("phase", ["write", "post_commit_publication"])
async def test_shutdown_joins_the_writer_then_drains_and_stamps(phase):
    (p, publishing, publish_release, refreshed, _, _) = committed_rig()
    # 1/2 are event 10's bridged open pair; the game flush hands them off.
    p.ns["open_outcome_ids"].update({1, 2})
    kept = []
    p.ns["blend_refresher"].keep_owed = lambda events, marks=(): kept.append(set(events))
    write_entered = asyncio.Event()
    initial_session = p.ns["get_task_session"]
    held_once = False

    @asynccontextmanager
    async def held_session():
        nonlocal held_once
        async with initial_session() as session:
            execute = session.execute

            async def held_execute(stmt, params=None):
                nonlocal held_once
                result = await execute(stmt, params)
                if (phase == "write" and not held_once
                        and isinstance(stmt, tuple) and stmt[0] == "prices"):
                    held_once = True
                    write_entered.set()
                    await asyncio.Event().wait()
                return result

            session.execute = held_execute
            yield session

    p.ns["get_task_session"] = held_session
    compile_functions(
        ROOT / "app/tasks/polymarket_ws.py", ["drain_prices", "join_flushes_then_drain"], p.ns,
    )
    boundary = p.ns["catalog_boundary"]
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=_T0 + 0), 1) is True
    assert boundary.bridges.busy() and boundary.bridges.reserved == {10}
    await asyncio.wait_for(
        (write_entered if phase == "write" else publishing).wait(), 1,
    )
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    p.ns.update({name: done for name in
                 ["flush_task", "standalone_task", "prop_task", "admission_task",
                  "game_run_task"]})
    p.ns.update(resolution_tasks=set(), open_run_task=None, FINAL_FLUSH_ATTEMPTS=3,
                LOOP_REAP_TIMEOUT_S=1, asyncio=asyncio)
    if phase == "write":
        boundary.bridges.task.cancel()  # cancelled mid-SQL: rolls back
    join = asyncio.create_task(p.ns["join_flushes_then_drain"]())
    await asyncio.sleep(0.02)
    assert not join.done() or phase == "write"
    publish_release.set()
    await asyncio.wait_for(join, 2)
    assert not boundary.bridges.busy() and not boundary.bridges.reserved
    commits = sum(kind == "commit" for kind, _ in p.trace)
    if phase == "write":
        # Nothing committed by the writer; the final drain writes the pair.
        assert kept == [] and commits == 1
        assert ("event_ready", 10) in p.trace
    else:
        # Committed by the writer and handed to debt before the drain.
        assert kept == [{10}] and commits == 1
    assert not p.ns["price_buffer"]
    assert p.ns["stats"]["final_flush_dropped"] == 0


def _hold_stamps_of(x, event_id):
    """Hold any stamp batch carrying ``event_id`` until released."""
    entered, release = asyncio.Event(), asyncio.Event()
    attempt = x.r._refresh_batch
    entered.count = 0

    async def held(ids, *args, **kwargs):
        if event_id in ids:
            entered.count += 1
            entered.set()
            await release.wait()
        return await attempt(ids, *args, **kwargs)

    x.r._refresh_batch = held
    return entered, release


def _bridge_writes(p, oid=900):
    return sum(1 for kind, v in p.trace if kind == "write" and oid in v)


async def test_a_continuously_ticking_bridge_is_stamped_between_its_writes(monkeypatch):
    """Root's continuous-arrival control (seven cohorts committed, zero event
    frames until the venue went quiet): a committed cohort's stamp takes its
    turn BEFORE the same event's newer pair is offered, the newer pair waits
    buffered while that stamp holds the event, and every committed cohort is
    stamped while ticks keep arriving before every flush. The fake reader
    returns one unchanged board, so a repeat stamp publishes no new frame here;
    the stamp's turn is what is counted (the real-PG twin publishes each
    committed value)."""
    p, x = _many_bridges(monkeypatch, events=(2,))
    for oid in (1, 2):
        p.ns["price_buffer"].pop(oid, None)
    x.release.set()
    boundary = p.ns["catalog_boundary"]
    entered, release = _hold_stamps_of(x, 2)
    seq = iter(range(100, 1000))

    def tick(value):
        p.ns["price_buffer"].update({900: value, 901: round(1 - value, 2)})
        p.ns["input_marks"].update({
            900: _mark(900, 2, value, next(seq)),
            901: _mark(901, 2, round(1 - value, 2), next(seq)),
        })

    async def flush():
        await asyncio.wait_for(p.ns["_flush_prices"](flush_started=time.monotonic()), 2)

    try:
        await flush()  # the first cohort goes to the bridged writer
        await asyncio.wait_for(boundary.bridges.join(), 2)
        assert _bridge_writes(p) == 1
        for n in range(1, 5):
            stamps, writes = entered.count, _bridge_writes(p)
            entered.clear()
            release.clear()
            tick(0.70 + n / 100)
            await flush()
            # The committed cohort's stamp started; its successor stays put.
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(boundary.bridges.join(), 2)
            assert _bridge_writes(p) == writes, "successor written beneath its stamp"
            assert p.ns["price_buffer"][900] == 0.70 + n / 100
            release.set()
            await asyncio.wait_for(boundary.join_stamps(), 2)
            assert entered.count == stamps + 1, n
            assert 2 not in x.r.pending_event_ids(), n
            assert ("event_frame", 2) in p.trace
            # A newer tick still arrives before the next flush: the newest
            # value is the one written.
            tick(0.80 + n / 100)
            await flush()
            await asyncio.wait_for(boundary.bridges.join(), 2)
            assert _bridge_writes(p) == writes + 1
            assert 900 not in p.ns["price_buffer"]
            last = [v for kind, v in p.trace if kind == "values" and 900 in v]
            assert not last or last[-1][900] == 0.80 + n / 100
        assert not boundary.bridges.unstamped
    finally:
        release.set()
        await asyncio.wait_for(boundary.bridges.join(), 2)
        await asyncio.wait_for(boundary.join_stamps(cancel=True), 2)


async def test_postcommit_cancellation_owes_the_stamp_before_a_held_notification():
    """Root's POSTCOMMIT-CANCEL control: cancelled after the commit callback,
    while write_chunk awaits its buffer cleanup, the cohort is owed (every
    chunk id) at once, not after its held market notification; the sender is
    still owned and joined, and the event stays reserved until it returns."""
    committed, notifying = asyncio.Event(), asyncio.Event()
    release_notification, finish_cleanup = asyncio.Event(), asyncio.Event()

    async def write(chunk, *, start_market_publish):
        start_market_publish(object())
        committed.set()
        await finish_cleanup.wait()
        return pm._PMPriceWriteResult([900])

    async def publish(session):
        notifying.set()
        await release_notification.wait()

    deps = _writer_deps(write)
    deps["publish"] = publish
    wake = asyncio.Event()
    w = pm._PMBridgeWriter(wake)
    w.offer([900, 901], {2}, **deps)
    try:
        await asyncio.wait_for(committed.wait(), 1)
        await asyncio.wait_for(notifying.wait(), 1)
        wake.clear()
        w.task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert w.completed == [([900, 901], {900: "m900", 901: "m901"}, {2})]
        assert wake.is_set() and w.unstamped == set()
        assert w.reserved == {2} and not w.task.done(), "sender not joined"
    finally:
        finish_cleanup.set()
        release_notification.set()
        await asyncio.wait_for(asyncio.gather(w.task, return_exceptions=True), 1)
    assert len(w.take_completed()) == 1 and not w.reserved


async def test_retry_held_bridged_events_are_written_apart_then_recover(monkeypatch):
    """Root's BRIDGE-RETRY-ISOLATION control: after a joint lock rollback left
    events 2 and 3 retry-held, each is its own cohort, so NOWAIT refusals on
    locked event 2 never roll back event 3, which commits and is stamped while
    2 stays locked; 2 recovers once its holder lets go."""
    p, x = _many_bridges(monkeypatch, events=(2, 3))
    p.ns["price_buffer"].pop(1)
    p.ns["price_buffer"].pop(2)
    p.ns["FLUSH_CHUNK_ROWS"] = 250
    p.ns["lock_retry_until"].update(dict.fromkeys((900, 901, 902, 903), 0.0))
    p.ns["lock_retry_events"].update((2, 3))
    attempts, locked = [], [True]
    original = p.ns["write_chunk"]

    async def locked_a(chunk, **kwargs):
        attempts.append(tuple(chunk))
        if 900 in chunk and locked[0]:
            return None  # NOWAIT refusal on event 2's held rows
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = locked_a
    boundary = p.ns["catalog_boundary"]
    x.release.set()

    async def flush():
        await p.ns["_flush_prices"](flush_started=time.monotonic())
        await asyncio.wait_for(boundary.bridges.join(), 1)
        await asyncio.sleep(0)

    try:
        for _ in range(2):
            await flush()
        assert not any(900 in c and 902 in c for c in attempts), attempts
        assert any(902 in c for c in attempts), attempts
        assert 902 not in p.ns["price_buffer"] and {900, 901} <= set(p.ns["price_buffer"])
        await flush()  # takes event 3's completion and stamps it
        await asyncio.wait_for(boundary.join_stamps(), 1)
        assert ("event_frame", 3) in p.trace and ("event_frame", 2) not in p.trace
        locked[0] = False
        for _ in range(2):
            await flush()
        await asyncio.wait_for(boundary.join_stamps(), 1)
        assert not p.ns["price_buffer"]
        assert ("event_frame", 2) in p.trace
    finally:
        await asyncio.wait_for(boundary.bridges.join(), 1)
        await asyncio.wait_for(boundary.join_stamps(cancel=True), 1)


async def test_retry_held_bridged_events_take_turns_for_the_queue(monkeypatch):
    """Two locked retry-held events at the head of the buffer cannot keep a
    third retry-held but unlocked event out of the bounded queue: retried
    events are offered least recently offered first."""
    assert pm.PM_BRIDGE_QUEUE_LIMIT == 2
    p, x = _many_bridges(monkeypatch, events=(2, 3, 4))
    p.ns["price_buffer"].pop(1)
    p.ns["price_buffer"].pop(2)
    p.ns["FLUSH_CHUNK_ROWS"] = 250
    p.ns["lock_retry_until"].update(dict.fromkeys(range(900, 906), 0.0))
    p.ns["lock_retry_events"].update((2, 3, 4))
    original = p.ns["write_chunk"]

    async def two_locked(chunk, **kwargs):
        if 900 in chunk or 902 in chunk:
            return None
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = two_locked
    boundary = p.ns["catalog_boundary"]
    x.release.set()
    try:
        for _ in range(3):
            await p.ns["_flush_prices"](flush_started=time.monotonic())
            await asyncio.wait_for(boundary.bridges.join(), 1)
            await asyncio.sleep(0.002)  # distinct offer clocks
        assert 904 not in p.ns["price_buffer"], "event 4 never reached the queue"
        assert {900, 901, 902, 903} <= set(p.ns["price_buffer"])
    finally:
        await asyncio.wait_for(boundary.bridges.join(), 1)
        await asyncio.wait_for(boundary.join_stamps(cancel=True), 1)
