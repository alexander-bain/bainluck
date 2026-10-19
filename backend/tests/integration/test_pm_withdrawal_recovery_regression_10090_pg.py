"""#10090 — a source withdrawal survives uncertain commits, worker handoff and
transaction-status errors, and a due withdrawal never slows a healthy quote,
on real PostgreSQL.

## the ship

Worker restarts and transaction errors do not strand source removals, and
waiting withdrawals do not delay healthy live quotes.

## where these cases come from

These are the deciding lab cases of attempts 126, 127, 129 and 130 (the
frozen packets under
``artifacts/live-iteration-goal-20261011/local-blended-web-20261016/``),
ported verbatim in their assertions so they travel with the application
source they judge. Nothing here reads an artifact directory; the lab's result
files became assertion messages.

* attempt126 — a withdrawal or removal transaction whose acknowledgement was
  lost is recovered once its outcome is definitive (committed: one
  invalidation; aborted: the original obligation retries), and recovery
  checking STOPS once the outcome is known.
* attempt127 — the outgoing worker's late commit, in either the price
  withdrawal or the source removal transaction, is delivered by the
  replacement owner; ownership claims never wait and stale owners are fenced.
* attempt129 — a REAL failing ``pg_xact_status`` (a future xid) must not skip
  the custody scan: the committed owed row still loads in the same
  opportunity and the xid stays retained. Cancelling the status lookup keeps
  the debt and releases the session.
* attempt130 — when withdrawal work is due but ownership is unavailable
  (unacquired, superseded, superseded with the removal owed) the healthy
  quote still publishes inside a second and the flush succeeds; a DELETED
  ownership row reclaims, a REPLACED one keeps the stale owner fenced.

Each group fails on the source before its attempt (see the offer evidence);
later groups need APIs that earlier sources do not have.

## the rig

#10090's withdrawal-debt rig (``test_pm_withdrawal_debt_10090_pg``) over the
release-wake rig: the shipped flush closures on the consumer's own pool, real
stamps, and a recording Redis that acknowledges a frame only after an
independent connection reads the committed row. Lost acknowledgements are a
session wrapper that raises after the body while the real transaction stays
open, then commits or rolls back on cue.

Synthetic rows on one machine: order and coherence, not production timing.
The 1 s healthy-quote and 0.2 s claim bounds are the lab's own bounds.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.tasks import polymarket_ws as pm
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
    seed,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (
    start_cadence,
    stop_cadence,
)
from tests.integration.test_pm_withdrawal_debt_10090_pg import (  # noqa: F401
    WIDE,
    consumer,
    flush,
    prime,
    setup,
    state,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

#: The custody scan's statement prefix (`PMWithdrawalDebt.load`).
CUSTODY_SCAN = "SELECT owed_chart_points.id"


def arm_reload(debt, xid):
    """attempt126's parent has no identity argument; keep its actual
    uncertain behaviour so that source fails on the assertion, not a
    TypeError."""
    if "xid" in inspect.signature(debt.require_reload).parameters:
        debt.require_reload(xid=xid)
    else:
        debt.require_reload()


@contextlib.asynccontextmanager
async def committing(rig):
    async with rig.maker() as db:
        yield db
        await db.commit()


def lost_ack_sessions(factory, armed, release, delayed, times, loads, finish):
    """The shipped session factory, except that the first session whose body
    `armed["ready"]` marks raises a lost acknowledgement while its real
    transaction stays open; `release` then commits it (or rolls it back)."""

    @contextlib.asynccontextmanager
    async def sessions():
        cm = factory()
        session = await cm.__aenter__()
        execute = session.execute

        async def observed(stmt, *args, **kw):
            if str(stmt).startswith(CUSTODY_SCAN):
                loads.append(time.monotonic())
            return await execute(stmt, *args, **kw)

        session.execute = observed
        try:
            yield session
        except BaseException as exc:
            await cm.__aexit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            if armed["ready"] and not armed["fired"]:
                armed["fired"] = True
                times["lost_ack"] = time.monotonic()

                async def later():
                    await release.wait()
                    if finish == "rollback":
                        await session.rollback()
                    await cm.__aexit__(None, None, None)
                    times["visible"] = time.monotonic()

                delayed.append(
                    asyncio.create_task(later(), name="controlled-late-removal-commit")
                )
                raise ConnectionError(
                    "controlled lost acknowledgement while original removal "
                    "transaction remains open"
                )
            await cm.__aexit__(None, None, None)

    return sessions


async def signalled_or_raise(task, event, what):
    """Wait at most 2 s for `event`. A task that ended first re-raises its own
    error here (a missing interface reads as itself, not as a timeout); a task
    still running is cancelled and awaited, never abandoned."""
    waiter = asyncio.ensure_future(event.wait())
    try:
        await asyncio.wait(
            {task, waiter}, timeout=2, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
    if event.is_set():
        return
    if task.done():
        task.result()
        raise AssertionError(f"{what}: task ended without signalling")
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    raise AssertionError(f"{what}: not signalled within 2 s")


def record_invalidations(t, notices):
    original_publish = t.r._publish

    async def publish(frames):
        result = await original_publish(frames)
        if any(f.get("invalidation") for f in frames):
            notices.append(time.monotonic())
        return result

    t.r._publish = publish


# ---------------------------------------------------------------- attempt126


@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_definitive_outcome_discovered_then_checking_stops(rig, finish):
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    calls = []

    @contextlib.asynccontextmanager
    async def sessions():
        async with rig.maker() as db:
            original = db.execute

            async def execute(stmt, *a, **kw):
                calls.append(str(stmt))
                return await original(stmt, *a, **kw)

            db.execute = execute
            yield db

    await debt.load(sessions)
    assert debt.loaded
    async with rig.maker() as outgoing:
        xid = (
            await outgoing.execute(text("SELECT pg_current_xact_id()::text"))
        ).scalar_one()
        expected = await debt.record_publications(
            outgoing, [{"event_id": 1, "rev": {"1": 1}, "invalidation": True}]
        )
        arm_reload(debt, xid)
        await debt.load(sessions)
        assert not debt.publications, "uncommitted row adopted"
        await (outgoing.commit() if finish == "commit" else outgoing.rollback())
    await asyncio.sleep(0.27)
    await debt.load(sessions)
    assert debt.publications == (expected if finish == "commit" else {})
    before = len(calls)
    for _ in range(3):
        await asyncio.sleep(0.27)
        await debt.load(sessions)
    result = {
        "finish": finish,
        "queries_after_definitive_scan": len(calls) - before,
        "query_count": len(calls),
        "publication_rows": len(debt.publications),
    }
    assert len(calls) == before, result


async def test_committed_identity_survives_failed_discovery(rig):
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    await debt.load(rig.maker)
    async with rig.maker() as outgoing:
        xid = (
            await outgoing.execute(text("SELECT pg_current_xact_id()::text"))
        ).scalar_one()
        expected = await debt.record_publications(
            outgoing, [{"event_id": 1, "rev": {"1": 2}}]
        )
        await outgoing.commit()
    arm_reload(debt, xid)

    @contextlib.asynccontextmanager
    async def broken():
        async with rig.maker() as db:
            original = db.execute

            async def execute(stmt, *a, **kw):
                if str(stmt).startswith(CUSTODY_SCAN):
                    raise ConnectionError("controlled discovery failure")
                return await original(stmt, *a, **kw)

            db.execute = execute
            yield db

    await debt.load(broken)
    assert not debt.publications
    await asyncio.sleep(0.27)
    await debt.load(rig.maker)
    assert debt.publications == expected
    assert not getattr(debt, "_uncertain_xids", set())


async def test_precommit_body_failure_does_not_arm_permanent_discovery(
    rig,
    consumer,
    monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    original = t.p.ns["withdraw_book_refuted_prices"]

    async def fail(*a, **kw):
        raise ConnectionError("controlled body failure before COMMIT")

    t.p.ns["withdraw_book_refuted_prices"] = fail
    t.p.ns["withdraw_buffer"][1] = WIDE
    await flush(t)
    debt = t.r.withdrawal_debt
    assert not debt._uncertain_commit and not getattr(debt, "_uncertain_xids", set())
    t.p.ns["withdraw_book_refuted_prices"] = original
    await flush(t)
    await t.boundary.join_stamps()
    await t.r.drain_history()


async def test_unknown_status_keeps_identity_and_counts_it(rig):
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    await debt.load(rig.maker)
    async with rig.maker() as db:
        xid = (await db.execute(text("SELECT pg_current_xact_id()::text"))).scalar_one()
        await db.rollback()
    arm_reload(debt, xid)

    @contextlib.asynccontextmanager
    async def unknown():
        async with rig.maker() as db:
            original = db.execute

            async def execute(stmt, *a, **kw):
                if "pg_xact_status" in str(stmt):
                    return SimpleNamespace(all=lambda: [(xid, None)])
                return await original(stmt, *a, **kw)

            db.execute = execute
            yield db

    await debt.load(unknown)
    assert xid in debt._uncertain_xids and debt._unknown_outcomes == 1
    await asyncio.sleep(0.27)
    await debt.load(rig.maker)
    assert not debt._uncertain_xids


async def test_full_page_does_not_retire_committed_identity_early(rig, monkeypatch):
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    await debt.load(rig.maker)
    async with rig.maker() as outgoing:
        xid = (
            await outgoing.execute(text("SELECT pg_current_xact_id()::text"))
        ).scalar_one()
        expected = await debt.record_publications(
            outgoing, [{"event_id": 1, "rev": {"1": n}} for n in [1, 2]]
        )
        await outgoing.commit()
    monkeypatch.setattr(pm, "PM_WITHDRAWAL_DEBT_LOAD_LIMIT", 1)
    arm_reload(debt, xid)
    await debt.load(rig.maker)
    assert len(debt.publications) == 1 and xid in debt._uncertain_xids
    await asyncio.sleep(0.27)
    await debt.load(rig.maker)
    assert len(debt.publications) == 2 and xid in debt._uncertain_xids
    await asyncio.sleep(0.27)
    await debt.load(rig.maker)
    assert debt.publications == expected and not debt._uncertain_xids


@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_late_visible_removal_is_recovered_without_new_quote(
    rig,
    consumer,
    monkeypatch,
    finish,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    factory = t.p.ns["get_task_session"]
    armed = {"ready": False, "fired": False}
    release = asyncio.Event()
    delayed, times, notices, loads = [], {}, [], []
    original_remove = pm.withdraw_attributed_event_sources

    async def removal(*args, **kw):
        result = await original_remove(*args, **kw)
        if result:
            armed["ready"] = True
        return result

    monkeypatch.setattr(pm, "withdraw_attributed_event_sources", removal)
    record_invalidations(t, notices)
    t.p.ns["get_task_session"] = lost_ack_sessions(
        factory, armed, release, delayed, times, loads, finish
    )
    t.p.ns["withdraw_buffer"][1] = WIDE
    stop = asyncio.Event()
    cadence = None
    try:
        await flush(t)
        assert armed["fired"] and delayed and not notices
        t.p.ns["withdraw_buffer"].clear()
        cadence = start_cadence(t, stop)
        # More than one actual 250 ms flush opportunity before commit is made visible.
        await asyncio.sleep(0.68)
        assert not notices, "uncommitted withdrawal reached publication"
        release.set()
        await delayed[0]
        deadline = time.monotonic() + 1.3
        while not notices and time.monotonic() < deadline:
            await asyncio.sleep(0.003)
        result = {
            "finish": finish,
            "visible_at": times["visible"],
            "lost_ack_at": times["lost_ack"],
            "load_count": len(loads),
            "loads_before_visibility": sum(x < times["visible"] for x in loads),
            "loads_after_visibility": sum(x >= times["visible"] for x in loads),
            "eligible_count": 1,
            "delivered_count": len(notices),
            "missing_count": int(not notices),
            "max_completed_seconds": (
                notices[0] - times["visible"] if notices else None
            ),
            "oldest_outstanding_seconds": (
                0 if notices else time.monotonic() - times["visible"]
            ),
            "invalidations": t.invalidations,
            "state": vars(await state(rig)),
            "scope": (
                "commit visibility to committed invalidation publication; "
                "rollback arm retries the original durable withdrawal obligation"
            ),
        }
        assert (
            notices and len(notices) == 1 and notices[0] - times["visible"] < 1
        ), result
        assert (
            result["state"]["source"] is None and result["state"]["vertices"] == 1
        ), result
    finally:
        release.set()
        for task in delayed:
            await task
        if cadence is not None:
            await stop_cadence(t, stop, cadence)
        await t.boundary.join_stamps()
        await t.r.drain_history()


async def test_uncertain_recovery_has_one_inflight_scan_and_fixed_cadence(
    rig,
    consumer,
    monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = t.r.withdrawal_debt
    debt.require_reload()
    factory = t.p.ns["get_task_session"]
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    @contextlib.asynccontextmanager
    async def slow():
        async with factory() as session:
            execute = session.execute

            async def recorded(stmt, *args, **kw):
                calls.append(time.monotonic())
                started.set()
                await release.wait()
                return await execute(stmt, *args, **kw)

            session.execute = recorded
            yield session

    first = asyncio.create_task(debt.load(slow))
    await signalled_or_raise(first, started, "first custody scan")
    others = []
    try:
        # One query lasts longer than the scan period. Concurrent flush callers
        # must not create additional outstanding queries after that period expires.
        await asyncio.sleep(0.28)
        others = [asyncio.create_task(debt.load(slow)) for _ in range(20)]
        await asyncio.sleep(0.01)
        count_while_held = len(calls)
    finally:
        release.set()
        await first
        await asyncio.gather(*others)
    assert count_while_held == 1, {"overlapping_scans": count_while_held}
    before = len(calls)
    await asyncio.gather(*(debt.load(slow) for _ in range(20)))
    assert len(calls) <= before + 1


# ---------------------------------------------------------------- attempt127


async def test_handoff_refuses_immediately_and_fences_old_writers(rig):
    await seed(rig, count=1)
    factory = lambda: committing(rig)  # noqa: E731
    old = pm.PMWithdrawalDebt()
    await old.load(factory)
    async with rig.maker() as outgoing:
        await old.guard_owner(outgoing)
        new = pm.PMWithdrawalDebt()
        start = time.monotonic()
        await new.load(factory)
        elapsed = time.monotonic() - start
        assert new._owner_id is None and elapsed < 0.2
        await outgoing.commit()
    await asyncio.sleep(0.27)
    await new.load(factory)
    assert new._owner_id == old._owner_id
    async with rig.maker() as stale:
        with pytest.raises(RuntimeError, match="superseded"):
            await old.guard_owner(stale)
    async with rig.maker() as current:
        await new.guard_owner(current)


async def test_repeated_replacements_keep_one_row_and_current_owner(rig):
    await seed(rig, count=1)
    factory = lambda: committing(rig)  # noqa: E731
    owners = []
    for _ in range(4):
        debt = pm.PMWithdrawalDebt()
        await debt.load(factory)
        owners.append(debt)
    async with rig.maker() as db:
        count = await db.scalar(
            text("SELECT count(*) FROM owed_chart_points WHERE source=:s"),
            {"s": pm.PM_WITHDRAWAL_DEBT_SOURCE + "_owner"},
        )
        assert count == 1
    for owner in owners[:-1]:
        async with rig.maker() as db:
            with pytest.raises(RuntimeError, match="superseded"):
                await owner.guard_owner(db)
    async with rig.maker() as db:
        await owners[-1].guard_owner(db)


async def test_cancelled_writer_releases_handoff_fence(rig):
    await seed(rig, count=1)
    factory = lambda: committing(rig)  # noqa: E731
    old = pm.PMWithdrawalDebt()
    await old.load(factory)
    entered = asyncio.Event()

    async def writer():
        async with rig.maker() as db:
            await old.guard_owner(db)
            entered.set()
            await asyncio.Future()

    task = asyncio.create_task(writer())
    await signalled_or_raise(task, entered, "writer inside the fence")
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    new = pm.PMWithdrawalDebt()
    await new.load(factory)
    assert new._owner_id is not None


async def test_healthy_price_flows_while_handoff_is_waiting(rig, consumer, monkeypatch):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    old = t.r.withdrawal_debt
    async with rig.maker() as outgoing:
        await old.guard_owner(outgoing)
        t.r.withdrawal_debt = pm.PMWithdrawalDebt()
        stop = asyncio.Event()
        cadence = start_cadence(t, stop)
        t.accept(1, 0.73)
        start = time.monotonic()
        try:
            async with asyncio.timeout(0.95):
                while not any(e == 1 and v == 0.73 for _, e, v, _ in t.pubs):
                    await asyncio.sleep(0.003)
            elapsed = time.monotonic() - start
            assert elapsed < 1 and t.r.withdrawal_debt._owner_id is None
        finally:
            await stop_cadence(t, stop, cadence)
    await t.r.drain_history()


@pytest.mark.parametrize("transaction", ["withdrawal", "removal"])
@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_replacement_recovers_outgoing_late_removal_without_new_quote(
    rig,
    consumer,
    monkeypatch,
    finish,
    transaction,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    initial = vars(await state(rig))
    factory = t.p.ns["get_task_session"]
    armed = {"ready": False, "fired": False}
    release = asyncio.Event()
    delayed, times, notices, loads = [], {}, [], []
    if transaction == "removal":
        original_remove = pm.withdraw_attributed_event_sources

        async def removal(*args, **kw):
            result = await original_remove(*args, **kw)
            if result:
                armed["ready"] = True
            return result

        monkeypatch.setattr(pm, "withdraw_attributed_event_sources", removal)
    else:
        original_record = pm.PMWithdrawalDebt.record

        async def record(*args, **kw):
            result = await original_record(*args, **kw)
            if result:
                armed["ready"] = True
            return result

        monkeypatch.setattr(pm.PMWithdrawalDebt, "record", record)
    record_invalidations(t, notices)
    t.p.ns["get_task_session"] = lost_ack_sessions(
        factory, armed, release, delayed, times, loads, finish
    )
    t.p.ns["withdraw_buffer"][1] = WIDE
    stop = asyncio.Event()
    cadence = None
    try:
        await flush(t)
        assert armed["fired"] and delayed and not notices
        t.p.ns["withdraw_buffer"].clear()
        t.r.withdrawal_debt = pm.PMWithdrawalDebt()
        await t.r.withdrawal_debt.load(factory)
        assert not t.r.withdrawal_debt.publications
        cadence = start_cadence(t, stop)
        # More than one actual 250 ms flush opportunity before commit is made visible.
        await asyncio.sleep(0.68)
        assert not notices, "uncommitted withdrawal reached publication"
        release.set()
        await delayed[0]
        deadline = time.monotonic() + 1.3
        while not notices and time.monotonic() < deadline:
            await asyncio.sleep(0.003)
        obligation = transaction == "removal" or finish == "commit"
        result = {
            "finish": finish,
            "transaction": transaction,
            "visible_at": times["visible"],
            "lost_ack_at": times["lost_ack"],
            "load_count": len(loads),
            "loads_before_visibility": sum(x < times["visible"] for x in loads),
            "loads_after_visibility": sum(x >= times["visible"] for x in loads),
            "eligible_count": int(obligation),
            "delivered_count": len(notices),
            "missing_count": int(not notices and obligation),
            "max_completed_seconds": (
                notices[0] - times["visible"] if notices else None
            ),
            "oldest_outstanding_seconds": (
                0 if notices or not obligation else time.monotonic() - times["visible"]
            ),
            "invalidations": t.invalidations,
            "state": vars(await state(rig)),
            "scope": (
                "replacement owner; outgoing transaction visibility to "
                "publication; rollback retries original durable obligation"
            ),
        }
        if transaction == "withdrawal" and finish == "rollback":
            assert (
                not notices
                and result["state"]["price"] == 0.6
                and result["state"]["source"] == initial["source"]
                and result["state"]["vertices"] == 0
            ), result
        else:
            assert (
                notices and len(notices) == 1 and notices[0] - times["visible"] < 1
            ), result
            assert (
                result["state"]["source"] is None and result["state"]["vertices"] == 1
            ), result
    finally:
        release.set()
        for task in delayed:
            await task
        if cadence is not None:
            await stop_cadence(t, stop, cadence)
        await t.boundary.join_stamps()
        await t.r.drain_history()


# ---------------------------------------------------------------- attempt129


async def test_future_xid_error_still_loads_committed_row_in_same_opportunity(
    rig,
    caplog,
):
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    factory = lambda: committing(rig)  # noqa: E731
    await debt.load(factory)
    async with committing(rig) as db:
        now = int(
            (await db.execute(text("SELECT pg_current_xact_id()::text"))).scalar_one()
        )
        expected = await debt.record_publications(
            db, [{"event_id": 1, "rev": {"1": 7}, "invalidation": True}]
        )
    future = str(now + 1000000)
    # Establish an actual PostgreSQL error, not a mocked successful NULL.
    async with rig.maker() as db:
        with pytest.raises(Exception, match="future"):
            await db.execute(
                text("SELECT pg_xact_status(CAST(:xid AS xid8))"), {"xid": int(future)}
            )
    debt.require_reload(xid=future)
    before = time.monotonic()
    await debt.load(factory)
    result = {
        "committed_rows": len(expected),
        "loaded_rows": len(debt.publications),
        "same_opportunity": True,
        "elapsed_seconds": time.monotonic() - before,
        "identity_retained": future in debt._uncertain_xids,
        "unknown_count": debt._unknown_outcomes,
    }
    assert debt.publications == expected, result
    assert future in debt._uncertain_xids and debt._unknown_outcomes == 1
    await asyncio.sleep(0.27)
    await debt.load(factory)
    assert (
        debt.publications == expected
        and future in debt._uncertain_xids
        and debt._unknown_outcomes == 2
    )
    errors = [
        r
        for r in caplog.records
        if r.levelname == "ERROR" and "withdrawal debt not loaded" in r.message
    ]
    warnings = [
        r for r in caplog.records if "transaction outcome unavailable" in r.message
    ]
    assert not errors and len(warnings) == 1


async def test_cancelled_status_lookup_preserves_debt_and_releases_session(rig):
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    await debt.load(rig.maker)
    async with rig.maker() as db:
        xid = (await db.execute(text("SELECT pg_current_xact_id()::text"))).scalar_one()
        expected = await debt.record_publications(
            db, [{"event_id": 1, "rev": {"1": 8}, "invalidation": True}]
        )
        await db.commit()
    debt.require_reload(xid=xid)
    entered = asyncio.Event()

    @contextlib.asynccontextmanager
    async def slow():
        async with rig.maker() as db:
            original = db.execute

            async def execute(stmt, *args, **kwargs):
                if "pg_xact_status" in str(stmt):
                    assert (
                        db.in_nested_transaction()
                    ), "status lookup not isolated in savepoint"
                    entered.set()
                    await original(text("SELECT pg_sleep(30)"))
                return await original(stmt, *args, **kwargs)

            db.execute = execute
            yield db

    task = asyncio.create_task(debt.load(slow))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert not debt._load_running
        assert xid in debt._uncertain_xids and not debt.publications
        assert rig.engine.pool.checkedout() == 0
        await asyncio.sleep(0.27)
        await debt.load(rig.maker)
        assert debt.publications == expected and not debt._uncertain_xids
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------- attempt130


@pytest.mark.parametrize("mode", ["unacquired", "superseded", "superseded-removal"])
async def test_due_withdrawal_does_not_slow_healthy_quote(
    rig,
    consumer,
    monkeypatch,
    caplog,
    mode,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    old = t.r.withdrawal_debt
    holder = None
    factory = t.p.ns["get_task_session"]
    if mode == "superseded-removal":
        original_remove = pm.withdraw_attributed_event_sources

        async def refuse(*a, **kw):
            raise ConnectionError("setup: hold removal for handoff")

        monkeypatch.setattr(pm, "withdraw_attributed_event_sources", refuse)
        t.p.ns["withdraw_buffer"][1] = WIDE
        await flush(t)
        monkeypatch.setattr(pm, "withdraw_attributed_event_sources", original_remove)
        assert old.owed and (await state(rig)).price is None
        t.p.ns["withdraw_buffer"].clear()
    if mode == "unacquired":
        holder = rig.maker()
        await old.guard_owner(holder)
        t.r.withdrawal_debt = pm.PMWithdrawalDebt()
    else:
        replacement = pm.PMWithdrawalDebt()
        await replacement.load(factory)
        assert replacement._owner_token != old._owner_token
    if mode != "superseded-removal":
        t.p.ns["withdraw_buffer"][1] = WIDE
    debt = t.r.withdrawal_debt
    first = asyncio.Event()
    flush_results, published = [], []
    tracked = t.tracked_flush
    publish = t.r._publish

    async def tracked_flush(started):
        result = await tracked(started)
        flush_results.append(result)
        first.set()
        return result

    async def observed(frames):
        result = await publish(frames)
        if any(
            f.get("event_id") == 2 and f.get("source_value") == 0.73 for f in frames
        ):
            published.append(time.monotonic())
        return result

    t.tracked_flush = tracked_flush
    t.r._publish = observed
    caplog.clear()
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    try:
        await asyncio.wait_for(first.wait(), 2)
        accepted = time.monotonic()
        t.accept(2, 0.73)
        until = accepted + 1.15
        while not published and time.monotonic() < until:
            await asyncio.sleep(0.003)
        elapsed = None if not published else published[0] - accepted
        result = {
            "mode": mode,
            "input_to_publish_ms": None if elapsed is None else elapsed * 1000,
            "delivered_count": int(bool(published)),
            "eligible_count": 1,
            "oldest_outstanding_seconds": (
                0 if published else time.monotonic() - accepted
            ),
            "flush_results": flush_results.copy(),
            "withdrawal_still_owed": bool(debt.owed or t.p.ns["withdraw_buffer"]),
        }
        assert elapsed is not None and elapsed < 1, result
        assert all(flush_results), result
        await asyncio.sleep(0.55)
        assert debt.owed or t.p.ns["withdraw_buffer"]
        assert (await state(rig)).source is not None and not t.invalidations
        warnings = [
            x for x in caplog.records if "withdrawal ownership deferred" in x.message
        ]
        assert len(warnings) == 1
        assert not [x for x in caplog.records if x.levelname == "ERROR"]
        if mode != "unacquired":
            async with rig.maker() as db:
                await replacement.guard_owner(db)
    finally:
        await stop_cadence(t, stop, cadence)
        if holder is not None:
            await holder.rollback()
            await holder.close()


async def test_missing_owner_row_reclaims_and_finishes_due_withdrawal(
    rig,
    consumer,
    monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = t.r.withdrawal_debt
    old_id = debt._owner_id
    async with rig.engine.begin() as db:
        await db.execute(
            text("DELETE FROM owed_chart_points WHERE id=:id"), {"id": old_id}
        )
    t.p.ns["withdraw_buffer"][1] = WIDE
    results = [await flush(t)]
    await asyncio.sleep(0.27)
    results.append(await flush(t))
    current = await state(rig)
    outcome = {
        "flush_results": results,
        "reclaimed": debt._owner_id is not None and debt._owner_id != old_id,
        "source_removed": current.source is None,
        "invalidations": len(t.invalidations),
        "remaining_withdrawals": len(debt.owed),
    }
    assert (
        outcome["reclaimed"]
        and outcome["source_removed"]
        and outcome["invalidations"] == 1
    ), outcome
    assert all(results) and not debt.owed and not t.p.ns["withdraw_buffer"]
    async with rig.maker() as db:
        await debt.guard_owner(db)


async def test_recreated_row_does_not_let_stale_owner_steal_it(
    rig,
    consumer,
    monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    old = t.r.withdrawal_debt
    async with rig.engine.begin() as db:
        await db.execute(
            text("DELETE FROM owed_chart_points WHERE id=:id"), {"id": old._owner_id}
        )
    replacement = pm.PMWithdrawalDebt()
    await replacement.load(t.p.ns["get_task_session"])
    assert replacement._owner_id != old._owner_id
    t.p.ns["withdraw_buffer"][1] = WIDE
    assert await flush(t)
    await asyncio.sleep(0.27)
    assert await flush(t)
    async with rig.maker() as db:
        await replacement.guard_owner(db)
    assert (await state(rig)).source is not None and not t.invalidations
    assert t.p.ns["withdraw_buffer"] and old._owner_id != replacement._owner_id
