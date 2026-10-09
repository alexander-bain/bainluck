"""A game's own quote cleanup must not wait for unrelated price writes.

Execute the shipped closure bodies and chunk planner. The database boundary is
held by asyncio Events; this proves ordering, not production latency.
"""

import ast
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Mapping, Optional

from app.tasks.polymarket_ws import PRICE_CHUNK_LOCK_TIMEOUT_MS, _PMCatalogFlushBoundary
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, is_lock_timeout, lock_timeout_value

ROOT = Path(__file__).resolve().parents[1]


def compile_functions(path, names, namespace):
    tree = ast.parse(path.read_text())
    nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
    ]
    assert {n.name for n in nodes} == set(names)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
            str(path),
            "exec",
        ),
        namespace,
    )
    return namespace


def rig(
    *,
    batch=None,
    mapping=None,
    books=None,
    fail=False,
    replace=False,
    failed_price=None
):
    batch = dict(batch if batch is not None else {1: 0.6, 2: 0.4, 900: 0.1})
    # #10090: 900 is a BRIDGED open leg (event 90), so it stays on the game
    # flush; an eventless open leg is `flush_standalone`'s.
    mapping = mapping or {1: 10, 2: 10, 900: 90}
    books = dict(books if books is not None else {1: (0.1, 0.9)})
    trace, marks = [], []
    entered, release = asyncio.Event(), asyncio.Event()
    control = {"fail": fail, "replace": replace}

    class Refresher:
        async def publish_market_changes(self, session):
            trace.append(("publish", None))

        async def refresh(self, ids, **kwargs):
            trace.append(("refresh", sorted(ids)))

        async def refresh_pending(self, **kwargs):
            trace.append(("pending", None))

    class Session:
        async def execute(self, statement, params=None):
            if statement is SET_LOCK_TIMEOUT_SQL:
                trace.append(("lock_budget", params))
            return SimpleNamespace(rowcount=1)

    @asynccontextmanager
    async def session():
        trace.append(("begin", None))
        try:
            yield Session()
        except Exception:
            trace.append(("rollback", None))
            raise
        else:
            trace.append(("commit", None))

    async def withdraw(session, selected):
        trace.append(("withdraw", sorted(selected)))
        if control["fail"]:
            raise RuntimeError("held database failure")
        if control["replace"]:
            books[1] = (0.2, 0.8)
        return [
            SimpleNamespace(id=oid, market_id=oid, last_updated=1) for oid in selected
        ]

    async def write(chunk, *, final=False, start_market_publish=None):
        trace.append(("write", list(chunk)))
        if 900 in chunk:
            entered.set()
            await release.wait()
        if failed_price is not None and failed_price in chunk:
            return False
        if start_market_publish is not None:
            start_market_publish(None)
        for oid, value in chunk.items():
            if batch.get(oid) == value:
                batch.pop(oid)
        return True

    ns = {
        "Optional": Optional,
        "Iterable": Iterable,
        "Mapping": Mapping,
        "FLUSH_CHUNK_ROWS": 2,
        "OPEN_FLUSH_CHUNKS_PER_FLUSH": 2,
        "buffer_lock": asyncio.Lock(),
        "catalog_boundary": _PMCatalogFlushBoundary(),
        "price_buffer": batch,
        "withdraw_buffer": books,
        "withdrawal_retry_until": {},
        "lock_retry_until": {},
        "lock_retry_events": set(),
        "successful_price_write_at": {},
        "PRICE_CHUNK_LOCK_TIMEOUT_MS": PRICE_CHUNK_LOCK_TIMEOUT_MS,
        "SET_LOCK_TIMEOUT_SQL": SET_LOCK_TIMEOUT_SQL,
        "lock_timeout_value": lock_timeout_value,
        "is_lock_timeout": is_lock_timeout,
        "PRICE_FLUSH_SECONDS": 2,
        "input_marks": {oid: oid for oid in batch},
        "event_id_by_outcome": mapping,
        "market_by_outcome": {oid: oid for oid in batch},
        "non_blend_outcome_ids": set(),
        "open_outcome_ids": {900, 901},
        "open_complement_of": {1: 2, 2: 1},
        "stats": defaultdict(int),
        "write_chunk": write,
        "get_task_session": session,
        "withdraw_book_refuted_prices": withdraw,
        "queue_market_change": lambda *a, **k: None,
        "rerank_market_fields_stmt": lambda ids: ids,
        "logger": SimpleNamespace(exception=lambda *a: trace.append(("failure", None))),
        "blend_refresher": Refresher(),
        "tail_receipts": SimpleNamespace(stage=lambda x: marks.extend(x)),
        "event_ids_for_outcomes": lambda m, ids: {m[x] for x in ids if x in m},
    }
    compile_functions(
        ROOT / "app/tasks/polymarket_open_contracts.py", ["plan_flush_chunks"], ns
    )
    compile_functions(
        ROOT / "app/tasks/polymarket_ws.py",
        [
            "standalone_open_outcome_ids",
            "flush_withdrawals",
            "_flush_prices",
            "_flush_standalone",
            "flush_prices",
            "flush_standalone",
        ],
        ns,
    )
    return SimpleNamespace(
        ns=ns,
        trace=trace,
        marks=marks,
        entered=entered,
        release=release,
        books=books,
        control=control,
    )


