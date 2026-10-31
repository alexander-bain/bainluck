"""A held PM whole chunk rolls back, cools down and leaves healthy chunks eligible."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import asyncpg.exceptions
import pytest
from sqlalchemy.exc import OperationalError

from app.tasks.polymarket_ws import (
    PRICE_CHUNK_LOCK_TIMEOUT_MS, PRICE_ROW_LOCK_REFUSAL_MESSAGE, PRICE_STATEMENT_LOCK_TIMEOUT_MS,
    _PMPriceWriteResult,
    _pm_lock_isolated_chunks, chunk_price_update_stmt, is_price_row_lock_refusal,
)
from app.tasks.kalshi_ws import PRICE_FLUSH_SECONDS
from app.tasks.live_blend_refresh import run_flush_cadence
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, is_lock_timeout, lock_timeout_value
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions, rig
from tests.test_ws_flush_cadence_10090 import _FakeTime


LOCK_TIMEOUT_MESSAGE = "canceling statement due to lock timeout"


class LockHeld(Exception):
    """Shaped like asyncpg's 55P03: the SQLSTATE and server message together."""

    sqlstate = "55P03"

    def __init__(self, message=LOCK_TIMEOUT_MESSAGE):
        super().__init__(message)
        self.message = message


def writer_rig(clock, *, error=None, database=None, **kwargs):
    r = rig(**({"books": {1: (0.2, 0.8)}} | kwargs))
    r.release.set()
    state = SimpleNamespace(held=True, attempts=[], settings=[], commits=[], pending=set(),
                            forced=[], ranks=[], values={}, nowait=[], skip=[], budgets=[],
                            statement_budgets=[], rank_error=None,
                            refusal_delay=0.0, refusal_message=PRICE_ROW_LOCK_REFUSAL_MESSAGE)

    class Session:
        def __init__(self):
            self.info = {}  # no market frames staged by this lock-budget fake

        # #10090: models PostgreSQL row locks, so the writer may SKIP LOCKED.
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        budget_s = None  # no SET: the final drain waits for its locks

        async def execute(self, stmt, params=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                state.settings.append(clock.t)
                state.budgets.append(params["ms"])
                self.budget_s = int(params["ms"].removesuffix("ms")) / 1000
                return SimpleNamespace(rowcount=1)
            kind, values = stmt
            if kind == "rank":
                state.statement_budgets.append(("rank", self.budget_s))
                if state.rank_error is not None:
                    clock.t += self.budget_s
                    raise state.rank_error
                state.ranks.append(tuple(values))
                return SimpleNamespace(rowcount=len(values))
            chunk, forced, nowait, skip_units = values
            state.statement_budgets.append(("price", self.budget_s))
            state.forced.append(set(forced))
            state.nowait.append(nowait)
            state.skip.append(skip_units is not None)
            state.attempts.append((clock.t, tuple(chunk)))
            written = {
                oid: value for oid, value in chunk.items()
                if database is None or oid in forced
                or database.get(oid) != round(value, 6)
            }
            skipped = {}
            if 1 in chunk and state.held:
                # A newer accepted quote survives the whole transaction rollback.
                r.ns["price_buffer"][1] = 0.9
                if skip_units is None or error is not None:
                    # NOWAIT is refused without waiting (its answer may still
                    # arrive late); otherwise the statement's lock budget is spent.
                    clock.t += state.refusal_delay if nowait else self.budget_s
                    raise error or (
                        LockHeld(state.refusal_message) if nowait else LockHeld()
                    )
                # #10090 SKIP LOCKED, as `chunk_price_update_stmt` does it:
                # row 1's unit (its event, else its market) and its market are held back,
                # returned as skipped; every other unit writes, no wait.
                def unit(oid):
                    event = skip_units.get(oid)
                    return ("event", event) if event is not None else (
                        "market", r.ns["market_by_outcome"].get(oid, oid))
                market = r.ns["market_by_outcome"].get
                skipped = {oid: v for oid, v in written.items()
                           if unit(oid) == unit(1) or market(oid, oid) == market(1, 1)}
                written = {oid: v for oid, v in written.items() if oid not in skipped}
            state.pending.update(written)
            state.values.update(written)
            rows = [SimpleNamespace(ord=i, id=oid, market_id=oid,
                                    quote_moved=True, last_updated=1)
                    for i, oid in enumerate(written)]
            rows += [SimpleNamespace(ord=len(rows) + i, id=oid, market_id=oid, skipped=True)
                     for i, oid in enumerate(skipped)]
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
        PRICE_STATEMENT_LOCK_TIMEOUT_MS=PRICE_STATEMENT_LOCK_TIMEOUT_MS,
        PRICE_FLUSH_SECONDS=PRICE_FLUSH_SECONDS, SET_LOCK_TIMEOUT_SQL=SET_LOCK_TIMEOUT_SQL,
        is_lock_timeout=is_lock_timeout, lock_timeout_value=lock_timeout_value,
        is_price_row_lock_refusal=is_price_row_lock_refusal,
        chunk_price_update_execution=lambda chunk, force_ids, nowait=False, skip_units=None: (
            ("price", (chunk, force_ids, nowait, skip_units)), {}
        ),
        pm_rerank_market_fields_execution=lambda ids: (("rank", ids), {}),
        rerank_market_fields_stmt=lambda ids: ("rank", ids),  # withdrawals retain their builder
        market_by_outcome={oid: oid for oid in r.ns["price_buffer"]},
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], r.ns)
    return r, state


