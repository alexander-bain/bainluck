"""A held PM whole chunk rolls back, cools down and leaves healthy chunks eligible."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.tasks.polymarket_ws import PRICE_CHUNK_LOCK_TIMEOUT_MS
from app.tasks.kalshi_ws import PRICE_FLUSH_SECONDS
from app.tasks.live_blend_refresh import run_flush_cadence
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, is_lock_timeout, lock_timeout_value
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions, rig
from tests.test_ws_flush_cadence_10090 import _FakeTime


class LockHeld(Exception):
    sqlstate = "55P03"


def writer_rig(clock, *, error=None):
    r = rig(books={1: (0.2, 0.8)})
    r.release.set()
    state = SimpleNamespace(held=True, attempts=[], settings=[], commits=[], pending=set())

    class Session:
        async def execute(self, stmt, params=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:
                assert params == {"ms": "500ms"}
                state.settings.append(clock.t)
                return SimpleNamespace(rowcount=1)
            kind, values = stmt
            if kind == "rank":
                return SimpleNamespace(rowcount=len(values))
            chunk = values
            state.attempts.append((clock.t, tuple(chunk)))
            state.pending.update(chunk)
            if 1 in chunk and state.held:
                # A newer accepted quote survives the whole transaction rollback.
                r.ns["price_buffer"][1] = 0.9
                clock.t += 0.5
                raise error or LockHeld()
            rows = [SimpleNamespace(ord=i, id=oid, market_id=oid,
                                    quote_moved=True, last_updated=1)
                    for i, oid in enumerate(chunk)]
            return SimpleNamespace(all=lambda: rows)

    @asynccontextmanager
    async def session():
        try:
            yield Session()
        except Exception:
            state.pending.clear()
            r.trace.append(("rollback", None))
            raise
        else:
            state.commits.extend(sorted(state.pending))
            state.pending.clear()
            r.trace.append(("commit", None))

    r.ns.update(
        get_task_session=session, lock_retry_until={},
        PRICE_CHUNK_LOCK_TIMEOUT_MS=PRICE_CHUNK_LOCK_TIMEOUT_MS,
        PRICE_FLUSH_SECONDS=PRICE_FLUSH_SECONDS, SET_LOCK_TIMEOUT_SQL=SET_LOCK_TIMEOUT_SQL,
        is_lock_timeout=is_lock_timeout, lock_timeout_value=lock_timeout_value,
        chunk_price_update_stmt=lambda chunk: ("price", chunk),
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
    assert state.commits == [900, 900, 900, 1, 2, 900]
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
    assert await r.ns["write_chunk"]({1: 0.9, 2: 0.4}, final=True) is True
    assert len(state.settings) == 1  # no SET in the final transaction
    assert state.commits == [1, 2] and not r.ns["lock_retry_until"]


async def test_non_lock_error_retains_existing_global_failure_result(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock, error=RuntimeError("connection failed"))
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is False
    assert not r.ns["lock_retry_until"] and not state.commits
    assert r.ns["price_buffer"][1] == 0.9 and 2 in r.ns["price_buffer"]
