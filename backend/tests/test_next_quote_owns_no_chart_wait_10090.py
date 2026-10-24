"""A genuine second same-game quote pays its stamp while old history waits."""

import asyncio
import contextlib
import contextvars
from types import SimpleNamespace
import pytest
from tests.test_live_blend_refresh import (
    NormalRecoverySession,
    TestTheHeadlineDoesNotWaitForItsChartPoint as _HeadlineRig,
    _refuse_redis_without_a_socket,
    is_normal_recovery_owner,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_second_changed_quote_commits_and_publishes_before_old_history(
    monkeypatch, source
):
    from app.tasks.kalshi_ws import _KalshiPriceOwner
    from app.tasks.polymarket_ws import _PMStampOwner

    r, log = _HeadlineRig()._rig(monkeypatch, 1)
    r.source = source
    session = next(
        cell.cell_contents
        for cell in r._session_factory.__wrapped__.__closure__
        if hasattr(cell.cell_contents, "_returned")
    )
    session._returned = {
        source: {"value": 0.40, "updated_at": "2026-10-11T00:52:30+00:00"}
    }
    entered, release = asyncio.Event(), asyncio.Event()
    price, histories, frames = [0.40], [], []

    def reading(*args):
        return SimpleNamespace(
            home_probability=price[0],
            away_probability=None,
            draw_probability=None,
            eligibility=None,
            market=SimpleNamespace(id=10, name="game"),
            outcome=SimpleNamespace(name="home"),
            yes_probability=price[0],
        )

    async def chart(session, **kw):
        histories.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    async def publish(batch):
        frames.extend(batch)
        log.extend(("frame", frame["event_id"]) for frame in batch)

    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", reading)
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    monkeypatch.setattr(r, "_publish", publish)
    owner = _KalshiPriceOwner() if source == "kalshi" else _PMStampOwner(r)
    first = asyncio.create_task(r.refresh([1], flush_started=1000.0))
    if source == "kalshi":
        owner.stamping, owner.stamping_events, owner.stamping_fresh = first, {1}, {1}
        join = lambda: owner.join_stamp(r)
    else:
        owner.task, owner.events, owner.fresh = first, {1}, {1}
        join = owner.join
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert not release.is_set() and len(frames) == 1
        await asyncio.wait_for(join(), 0.25)
        assert not release.is_set()
        price[0] = 0.60
        session.returned_rev = 43
        session._returned = {
            source: {"value": 0.60, "updated_at": "2026-10-11T00:52:32+00:00"}
        }
        await asyncio.wait_for(r.refresh([1], flush_started=1002.0), 0.25)
        assert r.stats["stamped"] == 2
        assert [frame["source_value"] for frame in frames] == [0.40, 0.60]
        assert r._last_written_value == {1: 0.60}
        assert len(histories) == 1, "the 25-second chart reservation remains bounded"
        assert not r.pending_event_ids(), "history debt is not blend debt"
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)
        if hasattr(r, "drain_history"):
            await r.drain_history()
    assert len(histories) == 1


_PENDING_CUSTODY = contextvars.ContextVar("pending_custody", default=None)


class _MemoryCustody:
    """`OwedChartCustody`'s interface over a dict, for the unit rig (#11181).

    Each write is applied only when the session context that made it exits
    without an exception (`_transactional`), so a stamp or chart transaction
    that fails leaves custody as it was, as Postgres would. The real table's
    atomic boundary, replay and restart are proven on Postgres in
    `tests/integration/test_owed_chart_custody_11181_pg.py`. One store per
    test, shared by every rig the test builds, as one database would be."""

    def __init__(self):
        self.rows, self._next = {}, 1

    def _later(self, op):
        pending = _PENDING_CUSTODY.get()
        assert pending is not None, "custody write outside a session"
        pending.append(op)

    async def record(self, session, source, event_id, value, reading):
        from app.tasks.live_blend_refresh import _chart_reading_payload

        custody_id, self._next = self._next, self._next + 1
        row = (source, event_id, value, _chart_reading_payload(reading))
        self._later(lambda: self.rows.__setitem__(custody_id, row))
        return custody_id

    async def settle(self, session, custody_id):
        if custody_id not in self.rows:
            return False
        self._later(lambda: self.rows.pop(custody_id, None))
        return True

    async def load(self, session, source, held_ids, limit):
        return [
            (cid, eid, value, payload)
            for cid, (src, eid, value, payload) in sorted(self.rows.items())
            if src == source and cid not in held_ids
        ][:limit]

    def _transactional(self, factory):
        @contextlib.asynccontextmanager
        async def wrapped():
            pending = []
            token = _PENDING_CUSTODY.set(pending)
            try:
                async with factory() as session:
                    yield session
            finally:
                _PENDING_CUSTODY.reset(token)
            for op in pending:
                op()

        wrapped.__wrapped__ = factory
        return wrapped


