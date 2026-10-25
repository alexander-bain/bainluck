"""#10090 — the PM release wake on real PostgreSQL, with the stage trace off and on.

## the ship

Unrelated game probabilities publish without waiting a wasted cadence, and a
released game's newer quote reaches the page promptly.

## the rig

The SHIPPED game flush closures (`flush_prices`, `_flush_prices`, ...) and the
SHIPPED `write_chunk`, compiled from `app/tasks/polymarket_ws.py` against the
existing #10651 namespace, driven by the SHIPPED `run_flush_cadence` at
production's 250 ms override (wake + work count + 5 ms coalesce). Every price
is a real chunk UPDATE + re-rank + commit, and every stamp a real
`LiveBlendRefresher` transaction (reader, orientation, atomic stamp, revision
trigger), on the consumer's own five-connection pool over the #8129 schema.
Event and market frames go through the real `_publish` /
`publish_committed_market_changes` to a recording Redis connection that reads
the committed row back on an INDEPENDENT connection before it acknowledges.

A stamp is held by a real row lock: a second connection holds
`SELECT ... FOR UPDATE` on that events row, so the refresher's stamp UPDATE
waits inside Postgres (observed in `pg_stat_activity`) until it rolls back.

## what is asserted, and what is printed

The wake is a SCHEDULING decision, so that is what is asserted: when the flush
that wrote a quote STARTED, measured from the quote's arrival (the peer) or
from the window's actual `release` of its held event. Before the release wake
both waited for the next 250 ms periodic timer (~0.2 s); with it they start
within milliseconds. The commit, stamp, readback and publication that follow
are real and are asserted for value, revision and order; their end-to-end ages
depend on the host's load and are printed as `EVIDENCE`, not bounded.

Each case runs with the default-off stage trace OFF and ON for event 1's
outcome: turning the diagnostic on must not replace the functional release wake
(`_FreshAdmission.release_wake` vs `.on_release`), and the trace must name the
exact input, fence, release and stamp on the real rows.

Synthetic rows on one machine: order, coherence and scheduling — not
production timing.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import itertools
import json
import logging
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from app.tasks.base import get_task_session
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
    seed,
)
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions
from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

PERIOD = 0.25  # production's PM_WS_PRICE_FLUSH_SECONDS override
#: A wake-started flush starts within this of its trigger (measured a few ms;
#: the 5 ms coalesce is inside it). A timer-paced one starts ~0.2 s later.
START_BOUND_S = 0.100
#: How far past the 250 ms floor a floor-paced flush may start.
FLOOR_MARGIN_S = 0.100
#: #8129's seed: outcome N is event N's home leg, on market N.
EVENT_1_OUTCOME, PEER_OUTCOME, HELD_SIBLING_OUTCOME = 1, 2, 3


class _Connection:
    """Recording Redis connection: acknowledges a frame only after an
    independent database connection reads back exactly what it names."""

    def __init__(self, sink):
        self.sink = sink
        self.replies = []

    def pack_commands(self, commands):
        return list(commands)

    async def send_packed_command(self, commands, **_kw):
        for command in commands:
            payload = json.loads(command[2] if command[0] == "PUBLISH" else command[5])
            await self.sink(payload)
            self.replies.append(0)

    async def read_response(self, **_kw):
        return self.replies.pop(0)

    async def disconnect(self):
        pass


class _Pool:
    def __init__(self, sink):
        self.connection = _Connection(sink)

    async def get_connection(self, *_a):
        return self.connection

    async def release(self, _conn):
        pass


@pytest.fixture
async def consumer(rig):
    """The consumer's own pool (`ws_consumer_sessions`: `_get_task_engine(
    retain_full_pool=True)`, five connections, no overflow), opened first as a
    running consumer's are, so a flush does not pay connection setup. Holders
    and readbacks use the rig's separate engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    async with rig.engine.connect() as conn:
        schema = await conn.scalar(text("SELECT current_schema()"))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": schema}},
        pool_size=5, max_overflow=0,
    )
    for pool_engine in (engine, rig.engine):
        async with contextlib.AsyncExitStack() as stack:
            for _ in range(5):
                conn = await stack.enter_async_context(pool_engine.connect())
                await conn.execute(text("SELECT 1"))
    try:
        yield engine
    finally:
        await engine.dispose()


async def build(rig, consumer, monkeypatch, *, trace: bool, lock_ms: int):
    await seed(rig, 3)
    session_factory = functools.partial(get_task_session, engine=consumer)
    r = blend.LiveBlendRefresher(
        "polymarket", min_refresh_interval_s=PERIOD,
        session_factory=session_factory, stamp_lock_timeout_ms=lock_ms,
    )
    receipts = blend.TailReceipts("polymarket")
    r.receipts = receipts
    lines: list[dict] = []
    event_of = {EVENT_1_OUTCOME: 1, PEER_OUTCOME: 2, HELD_SIBLING_OUTCOME: 3}
    stage_trace = None
    if trace:
        from app.utils.pm_stage_trace import PMStageTrace

        stage_trace = receipts.exact_trace = PMStageTrace.from_env(
            {
                "WS_PM_TRACE_EVENT": "1",
                "WS_PM_TRACE_OUTCOMES": str(EVENT_1_OUTCOME),
                "WS_PM_TRACE_EXPIRES_AT": str(time.time() + 300),
                "WS_PM_TRACE_MAX_LINES": "256",
            },
            run="pg", event_of=event_of,
            emit=lambda record: lines.append(json.loads(json.dumps(record))),
        )
        assert stage_trace is not None

    # Every actual window release (an observer only: it calls the original).
    releases: list[tuple[float, frozenset]] = []
    original_release = blend._FreshAdmission.release

    def recorded_release(self, event_ids):
        releases.append((time.monotonic(), frozenset(event_ids)))
        return original_release(self, event_ids)

    monkeypatch.setattr(blend._FreshAdmission, "release", recorded_release)

    pubs: list[tuple[float, int, float, int]] = []

    async def sink(payload):
        async with rig.engine.connect() as conn:
            if "outcome_ids" in payload:
                rows = (await conn.execute(
                    text(
                        "SELECT id, last_updated FROM futures_outcomes "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": payload["outcome_ids"]},
                )).all()
                assert {row.id for row in rows} == set(payload["outcome_ids"])
                for row in rows:
                    assert (
                        row.last_updated.isoformat()
                        == payload["outcome_observed_at"][str(row.id)]
                    )
                return
            eid = payload["event_id"]
            row = (await conn.execute(
                text(
                    "SELECT win_probability_sources, win_probability_sources_rev "
                    "FROM events WHERE id = :id"
                ),
                {"id": eid},
            )).one()
            # Only what is committed can be acknowledged.
            stored = row.win_probability_sources["polymarket"]["value"]
            assert stored == payload["source_value"]
            assert row.win_probability_sources_rev == payload["rev"][str(eid)]
            pubs.append((time.monotonic(), eid, stored, payload["rev"][str(eid)]))

    client = SimpleNamespace(connection_pool=_Pool(sink))
    r._client = lambda: client

    p = pm_rig(batch={}, mapping=dict(event_of), books={})
    # Local111 adapter: the extracted closure needs its actual new module global.
    p.release.set()
    from app.tasks.polymarket_open_contracts import (
        FLUSH_CHUNK_ROWS, OPEN_FLUSH_CHUNKS_PER_FLUSH,
    )
    from app.utils import market_quote_push
    from app.utils.futures_rank import rerank_market_fields_stmt

    p.ns.update(
        FLUSH_CHUNK_ROWS=FLUSH_CHUNK_ROWS,
        OPEN_FLUSH_CHUNKS_PER_FLUSH=OPEN_FLUSH_CHUNKS_PER_FLUSH,
        PRICE_FLUSH_SECONDS=pm.PRICE_FLUSH_SECONDS,
        open_outcome_ids=set(),
        open_complement_of={},
        market_by_outcome=dict(event_of),
        input_marks={},
        get_task_session=session_factory,
        blend_refresher=r,
        tail_receipts=receipts,
        logger=logging.getLogger(__name__),
        chunk_price_update_stmt=pm.chunk_price_update_stmt,
        queue_market_change=market_quote_push.queue_market_change,
        rerank_market_fields_stmt=rerank_market_fields_stmt,
        _PMPriceWriteResult=pm._PMPriceWriteResult,
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], p.ns)

    flush_starts: list[float] = []
    #: (flush_started of the flush that wrote it, {outcome: value}) per commit.
    writes: list[tuple[float, dict]] = []
    shipped_write = p.ns["write_chunk"]

    async def recorded_write(chunk, **kwargs):
        values = dict(chunk)
        result = await shipped_write(chunk, **kwargs)
        if result:
            writes.append((flush_starts[-1], values))
        return result

    p.ns["write_chunk"] = recorded_write

    seqs = itertools.count(1)
    boundary = p.ns["catalog_boundary"]

    def accept(oid, value):
        """`handle_price`'s order: buffer, mark (trace accept), then wake."""
        seq = next(seqs)
        mark = blend.InputMark(
            seq=seq, event_id=event_of[oid], outcome_id=oid, probability=value,
            kind="price", recv_wall=time.time(), recv_mono=time.monotonic(),
            venue_ts_ms=None, event_ordinal=seq,
        )
        p.ns["price_buffer"][oid] = value
        p.ns["input_marks"][oid] = mark
        if stage_trace is not None:
            stage_trace.input_accepted(mark)
        wake_outcomes = getattr(boundary, "wake_for_outcomes", None)
        if wake_outcomes is not None:
            wake_outcomes(
                [oid], p.ns["open_outcome_ids"], p.ns["event_id_by_outcome"],
                p.ns["non_blend_outcome_ids"],
            )
        else:
            boundary.flush_wake.set()
        return mark

    async def tracked_flush(started: float):
        flush_starts.append(started)
        return await p.ns["flush_prices"](flush_started=started)

    return SimpleNamespace(
        r=r, p=p, boundary=boundary, accept=accept, pubs=pubs, lines=lines,
        flush_starts=flush_starts, writes=writes, releases=releases,
        tracked_flush=tracked_flush, trace=stage_trace,
    )


def start_cadence(t, stop):
    t.boundary.flush_wake.set()
    return asyncio.create_task(
        blend.run_flush_cadence(
            t.tracked_flush, PERIOD, stop=stop,
            failed_retry_interval_s=pm.PRICE_FLUSH_SECONDS,
            wake=t.boundary.flush_wake,
            work_count=lambda: t.boundary.flush_work,
            wake_coalesce_s=pm.PM_WAKE_COALESCE_SECONDS,
        )
    )


async def stop_cadence(t, stop, cadence):
    stop.set()
    t.boundary.flush_wake.set()
    await asyncio.wait_for(cadence, timeout=5.0)
    await t.boundary.join_stamps()
    await t.r.drain_history()


async def wait_for(predicate, timeout=3.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.002)


async def hold_event_row(rig, event_id):
    """A second transaction holds events row `event_id` FOR UPDATE."""
    conn = await rig.engine.connect()
    tx = await conn.begin()
    pid = await conn.scalar(text("SELECT pg_backend_pid()"))
    await conn.execute(
        text("SELECT id FROM events WHERE id = :id FOR UPDATE"), {"id": event_id}
    )
    return conn, tx, pid


async def lock_waiters(rig, *holder_pids) -> int:
    """Backends waiting on THIS test's holders (not a sibling test's)."""
    async with rig.engine.connect() as conn:
        return await conn.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' "
                "AND pg_blocking_pids(pid) && CAST(:pids AS int[])"
            ),
            {"pids": list(holder_pids)},
        )


async def wait_for_lock_waiters(rig, count, *holder_pids):
    for _ in range(400):
        if await lock_waiters(rig, *holder_pids) >= count:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"{count} stamp(s) never waited on the held row lock(s)")


def wrote_at(t, oid, value) -> float:
    """`flush_started` of the flush whose commit wrote `oid` = `value`."""
    return next(started for started, values in t.writes if values.get(oid) == value)


def released_at(t, event_id, after) -> float:
    """The window's first actual release of `event_id` at or after `after`."""
    return next(at for at, ids in t.releases if event_id in ids and at >= after)


def published_at(t, event_id, value) -> float:
    return next(at for at, eid, v, _ in t.pubs if eid == event_id and v == value)


def stage(lines, name):
    return [line for line in lines if line["stage"] == name]


async def run_held_event_case(rig, consumer, monkeypatch, *, trace,
                              release_after_peer_s, lock_ms, fenced_tick_s=None):
    """Event 1's first stamp waits on a real row lock; a newer event-1 quote is
    fenced by the next flush; then the peer's quote arrives and, after
    `release_after_peer_s`, the lock holder rolls back.

    `fenced_tick_s`: event 1 keeps moving while fenced (latest wins, no spin).
    """
    t = await build(rig, consumer, monkeypatch, trace=trace, lock_ms=lock_ms)
    holder, tx, holder_pid = await hold_event_row(rig, 1)
    stop = asyncio.Event()
    t0 = time.monotonic()
    marks = {"first": t.accept(EVENT_1_OUTCOME, 0.60)}
    latest = [0.64]
    cadence = start_cadence(t, stop)
    ticker = None
    try:
        # Flush 1 writes event 1 and its stamp waits inside Postgres.
        await wait_for_lock_waiters(rig, 1, holder_pid)
        await asyncio.sleep(max(0.0, 0.100 - (time.monotonic() - t0)))
        marks["newer"] = t.accept(EVENT_1_OUTCOME, 0.64)
        # Flush 2 fences event 1's newer quote while its stamp is held.
        await wait_for(
            lambda: len(t.flush_starts) >= 2
            and t.p.ns["stats"]["stamp_fenced"] >= 1
            and t.boundary.active == 0
        )
        work_after_fenced = t.boundary.flush_work
        await asyncio.sleep(0.040)
        t_peer = time.monotonic()
        marks["peer"] = t.accept(PEER_OUTCOME, 0.75)
        if fenced_tick_s is not None:
            async def tick():
                k = 0
                while True:
                    await asyncio.sleep(fenced_tick_s)
                    k += 1
                    latest[0] = round(0.64 + 0.001 * k, 4)
                    marks["latest"] = t.accept(EVENT_1_OUTCOME, latest[0])

            ticker = asyncio.create_task(tick())
        await asyncio.sleep(max(0.0, t_peer + release_after_peer_s - time.monotonic()))
        if ticker is not None:
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)
        t_release_called = time.monotonic()
        await tx.rollback()
        await wait_for(lambda: any(
            eid == 1 and v == latest[0] for _, eid, v, _ in t.pubs
        ))
        await wait_for(lambda: any(eid == 2 for _, eid, _, _ in t.pubs))
    finally:
        if ticker is not None:
            ticker.cancel()
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        await stop_cadence(t, stop, cadence)

    ev1 = [(v, rev) for _, eid, v, rev in t.pubs if eid == 1]
    ev1_release = released_at(t, 1, t_release_called)
    out = dict(
        trace=trace,
        lock_ms=lock_ms,
        latest=latest[0],
        work_after_fenced=work_after_fenced,
        # Scheduling: when the flush that wrote each quote started.
        peer_flush_after_arrival_s=round(wrote_at(t, PEER_OUTCOME, 0.75) - t_peer, 4),
        ev1_flush_after_release_s=round(
            wrote_at(t, EVENT_1_OUTCOME, latest[0]) - ev1_release, 4
        ),
        peer_flush=wrote_at(t, PEER_OUTCOME, 0.75),
        ev1_flush=wrote_at(t, EVENT_1_OUTCOME, latest[0]),
        flushes_peer_to_release=sum(
            1 for s in t.flush_starts if t_peer <= s <= t_release_called
        ),
        # End to end (host-load dependent): committed, read back, acknowledged.
        peer_published_after_arrival_s=round(published_at(t, 2, 0.75) - t_peer, 4),
        ev1_published_after_release_s=round(
            published_at(t, 1, latest[0]) - ev1_release, 4
        ),
        ev1_values=[v for v, _ in ev1],
        ev1_revs=[rev for _, rev in ev1],
        t_release_called=t_release_called,
        ev1_release=ev1_release,
        final_at=published_at(t, 1, latest[0]),
        flush_starts_rel=[round(s - t0, 4) for s in t.flush_starts],
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
    )
    evidence(dict(out, case=f"release+{release_after_peer_s}s/lock{lock_ms}ms"))
    return t, out, marks


def evidence(out):
    hidden = ("t_release_called", "ev1_release", "final_at", "peer_flush", "ev1_flush")
    print("EVIDENCE", json.dumps(
        {k: v for k, v in out.items() if k not in hidden}, sort_keys=True,
    ))


def assert_delivered(out):
    assert out["errors"] == 0 and out["price_errors"] == 0, out
    assert out["pending_after"] == [] and out["buffer_after"] == {}, out
    # Latest wins: the last committed event-1 value is the newest quote, and
    # revisions only move forward.
    assert out["ev1_values"][-1] == out["latest"], out
    assert out["ev1_revs"] == sorted(set(out["ev1_revs"])), out


def assert_exact_trace_receipts(t, out, marks):
    """The trace names the exact input, the held attempt that fenced it, that
    attempt's release (the SAME `release` the functional wake answered), and
    the stamp and publication that carried the newest input."""
    lines = t.lines
    assert not stage(lines, "STOP"), stage(lines, "STOP")
    accepted = {line["input_seq"]: line for line in stage(lines, "ACCEPTED")}
    newest = marks.get("latest", marks["newer"])
    assert accepted[newest.seq]["probability"] == out["latest"]
    assert marks["peer"].seq not in accepted  # not a selected outcome
    (fenced,) = stage(lines, "FENCED")
    held = fenced["held_attempt"]
    (released,) = [a for a in stage(lines, "ATTEMPT") if a["attempt"] == held]
    assert released["fenced_ours"] is True, released
    # One clock, one call: the diagnostic saw the release the wake answered.
    assert abs(released["released_mono"] - out["ev1_release"]) < 0.005, (released, out)
    assert released["released_mono"] >= out["t_release_called"], (released, out)
    (committed,) = [
        c for c in stage(lines, "PRICE_COMMITTED") if c["input_seq"] == newest.seq
    ]
    assert committed["probability"] == out["latest"]
    assert committed["commit_mono"] >= released["released_mono"]
    (event_line,) = [
        e for e in stage(lines, "EVENT_COMMITTED") if e["input_seq"] == newest.seq
    ]
    assert event_line["linkage"] == "EXACT_OUTCOME_OBSERVATION_BASIS"
    assert event_line["revision"] == out["ev1_revs"][-1]
    assert event_line["attempt"] != held
    (publication,) = [
        e for e in stage(lines, "EVENT_PUBLICATION") if e["input_seq"] == newest.seq
    ]
    assert publication["publication"] == "REDIS_ACK"
    assert publication["revision"] == out["ev1_revs"][-1]


@pytest.mark.parametrize("trace", [False, True], ids=["trace-off", "trace-on"])
async def test_peer_and_released_event_flush_on_the_wake_not_the_next_timer(
    rig, consumer, monkeypatch, trace,
):
    """Event 1 releases after the second periodic probe (~0.57 s). A finite
    2 s stamp lock bound keeps the held attempt waiting that long (production's
    500 ms bound is the next case); event 1 keeps moving every 25 ms while
    fenced, so the wake must not spin and the latest value must win."""
    t, out, marks = await run_held_event_case(
        rig, consumer, monkeypatch, trace=trace, release_after_peer_s=0.270,
        lock_ms=2000, fenced_tick_s=0.025,
    )
    # The peer flushes at once: a 100%-fenced flush spent no socket budget.
    assert out["peer_flush_after_arrival_s"] < START_BOUND_S, out
    # The released event's newest quote flushes on the release wake.
    assert out["ev1_flush_after_release_s"] < START_BOUND_S, out
    assert_delivered(out)
    assert out["work_after_fenced"] == 1, out
    # No spin: event 1's fenced ticks woke nothing. From the peer's arrival to
    # the release (0.27 s) only the peer's flush and one timer probe start.
    assert out["flushes_peer_to_release"] <= 2, out
    if trace:
        assert_exact_trace_receipts(t, out, marks)


@pytest.mark.parametrize("trace", [False, True], ids=["trace-off", "trace-on"])
async def test_release_inside_the_peer_budget_window_waits_at_most_its_floor(
    rig, consumer, monkeypatch, trace,
):
    """Production's 500 ms stamp lock bound; event 1 releases ~45 ms after the
    peer arrives, inside the 250 ms window the peer's flush opened. The peer
    still flushes at once; event 1's newer quote waits for that floor and no
    more than `FLOOR_MARGIN_S` past it (the bounded tradeoff, kept visible)."""
    t, out, marks = await run_held_event_case(
        rig, consumer, monkeypatch, trace=trace, release_after_peer_s=0.045,
        lock_ms=blend.DEFAULT_STAMP_LOCK_TIMEOUT_MS,
    )
    assert out["peer_flush_after_arrival_s"] < START_BOUND_S, out
    assert_delivered(out)
    assert out["work_after_fenced"] == 1, out
    floor = out["peer_flush"] + PERIOD
    assert out["ev1_flush"] >= floor - 0.010, out
    assert out["ev1_flush"] - floor < FLOOR_MARGIN_S, out
    if trace:
        assert_exact_trace_receipts(t, out, marks)


@pytest.mark.parametrize("trace", [False, True], ids=["trace-off", "trace-on"])
async def test_a_mid_call_release_wakes_the_flush_while_the_call_still_holds_another_game(
    rig, consumer, monkeypatch, trace,
):
    """One stamp call holds events 1 and 3 on two real row locks. Event 1's
    newer quote is fenced; then event 1's holder lets go while event 3's keeps
    its lock, so the call is still running. Only the window's `release` can
    wake the flush here (the call's task has not finished): the newer quote
    must be written, admitted to the running call and published on that wake,
    and the stage trace's `on_release` observes the same release without
    replacing it."""
    t = await build(rig, consumer, monkeypatch, trace=trace, lock_ms=2000)
    holders = {eid: await hold_event_row(rig, eid) for eid in (1, 3)}
    stop = asyncio.Event()
    t0 = time.monotonic()
    marks = {"first": t.accept(EVENT_1_OUTCOME, 0.60)}
    marks["peer"] = t.accept(HELD_SIBLING_OUTCOME, 0.30)
    cadence = start_cadence(t, stop)
    try:
        await wait_for_lock_waiters(rig, 2, *(pid for _, _, pid in holders.values()))
        owner = t.boundary.stamps
        call = owner.task
        await asyncio.sleep(max(0.0, 0.100 - (time.monotonic() - t0)))
        marks["newer"] = t.accept(EVENT_1_OUTCOME, 0.64)
        await wait_for(
            lambda: len(t.flush_starts) >= 2
            and t.p.ns["stats"]["stamp_fenced"] >= 1
            and t.boundary.active == 0
        )
        work_after_fenced = t.boundary.flush_work
        # Just after the fenced probe: the old periodic phase is ~235 ms away.
        await asyncio.sleep(0.010)
        t_release_called = time.monotonic()
        await holders[1][1].rollback()
        await wait_for(lambda: any(eid == 1 and v == 0.64 for _, eid, v, _ in t.pubs))
        # The same call still holds event 3: no task-done wake could have run.
        call_still_holding = owner.task is call and not call.done()
        sibling_unpublished = not any(eid == 3 for _, eid, _, _ in t.pubs)
        await holders[3][1].rollback()
        await wait_for(lambda: any(eid == 3 for _, eid, _, _ in t.pubs))
    finally:
        for conn, tx, _ in holders.values():
            with contextlib.suppress(Exception):
                await tx.rollback()
            await conn.close()
        await stop_cadence(t, stop, cadence)

    ev1 = [(v, rev) for _, eid, v, rev in t.pubs if eid == 1]
    ev1_release = released_at(t, 1, t_release_called)
    out = dict(
        case="mid-call-release",
        trace=trace,
        latest=0.64,
        work_after_fenced=work_after_fenced,
        call_still_holding=call_still_holding,
        sibling_unpublished=sibling_unpublished,
        ev1_flush_after_release_s=round(
            wrote_at(t, EVENT_1_OUTCOME, 0.64) - ev1_release, 4
        ),
        ev1_published_after_release_s=round(published_at(t, 1, 0.64) - ev1_release, 4),
        ev1_values=[v for v, _ in ev1],
        ev1_revs=[rev for _, rev in ev1],
        t_release_called=t_release_called,
        ev1_release=ev1_release,
        final_at=published_at(t, 1, 0.64),
        flush_starts_rel=[round(s - t0, 4) for s in t.flush_starts],
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
    )
    evidence(out)
    assert out["call_still_holding"] and out["sibling_unpublished"], out
    assert out["ev1_flush_after_release_s"] < START_BOUND_S, out
    assert_delivered(out)
    assert out["work_after_fenced"] == 1, out
    if trace:
        assert_exact_trace_receipts(t, out, marks)


@pytest.mark.parametrize("seed", ["fresh", "quiet-debt"])
@pytest.mark.parametrize("trace", [False, True], ids=["trace-off", "trace-on"])
async def test_a_cancelled_held_stamp_keeps_its_debt_and_a_new_cadence_recovers(
    rig, consumer, monkeypatch, trace, seed,
):
    """Shutdown while event 1's stamp waits on the row lock and its newer quote
    is fenced: the held call is cancelled inside Postgres, the debt and the
    buffered quote survive, nothing wakes, and a fresh cadence's first flush
    writes and publishes the newer value once the holder is gone. `quiet-debt`:
    the held stamp is owed debt a quiet flush handed to the owner (its cohort
    already stored), not a fresh input."""
    t = await build(rig, consumer, monkeypatch, trace=trace, lock_ms=2000)
    holder, tx, holder_pid = await hold_event_row(rig, 1)
    stop = asyncio.Event()
    if seed == "fresh":
        t.accept(EVENT_1_OUTCOME, 0.60)
    else:
        t.r.keep_owed({1})
    cadence = start_cadence(t, stop)
    try:
        await wait_for_lock_waiters(rig, 1, holder_pid)
        newer = t.accept(EVENT_1_OUTCOME, 0.66)
        await wait_for(
            lambda: t.p.ns["stats"]["stamp_fenced"] >= 1 and t.boundary.active == 0
        )
        stop.set()
        t.boundary.flush_wake.set()
        await asyncio.wait_for(cadence, timeout=5.0)
        # Our own stop signal is spent; only the cancel below could set it.
        t.boundary.flush_wake.clear()
        owner = t.boundary.stamps
        await t.boundary.join_stamps(cancel=True)
        assert getattr(owner, "fenced", set()) == set()
        assert not t.boundary.flush_wake.is_set()
        assert 1 in t.r.pending_event_ids()
        assert t.p.ns["price_buffer"] == {EVENT_1_OUTCOME: 0.66}
        assert await lock_waiters(rig, holder_pid) == 0, (
            "the cancelled stamp still waits in Postgres"
        )
        assert not any(eid == 1 for _, eid, _, _ in t.pubs)
    finally:
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        if not cadence.done():
            # A failed assertion above: stop and reap the cadence and its stamp
            # owner before the fixture drops the schema under them.
            stop.set()
            t.boundary.flush_wake.set()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(cadence, timeout=5.0)
            with contextlib.suppress(Exception):
                await t.boundary.join_stamps(cancel=True)
    stop = asyncio.Event()
    restart = len(t.flush_starts)
    t_restart = time.monotonic()
    cadence = start_cadence(t, stop)
    try:
        await wait_for(lambda: any(eid == 1 and v == 0.66 for _, eid, v, _ in t.pubs))
    finally:
        await stop_cadence(t, stop, cadence)
    evidence(dict(
        case=f"cancel-recover/{seed}", trace=trace,
        published_after_restart_s=round(published_at(t, 1, 0.66) - t_restart, 4),
    ))
    # The restarted cadence's FIRST flush carries the retained quote.
    assert wrote_at(t, EVENT_1_OUTCOME, 0.66) == t.flush_starts[restart]
    assert not t.r.pending_event_ids() and not t.p.ns["price_buffer"]
    if trace:
        assert not stage(t.lines, "STOP")
        assert [
            e for e in stage(t.lines, "EVENT_COMMITTED") if e["input_seq"] == newer.seq
        ]


async def test_quiet_owed_debt_on_a_held_event_never_holds_an_unrelated_quote(
    rig, consumer, monkeypatch,
):
    """Event 1 owes a stamp (`keep_owed`: its cohort is already stored) and a
    second transaction holds its row. The cadence's first flush has no price,
    so it is the quiet ending: it hands that debt to the stamp owner and
    returns. Event 2's fresh quote then flushes at the next 250 ms floor and
    publishes while event 1's stamp still waits in Postgres; a newer event-1
    quote stays fenced behind it; once the holder lets go event 1 publishes its
    stored value, then the newer one. Before, the quiet flush awaited the held stamp,
    so no flush could start until the release (Root, real PG: 0.81 s)."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=2000)
    t.r.keep_owed({1})
    holder, tx, holder_pid = await hold_event_row(rig, 1)
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    peer_before_release = still_waiting = False
    try:
        await wait_for_lock_waiters(rig, 1, holder_pid)
        quiet_flush = t.flush_starts[0]
        t_peer = time.monotonic()
        t.accept(PEER_OUTCOME, 0.63)
        with contextlib.suppress(TimeoutError):
            await wait_for(
                lambda: any(eid == 2 and v == 0.63 for _, eid, v, _ in t.pubs), 1.0,
            )
        peer_before_release = any(eid == 2 for _, eid, _, _ in t.pubs)
        # A newer quote for the held event: it waits behind its owed stamp.
        t.accept(EVENT_1_OUTCOME, 0.66)
        with contextlib.suppress(TimeoutError):  # no flush ran: the asserts say so
            await wait_for(lambda: t.p.ns["stats"]["stamp_fenced"] >= 1, 1.0)
        still_waiting = await lock_waiters(rig, holder_pid) == 1
        await tx.rollback()
        await wait_for(lambda: any(eid == 1 and v == 0.66 for _, eid, v, _ in t.pubs))
        await wait_for(lambda: any(eid == 2 for _, eid, _, _ in t.pubs))
    finally:
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        await stop_cadence(t, stop, cadence)
    out = dict(
        case="quiet-debt-peer",
        peer_before_release=peer_before_release,
        owed_stamp_still_waiting=still_waiting,
        peer_flush_after_quiet_flush_s=round(
            wrote_at(t, PEER_OUTCOME, 0.63) - quiet_flush, 4
        ),
        peer_published_after_arrival_s=round(published_at(t, 2, 0.63) - t_peer, 4),
        ev1_values=[v for _, eid, v, _ in t.pubs if eid == 1],
        ev1_revs=[rev for _, eid, _, rev in t.pubs if eid == 1],
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
    )
    evidence(out)
    # Published while event 1's owed stamp still waited on its row lock.
    assert out["peer_before_release"] and out["owed_stamp_still_waiting"], out
    # Scheduling: the next budget floor after the quiet flush, not the release.
    assert out["peer_flush_after_quiet_flush_s"] < PERIOD + FLOOR_MARGIN_S, out
    # The owed event recovers its stored value, then its newer quote; revisions
    # strictly advance; nothing stays owed or buffered.
    assert out["ev1_values"] == [0.7, 0.66], out
    assert out["ev1_revs"] == sorted(set(out["ev1_revs"])), out
    assert out["errors"] == 0 and out["price_errors"] == 0, out
    assert out["pending_after"] == [] and out["buffer_after"] == {}, out


async def hold_outcome_row(rig, outcome_id):
    """A second transaction holds futures_outcomes row `outcome_id` FOR UPDATE."""
    conn = await rig.engine.connect()
    tx = await conn.begin()
    pid = await conn.scalar(text("SELECT pg_backend_pid()"))
    await conn.execute(
        text("SELECT id FROM futures_outcomes WHERE id = :id FOR UPDATE"),
        {"id": outcome_id},
    )
    return conn, tx, pid


def bridged_rig(t):
    """Event 2's leg becomes an event-bridged OPEN leg (the bridged writer's).
    The chunk lock budget is raised past the hold so the held UPDATE waits in
    Postgres for the whole hold instead of timing out (production: 500 ms)."""
    t.p.ns["open_outcome_ids"].add(PEER_OUTCOME)
    t.p.ns["PRICE_CHUNK_LOCK_TIMEOUT_MS"] = 5000
    t.p.ns["PRICE_STATEMENT_LOCK_TIMEOUT_MS"] = 5000
    bridged: list[tuple[float, float, dict]] = []
    inner = t.p.ns["write_chunk"]

    async def timed(chunk, **kwargs):
        started = time.monotonic()
        try:
            return await inner(chunk, **kwargs)
        finally:
            if PEER_OUTCOME in chunk:
                bridged.append((started, time.monotonic(), dict(chunk)))

    t.p.ns["write_chunk"] = timed
    return bridged


async def test_a_held_bridged_open_write_never_holds_the_next_game_quote(
    rig, consumer, monkeypatch,
):
    """#10090 bridged writer. Event 2's bridged open leg is written by the
    bridged writer while a second transaction holds its futures_outcomes row,
    so that UPDATE waits inside Postgres. Event 1's newer quote meanwhile
    commits, stamps and is acknowledged from its committed row. A newer event-2
    quote arriving during the hold waits buffered (no second writer, no stamp
    of event 2 on the old board). After the holder lets go, event 2 commits
    and its own stamp publishes, then its newer quote: latest wins, revisions
    advance. On the parent the game flush awaited this write, so event 1's
    newer quote could not even be written until the release."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=2000)
    bridged = bridged_rig(t)
    holder, tx, holder_pid = await hold_outcome_row(rig, PEER_OUTCOME)
    stop = asyncio.Event()
    t.accept(EVENT_1_OUTCOME, 0.60)
    t.accept(PEER_OUTCOME, 0.75)
    cadence = start_cadence(t, stop)
    selected_before_release = still_waiting = ev2_before_release = False
    try:
        await wait_for_lock_waiters(rig, 1, holder_pid)
        await wait_for(lambda: any(eid == 1 and v == 0.60 for _, eid, v, _ in t.pubs))
        t_new = time.monotonic()
        t.accept(EVENT_1_OUTCOME, 0.64)
        t.accept(PEER_OUTCOME, 0.77)  # newer bridged quote during the hold
        with contextlib.suppress(TimeoutError):  # the asserts below say so
            await wait_for(
                lambda: any(eid == 1 and v == 0.64 for _, eid, v, _ in t.pubs), 1.5,
            )
        selected_before_release = any(eid == 1 and v == 0.64 for _, eid, v, _ in t.pubs)
        still_waiting = await lock_waiters(rig, holder_pid) == 1
        ev2_before_release = any(eid == 2 for _, eid, _, _ in t.pubs)
        t_release = time.monotonic()
        await tx.rollback()
        await wait_for(lambda: any(eid == 2 and v == 0.77 for _, eid, v, _ in t.pubs))
    finally:
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        await stop_cadence(t, stop, cadence)
    ev2 = [(v, rev) for _, eid, v, rev in t.pubs if eid == 2]
    out = dict(
        case="bridged-held-write",
        selected_before_release=selected_before_release,
        bridged_write_still_waiting=still_waiting,
        ev2_published_before_release=ev2_before_release,
        selected_published_after_arrival_s=round(published_at(t, 1, 0.64) - t_new, 4),
        bridged_writes=[
            (round(s - t_release, 4), round(e - t_release, 4), v) for s, e, v in bridged
        ],
        ev1_values=[v for _, eid, v, _ in t.pubs if eid == 1],
        ev2_values=[v for v, _ in ev2],
        ev2_revs=[rev for _, rev in ev2],
        handed_off=t.p.ns["stats"].get("bridged_handed_off", 0),
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
        reserved_after=sorted(t.boundary.bridges.reserved),
    )
    evidence(out)
    # Event 1's newer quote published while the bridged UPDATE still waited.
    assert out["selected_before_release"] and out["bridged_write_still_waiting"], out
    assert not out["ev2_published_before_release"], out
    # The held write returned only after the release; the newer bridged value
    # was written after it, never beside it.
    (first_start, first_end, first), (second_start, _, second) = bridged[:2]
    assert first == {PEER_OUTCOME: 0.75} and second == {PEER_OUTCOME: 0.77}, out
    assert first_end >= t_release and second_start >= first_end, out
    assert out["ev2_values"][-1] == 0.77, out
    assert out["ev2_revs"] == sorted(set(out["ev2_revs"])), out
    assert out["ev1_values"][-1] == 0.64, out
    assert out["handed_off"] >= 2, out
    assert out["errors"] == 0 and out["price_errors"] == 0, out
    assert out["pending_after"] == [] and out["buffer_after"] == {}, out
    assert out["reserved_after"] == [], out


async def test_a_catalog_handover_waits_for_the_held_bridged_write_and_keeps_its_stamp(
    rig, consumer, monkeypatch,
):
    """#10090 bridged writer at a catalog handover. A handover that starts while
    the bridged UPDATE waits in Postgres fences side writes, waits for that
    write to commit, and hands its owed event-2 stamp to the refresher's debt
    before any map could change; once the handover ends, the cadence stamps
    event 2 from the committed row (no stamp read the uncommitted board, none
    is lost)."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=2000)
    bridged = bridged_rig(t)
    holder, tx, holder_pid = await hold_outcome_row(rig, PEER_OUTCOME)
    stop = asyncio.Event()
    t.accept(PEER_OUTCOME, 0.75)
    cadence = start_cadence(t, stop)
    entered = asyncio.Event()
    debt_at_entry = []

    async def handover():
        async with t.boundary.updating():
            debt_at_entry.extend(sorted(t.r.pending_event_ids()))
            entered.set()

    task = None
    try:
        await wait_for_lock_waiters(rig, 1, holder_pid)
        task = asyncio.create_task(handover())
        await asyncio.sleep(0.3)
        entered_while_held = entered.is_set()
        fenced_while_held = t.boundary.standalone_fenced
        t_release = time.monotonic()
        await tx.rollback()
        await asyncio.wait_for(task, 3.0)
        await wait_for(lambda: any(eid == 2 and v == 0.75 for _, eid, v, _ in t.pubs))
    finally:
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await stop_cadence(t, stop, cadence)
    out = dict(
        case="bridged-catalog-handover",
        entered_while_held=entered_while_held,
        fenced_while_held=fenced_while_held,
        debt_at_entry=debt_at_entry,
        bridged_end_after_release_s=round(bridged[0][1] - t_release, 4),
        ev2_values=[v for _, eid, v, _ in t.pubs if eid == 2],
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
    )
    evidence(out)
    assert not out["entered_while_held"] and out["fenced_while_held"], out
    assert out["bridged_end_after_release_s"] >= 0, out
    # Committed before the maps could change, owed as debt keyed by event.
    assert out["debt_at_entry"] == [2], out
    assert out["ev2_values"] == [0.75], out
    assert out["errors"] == 0 and out["price_errors"] == 0, out
    assert out["pending_after"] == [] and out["buffer_after"] == {}, out


async def test_a_locked_bridged_event_never_rolls_back_a_retried_neighbour(
    rig, consumer, monkeypatch,
):
    """#10090 bridged retry isolation (Root's BRIDGE-RETRY-ISOLATION). Events 2
    and 3 are bridged open legs written together; a second transaction holds
    event 2's futures_outcomes row, so their joint UPDATE times out and both
    are left retry-held. After the cooldown each is its own transaction: event
    3 commits, stamps and is acknowledged from its committed row while event
    2's row is still held, and event 2 recovers once its holder lets go. Packed
    together again, every NOWAIT refusal on 2 rolled 3 back with it."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=2000)
    t.p.ns["open_outcome_ids"].update({PEER_OUTCOME, HELD_SIBLING_OUTCOME})
    t.p.ns["PRICE_CHUNK_LOCK_TIMEOUT_MS"] = 300  # times out inside the hold
    t.p.ns["PRICE_STATEMENT_LOCK_TIMEOUT_MS"] = 300
    attempts: list[tuple] = []
    inner = t.p.ns["write_chunk"]

    async def recorded(chunk, **kwargs):
        attempts.append(tuple(sorted(chunk)))
        return await inner(chunk, **kwargs)

    t.p.ns["write_chunk"] = recorded
    holder, tx, holder_pid = await hold_outcome_row(rig, PEER_OUTCOME)
    stop = asyncio.Event()
    t.accept(PEER_OUTCOME, 0.75)
    t.accept(HELD_SIBLING_OUTCOME, 0.55)
    cadence = start_cadence(t, stop)
    ev3_before_release = ev2_before_release = False
    try:
        await wait_for_lock_waiters(rig, 1, holder_pid)
        with contextlib.suppress(TimeoutError):  # the asserts below say so
            await wait_for(
                lambda: any(eid == 3 for _, eid, _, _ in t.pubs),
                pm.PRICE_FLUSH_SECONDS + 2.0,
            )
        ev3_before_release = any(eid == 3 and v == 0.55 for _, eid, v, _ in t.pubs)
        ev2_before_release = any(eid == 2 for _, eid, _, _ in t.pubs)
        await tx.rollback()
        await wait_for(lambda: any(eid == 2 and v == 0.75 for _, eid, v, _ in t.pubs))
    finally:
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        await stop_cadence(t, stop, cadence)
    out = dict(
        case="bridged-retry-isolation",
        attempts=[list(a) for a in attempts],
        ev3_published_before_release=ev3_before_release,
        ev2_published_before_release=ev2_before_release,
        ev2_values=[v for _, eid, v, _ in t.pubs if eid == 2],
        ev3_values=[v for _, eid, v, _ in t.pubs if eid == 3],
        probes_refused=t.p.ns["stats"].get("price_lock_probes_refused", 0),
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
        reserved_after=sorted(t.boundary.bridges.reserved),
    )
    evidence(out)
    joint = (PEER_OUTCOME, HELD_SIBLING_OUTCOME)
    # The first attempt was the joint one; every retry kept them apart.
    assert attempts[0] == joint, out
    assert joint not in attempts[1:], out
    assert out["ev3_published_before_release"], out
    assert not out["ev2_published_before_release"], out
    assert out["ev3_values"] == [0.55] and out["ev2_values"] == [0.75], out
    # The one joint lock timeout is the only counted price error.
    assert out["price_errors"] == 1 and out["errors"] == 0, out
    assert out["pending_after"] == [] and out["buffer_after"] == {}, out
    assert out["reserved_after"] == [], out


async def test_a_continuously_ticking_bridged_event_publishes_while_it_ticks(
    rig, consumer, monkeypatch,
):
    """#10090 bridged continuous arrivals (Root's CONTINUOUS-BRIDGE-STAMP-
    STARVATION). Event 2's bridged open leg takes a new quote every 20 ms for
    two seconds, so a newer quote is buffered at nearly every flush. Each
    committed cohort's stamp takes its turn before the next bridged write of
    that event, so event 2 is acknowledged from its committed row repeatedly
    WHILE it ticks, revisions advancing, and ends on its last value. Before,
    every stamp was deferred behind the next cohort until the venue went
    quiet."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=2000)
    t.p.ns["open_outcome_ids"].add(PEER_OUTCOME)
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    values = [round(0.30 + 0.004 * i, 3) for i in range(100)]
    try:
        t_first = time.monotonic()
        for value in values:
            t.accept(PEER_OUTCOME, value)
            await asyncio.sleep(0.02)
        t_last = time.monotonic()
        await wait_for(lambda: any(eid == 2 and v == values[-1] for _, eid, v, _ in t.pubs))
    finally:
        await stop_cadence(t, stop, cadence)
    ev2 = [(at, v, rev) for at, eid, v, rev in t.pubs if eid == 2]
    during = [(at, v) for at, v, _ in ev2 if at < t_last]
    out = dict(
        case="bridged-continuous",
        ticking_s=round(t_last - t_first, 3),
        published_while_ticking=len(during),
        first_publication_s=round(ev2[0][0] - t_first, 4) if ev2 else None,
        largest_gap_while_ticking_s=round(max(
            (b - a for a, b in zip(
                [t_first] + [at for at, _ in during], [at for at, _ in during] + [t_last],
            )),
            default=t_last - t_first,
        ), 4),
        bridged_writes=sum(
            1 for _, chunk in t.writes if PEER_OUTCOME in chunk
        ),
        ev2_revs=[rev for _, _, rev in ev2],
        last_value=ev2[-1][1] if ev2 else None,
        errors=t.r.stats["errors"],
        price_errors=t.p.ns["stats"]["errors"],
        pending_after=sorted(t.r.pending_event_ids()),
        buffer_after=dict(t.p.ns["price_buffer"]),
    )
    evidence(out)
    # Acknowledged repeatedly while the quotes kept arriving, from committed
    # rows (the sink reads each back), each a quote that was actually sent.
    assert out["published_while_ticking"] >= 3, out
    assert all(v in values for _, v in during), out
    assert out["ev2_revs"] == sorted(set(out["ev2_revs"])), out
    assert out["last_value"] == values[-1], out
    assert out["errors"] == 0 and out["price_errors"] == 0, out
    assert out["pending_after"] == [] and out["buffer_after"] == {}, out
