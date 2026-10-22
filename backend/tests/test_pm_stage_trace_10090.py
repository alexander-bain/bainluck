"""#10090: the optional PM stage trace follows the EXACT selected input.

The actual game flush (`_flush_prices`), the actual chunk writer (`write_chunk`)
and a real `LiveBlendRefresher` run on the existing fakes. One worker clock drives
both the refresher (`_mono`) and the trace, so the durations are deterministic.
A deliberately slow price statement and a deliberately slow stamp must read
differently, both joined to the same selected `input_seq`. Disabled, expired,
budget-exhausted and logger-failing traces must leave delivery unchanged.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import live_blend_refresh as blend
from app.tasks.polymarket_ws import (
    ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL, _PMPriceWriteResult,
)
from app.utils.pm_stage_trace import PMStageTrace
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions
from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig
from tests.test_single_event_commit_10090 import rig as stamp_rig, settle_until

STORED = datetime(2026, 10, 14, 20, 53, 13, 500000, tzinfo=timezone.utc)
WALL = 1_000_000.0


def trace_rig(monkeypatch, *, slow_write=0.0, slow_stamp=0.0, block=False,
              env=None, emit=None, wall=None, during_write=None):
    clock = [500.0]
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])
    monkeypatch.setattr(blend, "_wall", lambda: WALL)
    x = stamp_rig(monkeypatch, count=2, block=block, blocked=(1,))
    reading = [0.9]
    # Event 1's reading names outcome 1's committed observation, as the real
    # reading's contributing outcomes do; event 2 has none.
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, home, away: SimpleNamespace(
            home_probability=reading[0], away_probability=None, draw_probability=None,
            eligibility=None,
            contributing_outcomes=(SimpleNamespace(id=1, last_updated=STORED),),
        ),
    )
    session_cls = x.Session
    original = session_cls.execute

    async def stamp_execute(self, statement, *args, **kwargs):
        from sqlalchemy.sql.dml import Update

        if isinstance(statement, Update) and slow_stamp:
            clock[0] += slow_stamp  # the stamp's own statement is slow
            await asyncio.sleep(0)
        return await original(self, statement, *args, **kwargs)

    monkeypatch.setattr(session_cls, "execute", stamp_execute)

    p = pm_rig(batch={1: 0.6, 2: 0.4}, mapping={1: 1, 2: 1}, books={})
    p.release.set()

    class PriceSession:
        info: dict = {}

        async def execute(self, statement, params=None):
            if statement is ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL:
                # The recording transaction starts with the default timeout;
                # let the real writer arm it and restore that prior setting.
                return SimpleNamespace(scalar_one=lambda: "0")
            if isinstance(statement, tuple) and statement[0] == "prices":
                if slow_write:
                    clock[0] += slow_write  # e.g. a row-lock wait inside the UPDATE
                    await asyncio.sleep(0)
                if during_write is not None:
                    during_write(statement[1])  # callbacks landing mid-statement
                return SimpleNamespace(all=lambda: [
                    SimpleNamespace(id=oid, ord=i, market_id=10, quote_moved=True,
                                    last_updated=STORED)
                    for i, oid in enumerate(statement[1])
                ])
            return SimpleNamespace(rowcount=1)

    @asynccontextmanager
    async def price_session():
        yield PriceSession()

    receipts = blend.TailReceipts("polymarket")
    x.r.receipts = receipts
    lines = []
    trace = PMStageTrace.from_env(
        env if env is not None else {
            "WS_PM_TRACE_EVENT": "1",
            "WS_PM_TRACE_OUTCOMES": "1",
            "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300),
            "WS_PM_TRACE_MAX_LINES": "256",
        },
        run="t", event_of=p.ns["event_id_by_outcome"],
        wall=wall or (lambda: WALL), mono=lambda: clock[0],
        # As production logs it: one JSON object per line.
        emit=emit or (lambda record: lines.append(json.loads(json.dumps(record)))),
    )
    receipts.exact_trace = trace
    p.ns.update(
        get_task_session=price_session,
        blend_refresher=x.r,
        tail_receipts=receipts,
        logger=blend.logger,
        _PMPriceWriteResult=_PMPriceWriteResult,
        chunk_price_update_stmt=lambda chunk, **kw: ("prices", chunk),
        input_marks={},
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], p.ns)

    def accept(oid, value, seq):
        mark = blend.InputMark(
            seq=seq, event_id=p.ns["event_id_by_outcome"][oid], outcome_id=oid,
            probability=value, kind="trade", recv_wall=WALL, recv_mono=clock[0],
            venue_ts_ms=1760475193000, event_ordinal=seq,
        )
        p.ns["price_buffer"][oid] = value
        p.ns["input_marks"][oid] = mark
        if trace is not None:
            trace.input_accepted(mark)
        return mark

    for seq, (oid, value) in enumerate(sorted(p.ns["price_buffer"].items()), 1):
        accept(oid, value, seq)
    return SimpleNamespace(
        p=p, x=x, clock=clock, trace=trace, lines=lines, accept=accept, reading=reading,
    )


async def flush(t, started=None):
    ok = await t.p.ns["flush_prices"](
        flush_started=t.clock[0] if started is None else started
    )
    await t.p.ns["catalog_boundary"].join_stamps()
    return ok


def stage(lines, name):
    return [line for line in lines if line["stage"] == name]


@pytest.mark.asyncio
@pytest.mark.parametrize("slow", ["write", "stamp"])
async def test_slow_write_and_slow_stamp_are_distinguishable_on_the_exact_mark(
    monkeypatch, slow
):
    t = trace_rig(
        monkeypatch,
        slow_write=1.0 if slow == "write" else 0.0,
        slow_stamp=1.0 if slow == "stamp" else 0.0,
    )
    assert await flush(t, started=500.0)
    assert t.x.published == [1]
    (accepted,) = stage(t.lines, "ACCEPTED")
    seq = accepted["input_seq"]
    assert accepted["outcome"] == 1 and accepted["probability"] == 0.6
    assert accepted["kind"] == "trade" and accepted["venue_ts_ms"] == 1760475193000
    assert accepted["accept_clock"].endswith("NOT_WIRE_INGRESS")

    (chunk,) = stage(t.lines, "CHUNK")
    assert chunk["result"] == "COMMITTED" and chunk["written"] == [[1, seq, 0.6]]
    assert chunk["flush_started_mono"] == 500.0 and chunk["size"] == 2

    (committed,) = stage(t.lines, "PRICE_COMMITTED")
    assert committed["input_seq"] == seq and committed["carries_changed_seq"] == seq
    assert committed["superseded_unwritten"] == committed["committed_unstamped"] == []
    assert committed["stored_epoch"] == STORED.timestamp()
    assert committed["stored_clock"] == "DB_TRANSACTION_NOW_NOT_COMMIT"

    (event,) = stage(t.lines, "EVENT_COMMITTED")
    assert event["input_seq"] == seq and event["revision"] == 42
    assert event["linkage"] == "EXACT_OUTCOME_OBSERVATION_BASIS"

    (attempt,) = stage(t.lines, "ATTEMPT")
    assert attempt["kind"] == "stamped" and attempt["revision"] == 42
    assert attempt["attempt"] == event["attempt"] and attempt["joined"] is True
    assert attempt["released_mono"] >= attempt["committed_mono"]
    stamp_s = attempt["committed_mono"] - attempt["start_mono"]
    if slow == "write":
        assert chunk["statement_s"] == 1.0 and stamp_s == 0.0
    else:
        assert chunk["statement_s"] == 0.0 and stamp_s == 1.0
    # One worker clock: the write's commit precedes the attempt's start.
    assert committed["commit_mono"] <= attempt["start_mono"]
    # The chain closed: nothing pending, a later unchanged flush writes nothing.
    assert not t.trace.waiting
    before = len(t.lines)
    t.accept(1, 0.6, 9)  # a repeat at the same price spends no line
    assert len(t.lines) == before
    # A sibling outcome's new price restamps the event on the SAME stored
    # observation of outcome 1: the joined mark is not re-emitted, and with no
    # chain open the flush, admission and attempt spend no line either.
    t.reading[0] = 0.85
    t.accept(2, 0.45, 10)
    assert await flush(t, started=502.0)
    assert t.x.published == [1, 1]
    assert len(t.lines) == before


@pytest.mark.asyncio
async def test_fence_names_the_held_attempt_and_the_next_flush_carries_the_mark(monkeypatch):
    t = trace_rig(monkeypatch, block=True)
    first = asyncio.create_task(t.p.ns["flush_prices"](flush_started=500.0))
    try:
        await settle_until(lambda: any(s.event_ids == [1] for s in t.x.sessions))
        await asyncio.wait_for(first, 2)
        held_attempt = t.trace.attempt["attempt"]
        newer = t.accept(1, 0.55, 5)
        assert await asyncio.wait_for(
            t.p.ns["flush_prices"](flush_started=500.25), 2
        )
        (fenced,) = stage(t.lines, "FENCED")
        assert fenced["held_attempt"] == held_attempt
        assert fenced["held_attempt_start_mono"] == 500.0
        fenced_chunk = [c for c in stage(t.lines, "CHUNK") if c["result"] == "FENCED"]
        assert fenced_chunk and fenced_chunk[0]["fenced_by"] == held_attempt
        assert 1 in t.p.ns["price_buffer"], "the fenced price stays buffered"
    finally:
        t.x.release.set()
        await asyncio.gather(first, return_exceptions=True)
        await t.p.ns["catalog_boundary"].join_stamps()
    released = [a for a in stage(t.lines, "ATTEMPT") if a["attempt"] == held_attempt]
    assert released and released[0]["fenced_ours"] is True
    t.reading[0] = 0.85  # the newer price moves the blend
    assert await flush(t, started=500.5)
    carried = [e for e in stage(t.lines, "EVENT_COMMITTED") if e["input_seq"] == newer.seq]
    assert carried, "the first flush after release writes and stamps the exact mark"
    assert [c["input_seq"] for c in stage(t.lines, "PRICE_COMMITTED")][-1] == newer.seq


async def outcome(t):
    assert await flush(t, started=500.0)
    return (
        list(t.x.published), sorted(t.p.ns["price_buffer"]), t.x.r.stats["errors"],
        t.x.r.stats["stamped"], sorted(t.x.r.pending_event_ids()),
    )


@pytest.mark.asyncio
async def test_disabled_expired_budget_and_logger_failure_leave_delivery_unchanged(
    monkeypatch,
):
    baseline = await outcome(trace_rig(monkeypatch, env={}))

    off = trace_rig(monkeypatch, env={})
    assert off.trace is None
    assert await outcome(off) == baseline

    def broken(record):
        raise RuntimeError("logger down")

    assert await outcome(trace_rig(monkeypatch, emit=broken)) == baseline

    budget = trace_rig(monkeypatch, env={
        "WS_PM_TRACE_EVENT": "1", "WS_PM_TRACE_OUTCOMES": "1",
        "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300), "WS_PM_TRACE_MAX_LINES": "4",
    })
    assert await outcome(budget) == baseline
    assert budget.lines[-1] == {**budget.lines[-1], "stage": "STOP", "reason": "BUDGET_STOP"}
    assert len(budget.lines) <= 4 and not budget.trace.waiting

    now = [WALL]
    expiring = trace_rig(monkeypatch, wall=lambda: now[0])
    now[0] = WALL + 301
    assert await outcome(expiring) == baseline
    assert [line["reason"] for line in stage(expiring.lines, "STOP")] == ["EXPIRED"]
    assert not expiring.trace.waiting and not expiring.trace.commits


def test_enablement_is_bounded_and_mapping_is_explicit():
    def make(**env):
        base = {
            "WS_PM_TRACE_EVENT": "7", "WS_PM_TRACE_OUTCOMES": "70",
            "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300),
        }
        base.update(env)
        lines = []
        trace = PMStageTrace.from_env(
            base, run="r", event_of={70: 7, 71: 7, 80: 8},
            wall=lambda: WALL, mono=lambda: 1.0, emit=lines.append,
        )
        return trace, lines

    assert PMStageTrace.from_env({}, run="r", event_of={}) is None
    assert make(WS_PM_TRACE_OUTCOMES="70,71,72,73,74")[0] is None  # >4
    assert make(WS_PM_TRACE_EXPIRES_AT=str(WALL + 601))[0] is None
    assert make(WS_PM_TRACE_EXPIRES_AT=str(WALL - 1))[0] is None
    assert make(WS_PM_TRACE_MAX_LINES="257")[0] is None
    assert make(WS_PM_TRACE_EVENT="7; DROP")[0] is None
    trace, lines = make(WS_PM_TRACE_OUTCOMES="70,80,99")
    assert lines[0]["mapping"] == {"70": "MAPPED", "80": "OTHER_EVENT", "99": "UNMAPPED"}
    assert trace.targets == frozenset({70})
    trace, lines = make(WS_PM_TRACE_OUTCOMES="80")
    assert [line["stage"] for line in lines] == ["START", "STOP"]
    assert lines[1]["reason"] == "NO_MAPPED_OUTCOME" and not trace.active()
    # The shared refresher finds hooks by NAME on whichever trace the socket
    # attached. None of these may exist on the Kalshi trace (its `admission`
    # has another signature), or the Kalshi path would call into it.
    from app.utils.kalshi_exact_trace import ExactKalshiTrace

    for name in ("stage_admission", "attempt_start", "attempt_session",
                 "attempt_committed", "attempt_released", "input_accepted",
                 "flush_begin", "chunk_begin", "chunk_note", "fence",
                 "chunk_write", "write_stage", "chunk_end"):
        assert not hasattr(ExactKalshiTrace, name), name
    # Every entry point swallows its own failure.
    trace, _ = make()
    for hook in (trace.input_accepted, trace.flush_begin, trace.chunk_begin,
                 trace.chunk_write, trace.write_stage, trace.chunk_end,
                 trace.stage_admission, trace.attempt_start, trace.attempt_released,
                 trace.stamp, trace.fence):
        assert hook(*([object()] * hook.__wrapped__.__code__.co_argcount)[1:]) is None


def test_pending_overflow_stops_rather_than_dropping_identity():
    lines = []
    trace = PMStageTrace.from_env(
        {"WS_PM_TRACE_EVENT": "1", "WS_PM_TRACE_OUTCOMES": "1",
         "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300), "WS_PM_TRACE_MAX_LINES": "256"},
        run="r", event_of={1: 1}, wall=lambda: WALL, mono=lambda: 1.0,
        emit=lines.append,
    )
    for seq in range(1, 80):
        trace.input_accepted(blend.InputMark(
            seq=seq, event_id=1, outcome_id=1, probability=seq / 100, kind="price",
            recv_wall=WALL, recv_mono=1.0, venue_ts_ms=None, event_ordinal=seq,
        ))
    assert lines[-1]["stage"] == "STOP" and lines[-1]["reason"] == "PENDING_OVERFLOW"
    assert not trace.active() and not trace.waiting


@pytest.mark.asyncio
async def test_a_repeat_burst_during_the_write_keeps_the_written_identity(monkeypatch):
    # Root 21:37Z, its exact shape: the flush snapshot pins an OLDER mark; a new
    # change arrives before outcome 1's chunk adopts it; 70 identical callbacks
    # during that chunk's awaited UPDATE age the adopted mark out of `accepted`.
    box = {"changed": None}

    def callbacks(chunk):
        t = box["t"]
        if 2 in chunk and box["changed"] is None:
            box["changed"] = t.accept(1, 0.55, 6)  # lands after the snapshot
        if 1 in chunk:
            for seq in range(100, 170):
                t.accept(1, 0.55, seq)

    t = box["t"] = trace_rig(monkeypatch, during_write=callbacks)
    t.p.ns["FLUSH_CHUNK_ROWS"] = 1
    t.p.ns["open_complement_of"].clear()  # two independent legs, two chunks
    buffer = t.p.ns["price_buffer"]
    buffer[1] = buffer.pop(1)  # outcome 2's chunk writes first
    assert await flush(t, started=500.0)
    written = box["changed"]
    assert len(t.trace.accepted) == 64 and written.seq not in t.trace.accepted
    (chunk,) = stage(t.lines, "CHUNK")
    assert chunk["snapshot"] == [[1, 1, 0.6]] and chunk["written"] == [[1, 6, 0.55]]
    (committed,) = stage(t.lines, "PRICE_COMMITTED")
    assert committed["input_seq"] == written.seq and committed["probability"] == 0.55
    assert committed["carries_changed_seq"] == written.seq
    assert committed["superseded_unwritten"] == [1]  # the snapshot's, never written
    (event,) = stage(t.lines, "EVENT_COMMITTED")
    assert event["input_seq"] == written.seq
    assert not stage(t.lines, "PRICE_COMMITTED_IDENTITY_UNAVAILABLE")


def _unit_trace():
    lines = []
    trace = PMStageTrace.from_env(
        {"WS_PM_TRACE_EVENT": "1", "WS_PM_TRACE_OUTCOMES": "7",
         "WS_PM_TRACE_EXPIRES_AT": str(WALL + 300), "WS_PM_TRACE_MAX_LINES": "256"},
        run="r", event_of={7: 1}, wall=lambda: WALL, mono=lambda: 1.0,
        emit=lines.append,
    )

    def mark(seq, value):
        m = blend.InputMark(
            seq=seq, event_id=1, outcome_id=7, probability=value, kind="price",
            recv_wall=WALL, recv_mono=1.0, venue_ts_ms=None, event_ordinal=seq,
        )
        trace.input_accepted(m)
        return m

    def write(m, chunk=None):
        chunk = chunk if chunk is not None else {7: m.probability}
        trace.flush_begin(1.0, False, {7: m} if m is not None else {}, chunk)
        token = trace.chunk_begin(0, [7])
        trace.chunk_write(token, chunk, {7: m} if m is not None else {})
        trace.write_stage(chunk, "COMMITTED", rows=[SimpleNamespace(id=7, last_updated=STORED)])
        trace.chunk_end(token, True)

    return trace, lines, mark, write


def test_lineage_separates_the_exact_commit_from_superseded_and_unstamped_seqs():
    trace, lines, mark, write = _unit_trace()
    first = mark(1, 0.40)
    write(first)
    mark(2, 0.45)  # replaced in the buffer before any write took it
    newest = mark(3, 0.50)
    repeat = mark(4, 0.50)  # the flush wrote this repeat of seq 3
    write(repeat)
    committed = stage(lines, "PRICE_COMMITTED")
    assert [c["input_seq"] for c in committed] == [first.seq, repeat.seq]
    assert committed[1]["carries_changed_seq"] == newest.seq
    assert committed[1]["superseded_unwritten"] == [2]
    assert committed[1]["committed_unstamped"] == [first.seq]
    trace.stamp(1, {"7": STORED.timestamp()}, 9, "db-clock")
    (event,) = stage(lines, "EVENT_COMMITTED")
    assert event["input_seq"] == repeat.seq and event["committed_unstamped"] == [1]
    assert not trace.waiting and not trace.written


def test_a_written_mark_with_no_retained_identity_is_reported_not_silent():
    trace, lines, mark, write = _unit_trace()
    mark(1, 0.40)
    write(None, chunk={7: 0.40})  # the flush had no mark for the written row
    (missing,) = stage(lines, "PRICE_COMMITTED_IDENTITY_UNAVAILABLE")
    assert missing["identity_reason"] == "NO_MARK" and missing["input_seq"] == "UNAVAILABLE"
    trace, lines, mark, write = _unit_trace()
    mark(1, 0.40)
    gone = blend.InputMark(  # a mark whose identity the trace never retained
        seq=999, event_id=1, outcome_id=7, probability=0.40, kind="price",
        recv_wall=WALL, recv_mono=1.0, venue_ts_ms=None, event_ordinal=999,
    )
    write(gone)
    (missing,) = stage(lines, "PRICE_COMMITTED_IDENTITY_UNAVAILABLE")
    assert missing["identity_reason"] == "WRITTEN_MARK_NOT_RETAINED"
    assert missing["input_seq"] == 999


@pytest.mark.asyncio
async def test_disabled_refresher_does_no_admission_work_and_reads_iterables_once(
    monkeypatch,
):
    t = trace_rig(monkeypatch, env={})
    assert t.trace is None
    called = []
    original = t.x.r._stage_trace
    monkeypatch.setattr(
        t.x.r, "_stage_trace",
        lambda name, *a, **k: (called.append(name), original(name, *a, **k)),
    )

    class Once:
        reads = 0

        def __iter__(self):
            Once.reads += 1
            return iter([1])

    assert t.x.r.admit_fresh(Once(), flush_started=500.0) == frozenset()
    assert await flush(t, started=500.0)
    assert t.x.published == [1]
    assert "stage_admission" not in called
    assert Once.reads <= 1