def _custody(monkeypatch):
    store = getattr(monkeypatch, "_owed_chart_custody_11181", None)
    if store is None:
        store = _MemoryCustody()
        monkeypatch._owed_chart_custody_11181 = store
    return store


async def _custody_read(r):
    """A quiet flush before the first quote: the run's first custody read
    completes, so memory takes points until its bound."""
    await r.refresh_pending(flush_started=999)
    await r._history_task
    assert not r._custody_backlog


def _ready_rig(monkeypatch):
    r, log = _HeadlineRig()._rig(monkeypatch, 1)
    session = next(
        cell.cell_contents
        for cell in r._session_factory.__wrapped__.__closure__
        if hasattr(cell.cell_contents, "_returned")
    )
    custody = _custody(monkeypatch)
    r._chart_custody, r._custody_backlog = custody, True
    r._session_factory = custody._transactional(r._session_factory)
    frames, price = [], [0.40]
    session._returned = {
        "polymarket": {"value": 0.40, "updated_at": "2026-10-11T00:52:30+00:00"}
    }

    def reading(*args):
        return SimpleNamespace(
            home_probability=price[0],
            away_probability=None,
            draw_probability=None,
            eligibility=None,
            market=SimpleNamespace(id=10, name="game"),
            outcome=SimpleNamespace(name="home"),
            yes_probability=price[0],
        )

    async def publish(batch):
        frames.extend(batch)

    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability", reading)
    monkeypatch.setattr(r, "_publish", publish)
    return r, session, frames, price


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_real_price_flush_second_same_game_frame_precedes_old_history(
    monkeypatch, source
):
    """Execute shipped price closures, not a manually relaunched refresher."""
    r, session, frames, price = _ready_rig(monkeypatch)
    r.source = source
    session._returned = {
        source: {"value": 0.40, "updated_at": "2026-10-11T00:52:30+00:00"}
    }
    entered, release = asyncio.Event(), asyncio.Event()

    async def chart(session, **kw):
        entered.set()
        await release.wait()
        return object(), True

    async def market_publish(session):
        pass

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    r.publish_market_changes = market_publish
    if source == "kalshi":
        from tests.test_kalshi_game_isolation_10655 import rig

        p = rig()
        p.batch.clear()
        p.batch.update({1: (0.40, 0.39, 0.41), 2: (0.60, 0.59, 0.61)})
        p.events.clear()
        p.events.update({1: 1, 2: 1})
        p.release.set()
        p.ns["blend_refresher"] = r
        flush = lambda clock: p.flush(clock)

        async def join():
            await p.ns["prices"].join_stamp(r)

        def change():
            p.batch.update({1: (0.60, 0.59, 0.61), 2: (0.40, 0.39, 0.41)})

        def price_committed_twice():
            return p.committed == [1, 2, 1, 2]

    else:
        from tests.test_polymarket_withdrawal_speed_10651 import rig

        p = rig(batch={1: 0.40, 2: 0.60}, mapping={1: 1, 2: 1}, books={})
        p.ns["blend_refresher"] = r
        p.release.set()
        flush = lambda clock: p.ns["flush_prices"](flush_started=clock)
        join = p.ns["catalog_boundary"].join_stamps

        def change():
            p.ns["price_buffer"].update({1: 0.60, 2: 0.40})

        def price_committed_twice():
            return p.trace.count(("write", [1, 2])) == 2 and not p.ns["price_buffer"]

    try:
        assert await asyncio.wait_for(flush(1000), 1)
        await asyncio.wait_for(entered.wait(), 1)
        assert len(frames) == 1 and not release.is_set()
        price[0] = 0.60
        session.returned_rev = 43
        session._returned = {
            source: {"value": 0.60, "updated_at": "2026-10-11T00:52:32+00:00"}
        }
        change()
        assert await asyncio.wait_for(flush(1002), 0.25)
        await asyncio.wait_for(join(), 0.25)
        assert price_committed_twice()
        assert [frame["source_value"] for frame in frames] == [0.40, 0.60]
        assert [frame["rev"] for frame in frames] == [{"1": 42}, {"1": 43}]
        assert r.stats["stamped"] == 2 and not release.is_set()
    finally:
        release.set()
        await join()
        await r.drain_history()
        if source == "kalshi":
            p.ns["prices"].close()


