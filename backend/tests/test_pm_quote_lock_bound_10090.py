"""A held PM whole chunk rolls back, cools down and leaves healthy chunks eligible."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.tasks.polymarket_ws import (
    PRICE_CHUNK_LOCK_TIMEOUT_MS, _PMPriceWriteResult, _pm_lock_isolated_chunks,
    chunk_price_update_stmt,
)
from app.tasks.kalshi_ws import PRICE_FLUSH_SECONDS
from app.tasks.live_blend_refresh import run_flush_cadence
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, is_lock_timeout, lock_timeout_value
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions, rig
from tests.test_ws_flush_cadence_10090 import _FakeTime


class LockHeld(Exception):
    sqlstate = "55P03"


def writer_rig(clock, *, error=None, database=None, **kwargs):
    r = rig(**({"books": {1: (0.2, 0.8)}} | kwargs))
    r.release.set()
    state = SimpleNamespace(held=True, attempts=[], settings=[], commits=[], pending=set(),
                            forced=[], ranks=[], values={})

    class Session:
        async def execute(self, stmt, params=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                assert params == {"ms": "500ms"}
                state.settings.append(clock.t)
                return SimpleNamespace(rowcount=1)
            kind, values = stmt
            if kind == "rank":
                state.ranks.append(tuple(values))
                return SimpleNamespace(rowcount=len(values))
            chunk, forced = values
            state.forced.append(set(forced))
            state.attempts.append((clock.t, tuple(chunk)))
            if 1 in chunk and state.held:
                # A newer accepted quote survives the whole transaction rollback.
                r.ns["price_buffer"][1] = 0.9
                clock.t += 0.5
                raise error or LockHeld()
            written = {
                oid: value for oid, value in chunk.items()
                if database is None or oid in forced
                or database.get(oid) != round(value, 6)
            }
            state.pending.update(written)
            state.values.update(written)
            rows = [SimpleNamespace(ord=i, id=oid, market_id=oid,
                                    quote_moved=True, last_updated=1)
                    for i, oid in enumerate(written)]
            return SimpleNamespace(all=lambda: rows)

    @asynccontextmanager
    async def session():
        try:
            yield Session()
        except Exception:
            state.pending.clear()
            state.values.clear()
            r.trace.append(("rollback", None))
            raise
        else:
            state.commits.extend(sorted(state.pending))
            if database is not None:
                database.update({oid: round(value, 6) for oid, value in state.values.items()})
            state.pending.clear()
            state.values.clear()
            r.trace.append(("commit", None))

    r.ns.update(
        get_task_session=session, lock_retry_until={},
        _PMPriceWriteResult=_PMPriceWriteResult,
        PRICE_CHUNK_LOCK_TIMEOUT_MS=PRICE_CHUNK_LOCK_TIMEOUT_MS,
        PRICE_FLUSH_SECONDS=PRICE_FLUSH_SECONDS, SET_LOCK_TIMEOUT_SQL=SET_LOCK_TIMEOUT_SQL,
        is_lock_timeout=is_lock_timeout, lock_timeout_value=lock_timeout_value,
        chunk_price_update_stmt=lambda chunk, force_ids: ("price", (chunk, force_ids)),
        rerank_market_fields_stmt=lambda ids: ("rank", ids),
        market_by_outcome={oid: oid for oid in r.ns["price_buffer"]},
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], r.ns)
    return r, state


async def test_failed_whole_chunk_cooldown_preserves_healthy_cadence_and_fences(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    starts = []
    stop = asyncio.Event()
    pending = {10}
    admitted = []
    original_refresher = r.ns["blend_refresher"]

    class Refresher:
        publish_market_changes = original_refresher.publish_market_changes

        def pending_event_ids(self):
            return frozenset(pending)

        async def refresh(self, ids, **kwargs):
            due = (set(ids) | pending) - set(kwargs.get("defer_event_ids", ()))
            admitted.append(due)
            pending.difference_update(due)
            await original_refresher.refresh(ids, **kwargs)

        async def refresh_pending(self, **kwargs):
            await self.refresh(set(), **kwargs)

    r.ns["blend_refresher"] = Refresher()

    async def flush(started):
        starts.append(started)
        if len(starts) > 1:
            r.ns["price_buffer"][900] = 0.8
        if len(starts) == 4:
            state.held = False
        result = await r.ns["flush_prices"](flush_started=started)
        assert result is True, "a lock-held cohort must not invoke global failure sleep"
        if len(starts) < 4:
            assert r.ns["price_buffer"] == {1: 0.9, 2: 0.4}
            assert r.ns["lock_retry_until"] == {1: 1003.5, 2: 1003.5}
            assert 1 not in r.ns["successful_price_write_at"], "rollback cannot acknowledge first observation"
            assert r.books == {1: (0.2, 0.8)}, "withdrawal must not bypass the hold"
            assert ("refresh", [10]) not in r.trace
            assert pending == {10} and all(10 not in ids for ids in admitted)
            assert state.commits == [900] * len(starts)
        else:
            stop.set()
        return result

    await run_flush_cadence(flush, 1, stop, failed_retry_interval_s=2)
    assert starts == [1001, 1002, 1003, 1004]
    assert [t for t, ids in state.attempts if 1 in ids] == [1001, 1004]
    # The fresh unrelated quote writes ahead of the retried cohort.
    assert state.commits == [900, 900, 900, 900, 1, 2]
    assert not r.ns["price_buffer"] and not r.ns["lock_retry_until"]
    assert not pending
    assert ("withdraw", [1]) in r.trace and ("refresh", [10]) in r.trace
    assert r.ns["stats"]["errors"] == 1 and r.ns["stats"]["requeued"] == 2


async def test_final_drain_ignores_hold_and_does_not_set_periodic_lock_budget(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert r.ns["lock_retry_until"]
    state.held = False
    assert (await r.ns["write_chunk"]({1: 0.9, 2: 0.4}, final=True)).written_ids == (1, 2)
    assert len(state.settings) == 1  # no SET in the final transaction
    assert state.commits == [1, 2] and not r.ns["lock_retry_until"]


async def test_non_lock_error_retains_existing_global_failure_result(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock, error=RuntimeError("connection failed"))
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is False
    assert not r.ns["lock_retry_until"] and not state.commits
    assert not r.ns["successful_price_write_at"]
    assert r.ns["price_buffer"][1] == 0.9 and 2 in r.ns["price_buffer"]


async def test_mixed_lock_failure_retries_events_separately_and_keeps_full_fences(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(
        clock,
        batch={1: 0.6, 2: 0.4, 900: 0.7, 901: 0.3, 3: 0.8, 902: 0.8},
        mapping={1: 10, 2: 10, 3: 10, 900: 90, 901: 90, 902: 90},
        books={1: (0.2, 0.8), 900: (0.1, 0.9)},
    )
    r.ns["FLUSH_CHUNK_ROWS"] = 4
    r.ns["open_outcome_ids"] = set()
    r.ns["open_complement_of"].update({900: 901, 901: 900})
    pending = {10, 90}
    admitted = []
    original = r.ns["blend_refresher"]

    class Refresher:
        publish_market_changes = original.publish_market_changes

        def pending_event_ids(self):
            return frozenset(pending)

        async def refresh(self, ids, **kwargs):
            due = (set(ids) | pending) - set(kwargs.get("defer_event_ids", ()))
            admitted.append(due)
            pending.difference_update(due)
            await original.refresh(ids, **kwargs)

        async def refresh_pending(self, **kwargs):
            await self.refresh(set(), **kwargs)

    r.ns["blend_refresher"] = Refresher()
    assert await r.ns["flush_prices"](flush_started=1000)
    # First attempt keeps ordinary batching: two unrelated event pairs share
    # one rollback. The later successful chunks must not release either stamp.
    assert state.attempts == [(1000, (1, 2, 900, 901)), (1000.5, (3, 902))]
    assert state.commits == [3, 902]
    assert pending == {10, 90} and all(not due for due in admitted)
    assert r.ns["lock_retry_events"] == {10, 90}
    assert r.books.keys() == {1, 900}

    clock.t = 1001
    assert await r.ns["flush_prices"](flush_started=1001)
    assert len(state.attempts) == 2, "cooldown still protects the original failed rows"

    clock.t = 1003
    # A new question for the held event is part of this admitted cohort too.
    r.ns["price_buffer"][3] = 0.85
    assert await r.ns["flush_prices"](flush_started=1003)
    assert state.attempts[-2:] == [(1003, (1, 2, 3)), (1003.5, (900, 901))]
    assert state.commits == [3, 902, 900, 901]
    assert r.ns["price_buffer"] == {1: 0.9, 2: 0.4, 3: 0.85}
    assert r.ns["lock_retry_events"] == {10}
    assert set(r.ns["lock_retry_until"]) == {1, 2, 3}
    assert r.books.keys() == {1} and pending == {10}
    assert ("refresh", [90]) in r.trace and ("refresh", [10]) not in r.trace
    assert ("withdraw", [900]) in r.trace and ("withdraw", [1]) not in r.trace

    clock.t = 1004
    r.ns["price_buffer"][900] = 0.75
    assert await r.ns["flush_prices"](flush_started=1004)
    assert state.attempts[-1] == (1004, (900,)), "healthy event keeps ordinary eligibility"
    state.held = False
    clock.t = 1006
    assert await r.ns["flush_prices"](flush_started=1006)
    assert not r.ns["price_buffer"] and not r.ns["lock_retry_until"]
    assert not r.ns["lock_retry_events"] and not pending and not r.books


def test_isolation_preserves_admitted_questions_complements_and_ordinary_remainders():
    chunks = [[700, 1, 2, 900], [3, 901, 701, 702], [902]]
    mapping = {1: 10, 2: 10, 3: 10, 900: 90, 901: 90, 902: 90}
    markets = {1: 100, 2: 200, 3: 100, 900: 900, 901: 901, 902: 902}
    pairs = {1: 2, 2: 1}
    assert _pm_lock_isolated_chunks(chunks, set(), mapping, markets, pairs, 2) is chunks
    planned = _pm_lock_isolated_chunks(chunks, {10, 90}, mapping, markets, pairs, 2)
    # Unrelated remainders write before the retried cohorts' lock waits.
    assert planned == [[700], [701, 702], [1, 2, 3], [900, 901], [902]]
    assert sorted(oid for chunk in planned for oid in chunk) == sorted(
        oid for chunk in chunks for oid in chunk
    ), "isolation cannot admit capped-out or newer buffered rows"


def test_retried_cohort_keeps_order_ahead_of_a_remainder_sharing_its_event():
    # Market 100's legs span events 10 (retried) and 20; 5 is event 20 alone.
    chunks = [[1, 2, 5, 6]]
    mapping = {1: 10, 2: 20, 5: 20, 6: 30}
    markets = {1: 100, 2: 100, 5: 500, 6: 600}
    planned = _pm_lock_isolated_chunks(chunks, {10}, mapping, markets, {}, 4)
    assert planned == [[1, 2], [5, 6]], "event 20 keeps its write order"
    planned = _pm_lock_isolated_chunks(
        [[1, 2, 6], [5]], {10}, mapping, markets, {}, 4,
    )
    assert planned == [[6], [1, 2], [5]], (
        "a disjoint remainder moves ahead; the overlapping one still waits"
    )


async def test_fresh_unrelated_event_writes_before_a_still_held_retried_cohort(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(
        clock, batch={1: 0.6, 2: 0.4}, mapping={1: 10, 2: 10, 5: 20}, books={},
    )
    r.ns["FLUSH_CHUNK_ROWS"] = 4
    r.ns["open_outcome_ids"] = set()
    assert await r.ns["flush_prices"](flush_started=1000)
    assert state.attempts == [(1000, (1, 2))] and not state.commits
    assert r.ns["lock_retry_events"] == {10}

    clock.t = 1003
    r.ns["price_buffer"][5] = 0.7
    r.ns["market_by_outcome"][5] = 5
    r.trace.clear()
    assert await r.ns["flush_prices"](flush_started=1003)
    # Event 20 commits at the flush start, not after event 10's 500 ms wait,
    # and its stamp is not held behind that retry.
    assert state.attempts == [(1000, (1, 2)), (1003, (5,)), (1003, (1, 2))]
    assert state.commits == [5]
    assert r.trace.index(("refresh", [20])) < r.trace.index(("rollback", None))
    # The held cohort was still attempted this flush and keeps its debt.
    assert r.ns["price_buffer"] == {1: 0.9, 2: 0.4}
    assert r.ns["lock_retry_events"] == {10}
    assert set(r.ns["lock_retry_until"]) == {1, 2}
    assert ("refresh", [10]) not in r.trace


def test_repeat_predicate_uses_database_precision_before_row_lock():
    from sqlalchemy.dialects import postgresql

    statement = chunk_price_update_stmt({1: 0.0512345678, 2: 0.4}, force_ids={2})
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "given.force_write OR futures_outcomes.current_probability IS DISTINCT FROM CAST(given.price AS NUMERIC(7, 6))" in sql
    assert sql.index("IS DISTINCT FROM") < sql.index("FOR UPDATE")
    assert statement.compile().params["chunk_force"] == [False, True]


async def test_identical_ack_skips_fresh_receipt_but_database_change_and_liveness_write(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    database = {1: 0.6, 2: 0.4, 900: 0.1}
    r, state = writer_rig(clock, database=database, books={})
    state.held = False
    original_batch = dict(database)
    assert await r.ns["flush_prices"](flush_started=1000)
    assert state.commits == [1, 2, 900], "first successful observation is forced"
    assert r.ns["successful_price_write_at"] == {1: 1000, 2: 1000, 900: 1000}

    for t in (1001, 1029.9):
        clock.t = t
        r.ns["price_buffer"].update(original_batch)
        r.trace.clear()
        r.marks.clear()
        assert await r.ns["flush_prices"](flush_started=t)
        assert not r.ns["price_buffer"] and not r.marks
        assert not any(kind == "refresh" for kind, _ in r.trace)
        assert state.commits == [1, 2, 900] and len(state.ranks) == 2
        assert r.ns["successful_price_write_at"][1] == 1000

    clock.t = 1030
    r.ns["price_buffer"].update(original_batch)
    assert await r.ns["flush_prices"](flush_started=1030)
    assert state.commits == [1, 2, 900] * 2, "real liveness write is forced at 30 seconds"
    assert r.ns["successful_price_write_at"][1] == 1030

    clock.t = 1031
    database[900] = 0.2  # An external writer changed the stored value.
    r.ns["price_buffer"].update(original_batch)
    assert await r.ns["flush_prices"](flush_started=1031)
    assert state.commits[-1] == 900 and database[900] == 0.1
    assert state.forced[-1] == set(), "repair comes from the DB predicate, not a quote cache"
    assert r.ns["successful_price_write_at"][900] == 1031

    clock.t = 1032
    r.ns["price_buffer"].update({1: 0.7, 2: 0.4})
    assert await r.ns["flush_prices"](flush_started=1032)
    assert state.commits[-1] == 1 and database[1] == 0.7
    assert state.forced[-1] == set(), "a changed price is immediate inside the liveness window"

    # An unchanged acknowledgement cannot discard an input arriving while its
    # transaction commits, even though that statement returned no price row.
    factory = r.ns["get_task_session"]

    @asynccontextmanager
    async def newer_input():
        async with factory() as session:
            yield session
            r.ns["price_buffer"][1] = 0.8

    r.ns["get_task_session"] = newer_input
    clock.t = 1033
    r.ns["price_buffer"][1] = 0.7
    result = await r.ns["write_chunk"]({1: 0.7})
    assert result.written_ids == () and r.ns["price_buffer"][1] == 0.8
    assert r.ns["successful_price_write_at"][1] == 1032


async def test_later_admitted_pair_adopts_latest_values_marks_and_new_withdrawal(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(
        clock,
        batch={900: 0.1, 901: 0.9, 1: 0.6, 2: 0.4},
        mapping={900: 90, 901: 90, 1: 10, 2: 10, 940: 94},
        books={},
    )
    state.held = False
    r.ns["open_outcome_ids"] = set()
    r.ns["open_complement_of"].update({900: 901, 901: 900})
    first_started, first_release = asyncio.Event(), asyncio.Event()
    observed = []
    factory = r.ns["get_task_session"]

    class DelayedSession:
        def __init__(self, session):
            self.session = session

        async def execute(self, stmt, params=None):
            if isinstance(stmt, tuple) and stmt[0] == "price":
                chunk, _forced = stmt[1]
                observed.append(dict(chunk))
                if 900 in chunk:
                    first_started.set()
                    await first_release.wait()
                elif 1 in chunk:
                    # Inputs after adoption still survive the successful write.
                    r.ns["price_buffer"].update({1: 0.85, 2: 0.15})
                    r.ns["input_marks"].update({1: "after1", 2: "after2"})
            return await self.session.execute(stmt, params)

    @asynccontextmanager
    async def delayed_session():
        async with factory() as session:
            yield DelayedSession(session)

    r.ns["get_task_session"] = delayed_session
    task = asyncio.create_task(r.ns["flush_prices"](flush_started=1000))
    try:
        await asyncio.wait_for(first_started.wait(), 1)
        async with r.ns["buffer_lock"]:
            r.ns["price_buffer"].update({1: 0.8, 2: 0.2, 940: 0.7})
            r.ns["input_marks"].update({1: "latest1", 2: "latest2", 940: "new-id"})
            r.books[1] = (0.1, 0.9)
        first_release.set()
        assert await task
    finally:
        first_release.set()
        await task
    assert observed == [{900: 0.1, 901: 0.9}, {1: 0.8, 2: 0.2}]
    assert r.marks == [900, 901, "latest1", "latest2"]
    assert r.ns["price_buffer"] == {1: 0.85, 2: 0.15, 940: 0.7}
    assert r.trace.index(("withdraw", [1])) < r.trace.index(("refresh", [10]))
    assert state.commits == [900, 901, 1, 2] and not r.books