async def test_a_lock_held_whole_chunk_is_probed_each_flush_preserving_cadence_and_fences(
    monkeypatch,
):
    # #10090 fast retry: the price UPDATE waits PRICE_STATEMENT_LOCK_TIMEOUT_MS,
    # and its lock timeout arms no two-second cooldown. The rows stay
    # known-held, so every later flush probes them NOWAIT (no wait spent) and
    # the first after the holder lets go writes them.
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
            assert r.ns["lock_retry_until"] == dict.fromkeys((1, 2), 1001 + 0.05)
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
    assert [t for t, ids in state.attempts if 1 in ids] == [1001, 1002, 1003, 1004]
    assert [n for n, ids in zip(state.nowait, state.attempts) if 1 in ids[1]] == [
        False, True, True, True,
    ]
    assert state.budgets[0] == f"{PRICE_STATEMENT_LOCK_TIMEOUT_MS}ms"
    # The fresh unrelated quote writes ahead of the retried cohort.
    assert state.commits == [900, 900, 900, 900, 1, 2]
    assert not r.ns["price_buffer"] and not r.ns["lock_retry_until"]
    assert not pending
    assert ("withdraw", [1]) in r.trace and ("refresh", [10]) in r.trace
    assert r.ns["stats"]["errors"] == 1 and r.ns["stats"]["requeued"] == 2
    assert r.ns["stats"]["price_lock_probes_refused"] == 2