@pytest.mark.asyncio
async def test_history_commit_failure_retries_quietly_with_original_scalar_point(
    monkeypatch,
):
    from contextlib import asynccontextmanager
    from app.tasks import live_blend_refresh as blend

    r, session, frames, _ = _ready_rig(monkeypatch)
    clock, opens, calls = [1000.0], [], []
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])

    @asynccontextmanager
    async def factory():
        if is_normal_recovery_owner(r):
            yield NormalRecoverySession()  # attempt151's recovery owner
            return
        opens.append(len(opens) + 1)
        number = len(opens)
        yield session
        if number == 2:
            raise RuntimeError("history outer COMMIT failed")

    async def chart(session, **kw):
        calls.append(kw)
        return object(), True

    # Counts this test's own opens: custody starts with no earlier rows.
    r._session_factory = r._chart_custody._transactional(factory)
    r._custody_backlog = False
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await r._history_task
    assert len(r._history) == r._history_count == 1
    assert r._last_snapshot_at == {} and r.stats["snapshots_written"] == 0
    assert r._history_reserved == {1: 1000}
    assert not r.pending_event_ids() and len(frames) == 1
    clock[0] += 2
    await r.refresh_pending(flush_started=1002)
    assert len(opens) == 2, "failed history retains the ordinary retry hold"
    clock[0] = 1000 + r.failed_retry_interval_s
    await r.refresh_pending(flush_started=clock[0])
    await r._history_task
    assert calls[0] == calls[1]
    assert calls[1]["observed_at"] == "2026-10-11T00:52:30+00:00"
    assert len(frames) == r.stats["stamped"] == r.stats["snapshots_written"] == 1
    assert r._last_snapshot_at == {1: 1000}
    assert not r._history and not r._history_count and not r._history_reserved


@pytest.mark.asyncio
async def test_cancelled_publication_keeps_committed_history(monkeypatch):
    r, session, frames, _ = _ready_rig(monkeypatch)
    entered, calls = asyncio.Event(), []

    async def publish(batch):
        frames.extend(batch)
        entered.set()
        await asyncio.Event().wait()

    async def chart(session, **kw):
        calls.append(kw)
        return object(), True

    r._publish = publish
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    task = asyncio.create_task(r.refresh([1], flush_started=1000))
    await asyncio.wait_for(entered.wait(), 1)
    assert len(r._history) == 1, "debt exists before the publication await"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await r.drain_history()
    assert len(calls) == 1 and r.stats["stamped"] == 1
    assert not r._history
    # Existing uncertain-publication cancellation policy keeps the quote owed.
    # The history owner drains without a second stamp or frame.
    assert r.pending_event_ids() == frozenset({1})
    assert len(frames) == 1


@pytest.mark.asyncio
async def test_full_backlog_publishes_next_stamp_at_once_and_keeps_every_due_point(
    monkeypatch,
):
    """#11138/#11181: past the ordinary backlog the next due stamp commits and
    publishes without waiting on the chart writer, and still owes its point at
    its own observation time; nothing queued drops."""
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    price[0] = 0.60
    session._returned = {
        "polymarket": {"value": 0.60, "updated_at": "2026-10-11T00:52:55+00:00"}
    }
    await asyncio.wait_for(r.refresh([1], flush_started=1025), 0.25)
    assert not release.is_set() and r._history_count == 2
    assert len(session.updates) == 2, "the stamp did not wait for chart room"
    assert [f["source_value"] for f in frames] == [0.40, 0.60]
    assert r.stats["history_deferred"] == 1 and len(r._history) == 2
    release.set()
    await r.drain_history()
    assert [c["home_win_probability"] for c in calls] == [0.40, 0.60]
    assert r._last_snapshot_at == {1: 1025}
    # The next due stamp owes its own point on the ordinary cadence.
    price[0] = 0.70
    session._returned = {
        "polymarket": {"value": 0.70, "updated_at": "2026-10-11T00:53:20+00:00"}
    }
    await r.refresh([1], flush_started=1050)
    await r.drain_history()
    assert [c["home_win_probability"] for c in calls] == [0.40, 0.60, 0.70]
    assert [c["observed_at"] for c in calls] == [
        "2026-10-11T00:52:30+00:00",
        "2026-10-11T00:52:55+00:00",
        "2026-10-11T00:53:20+00:00",
    ]
    assert [f["source_value"] for f in frames] == [0.40, 0.60, 0.70]
    assert not r._history and not r._history_count