def test_game_is_refreshed_before_unrelated_blocked_write():
    async def run():
        r = rig()
        task = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
        try:
            await asyncio.wait_for(r.entered.wait(), 1)
            assert ("refresh", [10]) in r.trace
            assert (
                r.trace.index(("withdraw", [1]))
                < r.trace.index(("refresh", [10]))
                < r.trace.index(("write", [900]))
            )
            assert not task.done()
        finally:
            r.release.set()
            await task
        assert r.trace.count(("refresh", [10])) == 1
        assert r.trace.count(("withdraw", [1])) == 1
        assert r.marks == [1, 2, 900]

    asyncio.run(run())


def test_event_waits_for_its_later_chunk_and_keeps_binary_pair_atomic():
    async def run():
        r = rig(batch={1: 0.6, 2: 0.4, 3: 0.7, 900: 0.1}, mapping={1: 10, 2: 10, 3: 10})
        r.release.set()
        assert await r.ns["flush_prices"]()
        assert (
            r.trace.index(("write", [1, 2]))
            < r.trace.index(("write", [3]))
            < r.trace.index(("withdraw", [1]))
            < r.trace.index(("refresh", [10]))
        )
        assert r.trace.count(("refresh", [10])) == 1

    asyncio.run(run())


def test_failed_withdrawal_does_not_early_publish_or_retry_twice():
    async def run():
        r = rig(fail=True)
        task = asyncio.create_task(r.ns["flush_prices"]())
        try:
            await asyncio.wait_for(r.entered.wait(), 1)
            assert ("refresh", [10]) not in r.trace
        finally:
            r.release.set()
            result = await task
        assert result is False
        assert r.trace.count(("withdraw", [1])) == 1
        assert 1 in r.books
        # Ordinary tail fallback remains; next flush, not same-flush retry,
        # handles the retained withdrawal.
        r.control["fail"] = False
        assert await r.ns["flush_prices"]()
        assert 1 not in r.books
        assert r.trace.count(("withdraw", [1])) == 2

    asyncio.run(run())


def test_failed_price_chunk_keeps_withdrawal_in_the_original_tail():
    async def run():
        r = rig(failed_price=1)
        r.release.set()
        assert not await r.ns["flush_prices"]()
        assert r.trace.index(("write", [900])) < r.trace.index(("withdraw", [1]))
        assert 1 in r.ns["price_buffer"] and 2 in r.ns["price_buffer"]

    asyncio.run(run())


def test_newer_book_during_withdrawal_is_retained_for_next_flush():
    async def run():
        r = rig(replace=True)
        r.release.set()
        assert await r.ns["flush_prices"]()
        assert r.books[1] == (0.2, 0.8)
        assert r.trace.count(("withdraw", [1])) == 1
        r.control["replace"] = False
        assert await r.ns["flush_prices"]()
        assert not r.books

    asyncio.run(run())


def test_unrelated_and_unmapped_withdrawals_keep_after_price_order():
    async def run():
        # 55: a slate leg with no event (not open), so still the game flush's.
        r = rig(
            books={1: (0.1, 0.9), 44: (0.2, 0.8), 55: (0.3, 0.7)},
            mapping={1: 10, 2: 10, 44: 20, 900: 90},
        )
        r.release.set()
        assert await r.ns["flush_prices"]()
        assert r.trace.index(("withdraw", [44, 55])) > r.trace.index(("write", [900]))
        assert not r.books

    asyncio.run(run())