async def test_final_drain_ignores_hold_and_does_not_set_periodic_lock_budget(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert r.ns["lock_retry_until"]
    state.held = False
    assert (await r.ns["write_chunk"]({1: 0.9, 2: 0.4}, final=True)).written_ids == (1, 2)
    assert len(state.settings) == 1  # no SET in the final transaction
    assert state.commits == [1, 2] and not r.ns["lock_retry_until"]
    assert state.nowait == [False, False], "the final drain still waits for its locks"


async def test_the_short_budget_covers_only_the_price_update_and_a_rerank_lock_keeps_its_cooldown(
    monkeypatch,
):
    # #10090 fast retry: only the price-row UPDATE runs under the short
    # budget; rerank is restored to the chunk budget in the same transaction,
    # and a lock timeout there (outside the price statement) keeps the
    # existing two-second cooldown and error accounting.
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    state.held = False
    short = PRICE_STATEMENT_LOCK_TIMEOUT_MS / 1000
    chunk_budget = PRICE_CHUNK_LOCK_TIMEOUT_MS / 1000
    assert short < chunk_budget
    assert (await r.ns["write_chunk"]({1: 0.6, 2: 0.4})).written_ids == (1, 2)
    assert state.statement_budgets == [("price", short), ("rank", chunk_budget)]
    state.statement_budgets.clear()
    state.rank_error = LockHeld()
    assert await r.ns["write_chunk"]({1: 0.7, 2: 0.3}) is None
    assert state.statement_budgets == [("price", short), ("rank", chunk_budget)]
    assert r.ns["lock_retry_until"] == dict.fromkeys(
        (1, 2), 1000 + chunk_budget + PRICE_FLUSH_SECONDS,
    )
    assert r.ns["stats"]["errors"] == 1
    assert not r.ns["stats"].get("price_lock_probes_refused")
    assert state.commits == [1, 2], "the rerank failure rolled its prices back"


async def test_a_probe_refusal_received_late_still_re_arms_no_cooldown(monkeypatch):
    # #10090 (Root's review_pg_delayed_refusal control): the database refused
    # the NOWAIT row lock at once, but the answer reached the task 60 ms later.
    # Judged by elapsed time it re-armed the two-second cooldown and the pair
    # sat unwritten 2.18 s after its holder let go. Judged by the error, it is
    # a refusal: the rows stay known-held and due for the next flush.
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    r.ns["lock_retry_until"].update({1: 0, 2: 0})
    state.refusal_delay = 0.06
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert state.nowait == [True]
    assert r.ns["lock_retry_until"] == {1: 0, 2: 0}
    assert r.ns["stats"]["price_lock_probes_refused"] == 1
    assert not r.ns["stats"].get("errors")
    state.held = False
    clock.t = 1000.25
    assert (await r.ns["write_chunk"]({1: 0.9, 2: 0.4})).written_ids == (1, 2)
    assert not r.ns["lock_retry_until"]


@pytest.mark.parametrize("message", [
    LOCK_TIMEOUT_MESSAGE,  # a table lock the probe queued on, budget spent
    'konnte Sperre für Zeile in Relation "futures_outcomes" nicht setzen',
    'could not obtain lock on row in relation "futures_markets"',
])
async def test_a_probe_55p03_that_is_not_the_known_row_refusal_is_a_counted_timeout_without_cooldown(
    monkeypatch, message,
):
    # Narrowly positive: an unrecognised 55P03 (lock timeout, a localised
    # server, another relation) is never a counted refusal. #10090 fast retry:
    # any 55P03 the price UPDATE raises arms no cooldown (each retry costs at
    # most the 50 ms statement budget); a table lock the probe queues on is
    # recovered at the next flush. On a probe the hold is already known, so it
    # is counted as a repeat timeout, not logged as a fresh error (lane1 R1).
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    r.ns["lock_retry_until"].update({1: 0, 2: 0})
    state.refusal_message = message
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert state.nowait == [True]
    assert r.ns["lock_retry_until"] == {1: 0, 2: 0}
    assert r.ns["stats"]["price_lock_timeouts"] == 1
    assert not r.ns["stats"].get("errors")
    assert not r.ns["stats"].get("price_lock_probes_refused")
    assert ("failure", None) not in r.trace, "a repeat timeout is not logged"


async def test_a_sustained_price_lock_logs_one_error_per_hold_and_counts_each_repeat(
    monkeypatch,
):
    # lane1 R1: with no cooldown a held price row is retried every 0.25 s
    # flush, and a table lock times out every probe. Logged and counted as an
    # error each time, that was ~20 Sentry events a second per held event
    # (parent: ~2). The first timeout in a hold episode stays the one logged
    # error; each repeat is counted in `price_lock_timeouts`. A rerank lock
    # timeout is not the price statement's and still logs every attempt.
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    state.refusal_message = LOCK_TIMEOUT_MESSAGE  # every probe queues on a table lock
    logged = []

    class RecordingLogger:
        def __getattr__(self, level):
            return lambda *args, **kwargs: logged.append(level)

    r.ns["logger"] = RecordingLogger()
    flushes, cadence = 6, 0.25  # production PM_WS_PRICE_FLUSH_SECONDS
    for n in range(flushes):
        clock.t = 1000 + n * cadence
        assert await r.ns["flush_prices"](flush_started=clock.t) is True
    held_attempts = [n for n, (_, ids) in zip(state.nowait, state.attempts) if 1 in ids]
    assert held_attempts == [False] + [True] * (flushes - 1), "retried every flush"
    assert logged == ["exception"], "one logged error for the whole hold"
    assert r.ns["stats"]["errors"] == 1 and r.ns["stats"]["requeued"] == 2
    assert r.ns["stats"]["price_lock_timeouts"] == flushes - 1
    assert not r.ns["stats"].get("price_lock_probes_refused")
    assert set(r.ns["lock_retry_until"]) == {1, 2}
    assert max(r.ns["lock_retry_until"].values()) <= clock.t, "no cooldown armed"

    # The table lock is gone; rerank now times out. Both attempts are probes
    # of the known-held rows, and each still logs and counts as an error.
    state.held = False
    state.rank_error = LockHeld()
    for _ in range(2):
        clock.t = max(r.ns["lock_retry_until"].values()) + PRICE_FLUSH_SECONDS
        assert await r.ns["write_chunk"]({1: 0.9, 2: 0.4}) is None
        assert state.nowait[-1] is True
    assert logged == ["exception"] * 3
    assert r.ns["stats"]["errors"] == 3
    assert r.ns["stats"]["price_lock_timeouts"] == flushes - 1

    # The write lands and ends the episode; the next hold's first timeout is
    # a fresh, logged error again.
    state.rank_error = None
    clock.t = max(r.ns["lock_retry_until"].values()) + PRICE_FLUSH_SECONDS
    assert (await r.ns["write_chunk"]({1: 0.9, 2: 0.4})).written_ids == (1, 2)
    assert not r.ns["lock_retry_until"]
    state.held = True
    clock.t += PRICE_FLUSH_SECONDS
    assert await r.ns["write_chunk"]({1: 0.95, 2: 0.4}) is None
    assert state.nowait[-1] is False
    assert logged == ["exception"] * 4
    assert r.ns["stats"]["errors"] == 4


def _wrapped(fields):
    """asyncpg's error as SQLAlchemy's asyncpg dialect delivers it."""
    raw = asyncpg.exceptions.LockNotAvailableError.new(fields)

    class Adapted(Exception):
        sqlstate = pgcode = raw.sqlstate

    try:
        try:
            raise Adapted(f"{type(raw).__name__}: {raw}") from raw
        except Adapted as adapted:
            raise OperationalError("UPDATE futures_outcomes ...", {}, adapted) from adapted
    except OperationalError as exc:
        return exc


def test_row_refusal_is_identified_by_sqlstate_and_server_message_together():
    refusal = {"C": "55P03", "S": "ERROR", "M": PRICE_ROW_LOCK_REFUSAL_MESSAGE}
    assert is_price_row_lock_refusal(_wrapped(refusal))
    timeout = refusal | {"M": LOCK_TIMEOUT_MESSAGE}
    assert is_lock_timeout(_wrapped(timeout))
    assert not is_price_row_lock_refusal(_wrapped(timeout))
    assert not is_price_row_lock_refusal(_wrapped(refusal | {"C": "40P01"}))
    assert not is_price_row_lock_refusal(RuntimeError(PRICE_ROW_LOCK_REFUSAL_MESSAGE))


async def test_non_lock_error_retains_existing_global_failure_result(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock, error=RuntimeError("connection failed"))
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is False
    assert not r.ns["lock_retry_until"] and not state.commits
    assert not r.ns["successful_price_write_at"]
    assert r.ns["price_buffer"][1] == 0.9 and 2 in r.ns["price_buffer"]


async def test_mixed_lock_failure_holds_back_only_its_event_and_keeps_full_fences(monkeypatch):
    """#10090: one held row (1) in a chunk shared with an unrelated event
    pair. The held event (10) is held back whole, unwritten, unstamped and
    retried; the neighbour (90) commits, withdraws and stamps in that same
    first attempt. Before, the joint chunk rolled 90 back with 10."""
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
    # The joint chunk SKIPS the held event instead of waiting for it: 900/901
    # commit in the first attempt, with no lock budget spent, so the second
    # chunk follows at once. Event 10's third leg (3) is a later chunk's
    # write; its stamp still waits for the held legs.
    assert state.attempts == [(1000, (1, 2, 900, 901)), (1000, (3, 902))]
    assert state.skip == [True, True]
    assert state.commits == [900, 901, 3, 902]
    assert r.ns["stats"]["price_rows_skipped_locked"] == 2
    assert not r.ns["stats"].get("errors")
    # 90 is stamped; 10 is offered only as deferred (its leg 3 committed),
    # never due while its held legs are unwritten.
    assert pending == {10}
    assert any(90 in due for due in admitted)
    assert all(10 not in due for due in admitted)
    # Its withdrawal waits for its price; the neighbour's does not.
    assert ("withdraw", [900]) in r.trace and ("withdraw", [1]) not in r.trace
    assert r.books.keys() == {1}
    # Q491: the held rows stay buffered (with the newer quote) and known-held,
    # due at once (no cooldown), and only their event is retry-isolated.
    assert r.ns["price_buffer"] == {1: 0.9, 2: 0.4}
    assert r.ns["lock_retry_events"] == {10}
    assert r.ns["lock_retry_until"] == {1: 0, 2: 0}

    clock.t = 1001
    assert await r.ns["flush_prices"](flush_started=1001)
    # Alone, the held event is one unit: the existing NOWAIT probe, refused.
    assert state.attempts[-1] == (1001, (1, 2))
    assert state.nowait[-1] is True and state.skip[-1] is False
    assert r.ns["stats"]["price_lock_probes_refused"] == 1

    clock.t = 1003
    # A new question for the held event is part of this admitted cohort too.
    r.ns["price_buffer"][3] = 0.85
    r.ns["price_buffer"][900] = 0.75
    assert await r.ns["flush_prices"](flush_started=1003)
    # The healthy event writes first; the held cohort is probed after it.
    assert state.attempts[-2:] == [(1003, (900,)), (1003, (1, 2, 3))]
    assert state.nowait[-2:] == [False, True]
    assert r.ns["price_buffer"] == {1: 0.9, 2: 0.4, 3: 0.85}
    assert set(r.ns["lock_retry_until"]) == {1, 2, 3}
    assert pending == {10}

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
    # Only rows a lock already refused skip the wait; a fresh chunk keeps it.
    assert state.nowait == [False, False, True]
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
            self.info = session.info

        async def execute(self, stmt, params=None):
            if isinstance(stmt, tuple) and stmt[0] == "price":
                chunk = stmt[1][0]
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


def test_the_minute_line_emits_repeat_price_lock_timeouts(caplog):
    # lane1 R3: a counter computed and never emitted is the defect
    # `_log_stats_line` exists to prevent. A sustained table lock shows as
    # `errors=1` and then nothing, unless the repeats are on the line.
    from app.tasks import polymarket_ws as poly_task

    stats = {"price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 1,
             "price_lock_timeouts": 7}
    blend_stats = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level("INFO", logger=poly_task.logger.name):
        poly_task._log_stats_line(stats, {}, blend_stats)
    assert "lock_timeouts=7" in caplog.text