@pytest.mark.asyncio
async def test_full_history_retains_final_changed_quote_without_a_future_tick(monkeypatch):
    """#11181 root countercase (attempt22-history-cap), kept as written: the
    venue goes quiet after a due quote that arrived past the ordinary backlog.
    No further input; its point lands at its original time."""
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    entered, release, calls = asyncio.Event(), asyncio.Event(), []
    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True
    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", chart)
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    price[0] = .60
    session._returned = {"polymarket": {"value": .60, "updated_at": "2026-10-11T00:52:55+00:00"}}
    try:
        await asyncio.wait_for(r.refresh([1], flush_started=1025), .25)
        assert [f["source_value"] for f in frames] == [.40,.60]
    finally:
        release.set()
        await r.drain_history()
    # No further venue input. Exercise ordinary empty/debt refresh and drain,
    # not a fabricated new quote or a weakening of the 25s eligibility floor.
    await r.refresh_pending(flush_started=1050)
    await r.drain_history()
    actual = [(c["home_win_probability"], c["observed_at"]) for c in calls]
    assert actual == [(.40,"2026-10-11T00:52:30+00:00"),(.60,"2026-10-11T00:52:55+00:00")], {
        "history": actual, "published": [f["source_value"] for f in frames],
        "pending": list(r.pending_event_ids()), "deferred": r.stats["history_deferred"],
    }


@pytest.mark.asyncio
async def test_long_held_writer_keeps_every_due_observation_at_its_own_time(
    monkeypatch,
):
    """#11181: through a long hold every due observation is owed, not only the
    last one, and each headline publishes at once. Growth is the ordinary
    25-second cadence: a quote inside it owes nothing, as with a free writer."""
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    quotes = [
        (1025, 0.60, "2026-10-11T00:52:55+00:00"),
        (1037, 0.65, "2026-10-11T00:53:07+00:00"),  # inside the cadence
        (1050, 0.70, "2026-10-11T00:53:20+00:00"),
        (1075, 0.80, "2026-10-11T00:53:45+00:00"),
    ]
    try:
        for at, value, observed in quotes:
            price[0] = value
            session._returned = {
                "polymarket": {"value": value, "updated_at": observed}
            }
            await asyncio.wait_for(r.refresh([1], flush_started=at), 0.25)
        assert [f["source_value"] for f in frames] == [0.40, 0.60, 0.65, 0.70, 0.80]
        assert not calls[1:], "the writer is still held"
        assert r._history_count == len(r._history) == 4
        assert r.stats["history_deferred"] == 3
    finally:
        release.set()
        await r.drain_history()
    # The venue goes quiet; an ordinary empty flush and drain only.
    await r.refresh_pending(flush_started=1100)
    await r.drain_history()
    assert [(c["home_win_probability"], c["observed_at"]) for c in calls] == [
        (0.40, "2026-10-11T00:52:30+00:00"),
        (0.60, "2026-10-11T00:52:55+00:00"),
        (0.70, "2026-10-11T00:53:20+00:00"),
        (0.80, "2026-10-11T00:53:45+00:00"),
    ]
    assert not r._history and not r._history_count and not r.pending_event_ids()