def test_quiet_and_withdrawal_only_flushes_and_failed_quiet_retry():
    async def run():
        quiet = rig(batch={}, books={})
        assert await quiet.ns["flush_prices"]()
        assert quiet.trace == [("pending", None)]
        r = rig(batch={})
        assert await r.ns["flush_prices"]()
        assert ("refresh", [10]) in r.trace
        bad = rig(batch={}, fail=True)
        assert not await bad.ns["flush_prices"]()
        assert bad.books

    asyncio.run(run())


def test_no_withdrawal_keeps_original_early_refresh_and_final_drain():
    async def run():
        r = rig(books={})
        r.release.set()
        assert await r.ns["flush_prices"](final=True)
        assert ("withdraw", [1]) not in r.trace
        assert r.trace.index(("refresh", [10])) < r.trace.index(("write", [900]))

    asyncio.run(run())


def test_lock_held_withdrawal_keeps_books_and_fence_without_sleeping_healthy_flush(monkeypatch):
    from app.tasks import live_blend_refresh as module

    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])

    class LockHeld(Exception):
        sqlstate = "55P03"

    async def run():
        r = rig()
        r.release.set()
        original = r.ns["withdraw_book_refuted_prices"]
        attempts, admissions = [], []
        original_refresher = r.ns["blend_refresher"]

        async def withdraw(session, books):
            attempts.append((clock[0], set(books)))
            if len(attempts) == 1:
                clock[0] += 0.5
                r.books[1] = (0.2, 0.8)  # newer book survives the rollback
                raise LockHeld()
            return await original(session, books)

        class Refresher:
            publish_market_changes = original_refresher.publish_market_changes

            async def refresh(self, ids, **kwargs):
                admissions.append(set(ids) - set(kwargs.get("defer_event_ids", ())))

            async def refresh_pending(self, **kwargs):
                admissions.append({10} - set(kwargs.get("defer_event_ids", ())))

        r.ns["withdraw_book_refuted_prices"] = withdraw
        r.ns["blend_refresher"] = Refresher()
        assert await r.ns["flush_prices"](flush_started=1000) is True
        assert attempts == [(1000.0, {1})]
        assert r.books == {1: (0.2, 0.8)}
        assert r.ns["withdrawal_retry_until"] == {1: 1002.5}
        assert ("rollback", None) in r.trace and any(90 in ids for ids in admissions)
        assert all(10 not in ids for ids in admissions)
        assert r.trace.count(("lock_budget", {"ms": "500ms"})) == 1

        # A new book on another leg of the held event cannot bypass cooldown.
        r.books[2] = (0.3, 0.7)
        clock[0] = 1001
        r.ns["price_buffer"][900] = 0.8
        assert await r.ns["flush_prices"](flush_started=1001) is True
        assert len(attempts) == 1 and set(r.books) == {1, 2}
        assert r.trace.count(("write", [900])) == 2
        assert all(10 not in ids for ids in admissions)

        # Healthy event withdrawal can still commit during that held interval.
        r.books[900] = (0.2, 0.8)
        assert await r.ns["flush_withdrawals"](only_events={90}) == [900]
        assert attempts[-1] == (1001, {900}) and set(r.books) == {1, 2}
        clock[0] = 1002.5
        assert await r.ns["flush_prices"](flush_started=1002.5) is True
        assert attempts[-1] == (1002.5, {1, 2})
        assert not r.books and not r.ns["withdrawal_retry_until"]
        assert 10 in admissions[-1]

    asyncio.run(run())


def test_final_withdrawal_ignores_cooldown_and_sets_no_periodic_budget(monkeypatch):
    from app.tasks import live_blend_refresh as module

    monkeypatch.setattr(module, "_mono", lambda: 1000)

    async def run():
        r = rig(batch={})
        r.ns["withdrawal_retry_until"] = {1: 1002}
        assert await r.ns["flush_withdrawals"](only_events={10}) == []
        assert r.books and not r.trace
        assert await r.ns["flush_prices"](final=True) is True
        assert ("withdraw", [1]) in r.trace and not r.books
        assert not any(kind == "lock_budget" for kind, _ in r.trace)
        assert not r.ns["withdrawal_retry_until"]

    asyncio.run(run())