@pytest.mark.asyncio
async def test_past_the_memory_bound_stamp_never_waits_and_custody_keeps_the_point(
    monkeypatch,
):
    """#11181: past ordinary backlog + memory bound a due stamp still publishes
    at once, and its point is not dropped: it lives in its custody row alone,
    memory stays at its bound, and the writer pays it at its own observation
    time once memory has room, without another quote."""
    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    r._history_spill_limit = 0
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await _custody_read(r)
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    price[0] = 0.60
    session._returned = {
        "polymarket": {"value": 0.60, "updated_at": "2026-10-11T00:52:55+00:00"}
    }
    await asyncio.wait_for(r.refresh([1], flush_started=1025), 0.25)
    assert [f["source_value"] for f in frames] == [0.40, 0.60]
    assert r._history_count == len(r._history) == 1, "the memory bound holds"
    assert r.stats["history_custody_only"] == 1
    assert [row[2] for row in r._chart_custody.rows.values()] == [0.40, 0.60]
    release.set()
    await r.drain_history()
    await r.refresh_pending(flush_started=1030)  # venue quiet
    await r.drain_history()
    assert [(c["home_win_probability"], c["observed_at"]) for c in calls] == [
        (0.40, "2026-10-11T00:52:30+00:00"),
        (0.60, "2026-10-11T00:52:55+00:00"),
    ]
    assert not r._history and not r._history_count
    assert not r._chart_custody.rows, "every custody row settled with its point"
    assert r._last_snapshot_at == {1: 1025}


@pytest.mark.asyncio
async def test_cancelled_history_restores_slots_and_repeated_final_cancel_still_joins(
    monkeypatch,
):
    r, session, frames, _ = _ready_rig(monkeypatch)
    entered, release, calls = asyncio.Event(), asyncio.Event(), []

    async def chart(session, **kw):
        calls.append(kw)
        entered.set()
        await release.wait()
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    r._history_task.cancel()
    await asyncio.gather(r._history_task, return_exceptions=True)
    assert r._last_snapshot_at == {} and r._history_count == 1
    entered.clear()
    drain = asyncio.create_task(r.drain_history())
    await asyncio.wait_for(entered.wait(), 1)
    drain.cancel()
    await asyncio.sleep(0)
    drain.cancel()
    await asyncio.sleep(0)
    assert not drain.done() and not r._history_task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(drain, 1)
    assert r._history_task.done() and not r._history and not r._history_count
    assert r._last_snapshot_at == {1: 1000}
    assert r.stats["snapshots_written"] == 1 and len(frames) == 1
    assert calls[0] == calls[1]


@pytest.mark.asyncio
async def test_history_and_next_refresh_share_existing_three_session_ceiling(
    monkeypatch,
):
    from contextlib import asynccontextmanager
    from tests.test_single_event_commit_10090 import rig, settle_until

    x = rig(monkeypatch, count=4, block=True, blocked=(2, 3, 4))
    x.r._last_snapshot_at.clear()
    entered, release = asyncio.Event(), asyncio.Event()
    opened, maximum, factory = [0], [0], x.r._session_factory

    @asynccontextmanager
    async def counted():
        opened[0] += 1
        maximum[0] = max(maximum[0], opened[0])
        try:
            async with factory() as session:
                yield session
        finally:
            opened[0] -= 1

    async def chart(session, **kw):
        entered.set()
        await release.wait()
        return object(), True

    x.r._session_factory = counted
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await x.r.refresh([1], flush_started=1000)
    await asyncio.wait_for(entered.wait(), 1)
    next_refresh = asyncio.create_task(x.r.refresh([2, 3, 4], flush_started=1002))
    try:
        await settle_until(lambda: opened[0] == 3)
        # A session opening precedes its preview admission read. Wait for
        # the actual two blocked stamps, rather than counting loop turns.
        await settle_until(lambda: x.commands.count("update") == 3)
        assert maximum[0] == 3
        assert x.commands.count("update") == 3, "history plus only two next stamps"
        assert len(x.committed) == 1 and not next_refresh.done()
    finally:
        release.set()
        x.release.set()
        await next_refresh
        await x.r.drain_history()
    assert maximum[0] == 3 and opened[0] == 0
    assert sorted(x.committed) == [1, 2, 3, 4]
    assert not x.r._history and not x.r._history_count


@pytest.mark.asyncio
async def test_failed_full_history_still_publishes_stamp_then_pays_both_points(
    monkeypatch,
):
    """#11138/#11181: a failed chart writer past the ordinary backlog does not
    refuse the next due stamp. Both points keep their order and original
    times; the hold ends and both are paid without a second stamp or frame."""
    from app.tasks import live_blend_refresh as blend

    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    clock, failing, calls = [1000.0], [True], []
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])

    async def chart(session, **kw):
        calls.append(kw)
        if failing[0]:
            raise RuntimeError("history row unavailable")
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await r._history_task
    # Still inside the history retry hold. The later due observation neither
    # drops its predecessor nor waits; it owes its own point behind it.
    price[0] = 0.60
    session._returned = {
        "polymarket": {"value": 0.60, "updated_at": "2026-10-11T00:52:55+00:00"}
    }
    clock[0] = 1002
    await r.refresh([1], flush_started=1025)
    assert len(session.updates) == len(frames) == 2
    assert r._history_count == len(r._history) == 2
    assert r.stats["history_deferred"] == 1
    assert not r.pending_event_ids()
    assert not r._last_snapshot_at
    failing[0] = False
    clock[0] = 1030
    await r.drain_history()
    assert [c["home_win_probability"] for c in calls] == [0.40, 0.40, 0.60]
    assert [c["observed_at"] for c in calls] == [
        "2026-10-11T00:52:30+00:00",
        "2026-10-11T00:52:30+00:00",
        "2026-10-11T00:52:55+00:00",
    ]
    assert [f["source_value"] for f in frames] == [0.40, 0.60]
    assert not r.pending_event_ids() and not r._history_count


@pytest.mark.asyncio
async def test_failed_writer_past_the_memory_bound_still_publishes_and_keeps_both(
    monkeypatch,
):
    """A failed chart writer at the memory bound does not refuse the stamp
    (master did, before COMMIT). The queued point retries at its time and the
    one past the bound is kept in custody; no blend debt is created."""
    from app.tasks import live_blend_refresh as blend

    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    r._history_spill_limit = 0
    clock, failing, calls = [1000.0], [True], []
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])

    async def chart(session, **kw):
        calls.append(kw)
        if failing[0]:
            raise RuntimeError("history row unavailable")
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await _custody_read(r)
    await r.refresh([1], flush_started=1000)
    await r._history_task
    price[0] = 0.60
    session._returned = {
        "polymarket": {"value": 0.60, "updated_at": "2026-10-11T00:52:55+00:00"}
    }
    clock[0] = 1002
    await asyncio.wait_for(r.refresh([1], flush_started=1025), 0.25)
    assert len(session.updates) == len(frames) == 2
    assert r._history_count == len(r._history) == 1
    assert r.stats["history_custody_only"] == 1
    assert not r.pending_event_ids()
    failing[0] = False
    clock[0] = 1030
    await r.refresh_pending(flush_started=1030)
    await r.drain_history()
    assert [c["observed_at"] for c in calls] == [
        "2026-10-11T00:52:30+00:00",
        "2026-10-11T00:52:30+00:00",
        "2026-10-11T00:52:55+00:00",
    ]
    assert [f["source_value"] for f in frames] == [0.40, 0.60]
    assert not r.pending_event_ids() and not r._history_count
    assert not r._chart_custody.rows


@pytest.mark.asyncio
async def test_run_handoff_carries_points_owed_past_the_backlog(monkeypatch):
    """#11181 T6: a point owed past the ordinary backlog is the same scalar
    debt as any other, so a run hand-off carries it at its original time."""
    from app.tasks import live_blend_refresh as blend

    r, session, frames, price = _ready_rig(monkeypatch)
    r._history_limit = 1
    clock, failing, calls = [1000.0], [True], []
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])

    async def chart(session, **kw):
        calls.append(kw)
        if failing[0]:
            raise RuntimeError("retry on next run")
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await r._history_task
    price[0] = 0.60
    session._returned = {
        "polymarket": {"value": 0.60, "updated_at": "2026-10-11T00:52:55+00:00"}
    }
    clock[0] = 1002
    await r.refresh([1], flush_started=1025)
    assert r.stats["history_deferred"] == 1 and len(r._history) == 2
    if r._history_task is not None:
        await r._history_task
    assert blend.hand_off_pending(r) == 0, "history is not an owed blend stamp"
    assert not r._history and r._history_count == 0
    replacement, _, new_frames, _ = _ready_rig(monkeypatch)
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    failing[0] = False
    clock[0] = 1030
    assert blend.adopt_handed_off(replacement) == 0
    assert replacement._history_count == 2
    await replacement.refresh_pending(flush_started=1030)
    await replacement.drain_history()
    paid = [(c["home_win_probability"], c["observed_at"]) for c in calls[-2:]]
    assert paid == [
        (0.40, "2026-10-11T00:52:30+00:00"),
        (0.60, "2026-10-11T00:52:55+00:00"),
    ]
    assert not new_frames and not replacement._history_count


@pytest.mark.asyncio
async def test_committed_scalar_history_handoff_is_separate_from_stamp_ttl(monkeypatch):
    from app.tasks import live_blend_refresh as blend
    from dataclasses import FrozenInstanceError

    r, session, frames, _ = _ready_rig(monkeypatch)
    clock, calls, failing = [1000.0], [], [True]
    monkeypatch.setattr(blend, "_mono", lambda: clock[0])

    async def chart(session, **kw):
        calls.append(kw)
        if failing[0]:
            raise RuntimeError("retry on next run")
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    await r.refresh([1], flush_started=1000)
    await r._history_task
    with pytest.raises(FrozenInstanceError):
        r._history[0][2].home_probability = 0.99
    assert blend.hand_off_pending(r) == 0, "history is not an owed blend stamp"
    assert not r._history and r._history_count == 0
    clock[0] += blend.PENDING_HANDOFF_TTL_S + 1
    replacement, replacement_session, new_frames, _ = _ready_rig(monkeypatch)
    # _ready_rig installs a fresh helper, so restore the same failed point spy.
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    failing[0] = False
    assert blend.adopt_handed_off(replacement) == 0
    assert replacement._history_count == 1
    await replacement.refresh_pending(flush_started=clock[0])
    await replacement.drain_history()
    assert calls[0] == calls[1]
    assert calls[1]["observed_at"] == "2026-10-11T00:52:30+00:00"
    assert not new_frames and replacement.stats["stamped"] == 0
    assert replacement.stats["snapshots_written"] == 1
    assert not replacement._history_count


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_real_consumer_joins_history_before_engine_disposal_under_repeated_cancel(
    monkeypatch, source
):
    from app.tasks import live_blend_refresh as blend
    from tests.test_ws_consumer_session_lifetime_2471 import (
        _Rig,
        KALSHI_SLATE,
        POLY_SLATE,
        YES_TOKEN,
        _run_kalshi,
        _run_poly,
        _kalshi_tick,
        _poly_frame,
        _assert_one_lent_engine,
        _assert_disposed_once_after_last_session,
    )

    entered, release, owners = asyncio.Event(), asyncio.Event(), []
    initialise = blend.LiveBlendRefresher.__init__

    def with_committed_history(self, *args, **kwargs):
        initialise(self, *args, **kwargs)
        owners.append(self)
        ready = asyncio.Event()
        ready.set()
        self._history.append((900, 0.40, SimpleNamespace(), 1000, ready))
        self._history_count = 1
        self._start_history()

    async def quote(self, ids, now, **kwargs):
        pass

    async def history(self, owed, now, factory, *, verify_event=False):
        async with self._session_slot(), factory():
            entered.set()
            await release.wait()
        return True

    monkeypatch.setattr(blend.LiveBlendRefresher, "__init__", with_committed_history)
    monkeypatch.setattr(blend.LiveBlendRefresher, "_refresh_batch", quote)
    monkeypatch.setattr(blend.LiveBlendRefresher, "_write_owed_snapshots", history)
    _refuse_redis_without_a_socket(monkeypatch)
    if source == "kalshi":
        p = _Rig(KALSHI_SLATE)
        task = asyncio.create_task(
            _run_kalshi(monkeypatch, [_kalshi_tick("0.40", "0.44")], p, recycle=0.1)
        )
    else:
        p = _Rig(POLY_SLATE)
        task = asyncio.create_task(
            _run_poly(
                monkeypatch,
                [
                    _poly_frame(
                        "best_bid_ask", YES_TOKEN, best_bid="0.40", best_ask="0.44"
                    )
                ],
                p,
                recycle=0.1,
            )
        )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.sleep(0.15)
        assert not task.done() and p.open == 1
        assert p.engines[0].disposed == 0
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and p.engines[0].disposed == 0
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    _assert_one_lent_engine(p, source)
    _assert_disposed_once_after_last_session(p, source)
    assert owners[0]._history_task.done() and not owners[0]._history_count
