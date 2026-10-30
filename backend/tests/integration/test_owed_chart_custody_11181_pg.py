"""#11181 — durable custody of owed chart points, on real Postgres.

The actual refresher, reader, stamp, custody INSERT/DELETE and ordered chart
writer, against the real `owed_chart_points` table built from the model the
migration matches. Each case owns a random schema on the explicitly supplied
disposable database. Proven here, not in the unit rig:

* the atomic boundary: a committed stamp always has its row, and a stamp whose
  INSERT fails does not commit;
* the INSERT queues behind no chart-row lock and no other uncommitted INSERT,
  so the headline stays prompt while the chart writer is held;
* past the memory bound every owed point, the quiet final included, is paid
  at its own observation time once the hold ends;
* replay after a lost COMMIT acknowledgement, a restart, and two drains
  overlapping on the same rows each write every point exactly once;
* (#10090) the ordered writer's series lookups read one index entry, not the
  whole (event, source) series, so the writer keeps up with the stamps.
"""

import asyncio
import contextlib
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Event, FuturesMarket, FuturesOutcome, OwedChartPoint, WinProbSnapshot,
)
from app.services.database import Base
from app.tasks.live_blend_refresh import LiveBlendRefresher, OwedChartCustody
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, seed

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

TABLES = (
    "sports", "teams", "venues", "events", "futures_markets",
    "futures_outcomes", "win_prob_snapshots", "odds_snapshots",
    "owed_chart_points",
)


@pytest.fixture
async def rig():
    schema = "custody11181_" + uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[Base.metadata.tables[name] for name in TABLES],
            )
        yield SimpleNamespace(engine=engine, maker=maker)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _factory(rig, *, lose_ack=None):
    """The consumer's session factory. `lose_ack(session)` True: the COMMIT
    succeeds on the server and the client is told it failed."""

    @contextlib.asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
            if lose_ack is not None and lose_ack(session):
                raise ConnectionError("COMMIT acknowledgement lost")

    return factory


def _refresher(rig, **kwargs):
    r = LiveBlendRefresher(
        "polymarket",
        session_factory=kwargs.pop("factory", None) or _factory(rig),
        stamp_lock_timeout_ms=kwargs.pop("stamp_lock_timeout_ms", 300),
        failed_retry_interval_s=0.05,
        chart_custody=OwedChartCustody(),
        **kwargs,
    )
    frames = []

    async def publish(batch):
        frames.extend(batch)
        # As Redis does (#10090 attempt151): a positive PUBLISH reply per
        # frame acknowledges its revision, so the price intent is settled.
        return {
            (f["event_id"], f["rev"][str(f["event_id"])]) for f in batch
            if isinstance(f.get("rev"), dict)
            and type(f["rev"].get(str(f["event_id"]))) is int
        }

    r._publish = publish
    return r, frames


async def _seed_with_prior_point(rig):
    await seed(rig, 1)
    async with rig.maker() as session:
        session.add(
            WinProbSnapshot(
                event_id=1, source="polymarket",
                captured_at=datetime.now(timezone.utc) - timedelta(seconds=60),
                home_win_probability=0.30, away_win_probability=0.70,
                reading_count=1,
            )
        )
        await session.commit()


async def _quote(rig, value):
    async with rig.maker() as session:
        await session.execute(
            update(FuturesOutcome).values(
                current_probability=value, last_updated=datetime.now(timezone.utc)
            )
        )
        await session.commit()


async def _points(rig):
    async with rig.maker() as session:
        rows = (
            await session.execute(
                select(WinProbSnapshot)
                .where(WinProbSnapshot.source == "polymarket")
                .order_by(WinProbSnapshot.captured_at)
            )
        ).scalars().all()
    return [
        (float(p.home_win_probability), p.captured_at, p.reading_count) for p in rows
    ]


async def _owed(rig):
    """Chart custody only: the refresher's own source. Its price publication
    intents (`polymarket_price_publish`, #10090) are a different duty."""
    async with rig.maker() as session:
        return (
            await session.execute(
                select(OwedChartPoint)
                .where(OwedChartPoint.source == "polymarket")
                .order_by(OwedChartPoint.id)
            )
        ).scalars().all()


async def _drain(r, until=5.0):
    """Ordinary quiet flushes and drains until the debt is paid or `until`."""
    deadline = time.monotonic() + until
    while time.monotonic() < deadline:
        await r.refresh_pending(flush_started=time.monotonic() + 10_000)
        if r._history_task is not None:
            # Bounded: a drain that never finishes is a red, not a CI hang.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.shield(r._history_task),
                    max(0.01, deadline - time.monotonic()),
                )
        if not r._history and not r._custody_backlog:
            return
        await asyncio.sleep(0.06)
    if r._history_task is not None:
        r._history_task.cancel()
        await asyncio.gather(r._history_task, return_exceptions=True)
    raise AssertionError(("debt not paid", r._history, r._custody_backlog))


def _at(frame):
    return datetime.fromisoformat(frame["updated_at"])


async def test_a_committed_stamp_has_its_row_and_its_point_settles_it(rig):
    await _seed_with_prior_point(rig)
    r, frames = _refresher(rig)
    holder = rig.maker()
    await holder.execute(select(WinProbSnapshot).with_for_update())
    try:
        await asyncio.wait_for(r.refresh([1], flush_started=1000), 1)
        owed = await _owed(rig)
        assert len(frames) == 1 and len(owed) == 1, "row committed with the stamp"
        row = owed[0]
        assert (row.source, row.event_id, row.value) == ("polymarket", 1, 0.7)
        assert row.reading["observed_at"] == frames[0]["updated_at"], "verbatim time"
        async with rig.maker() as session:
            stored = (await session.get(Event, 1)).win_probability_sources
        assert stored["polymarket"]["updated_at"] == frames[0]["updated_at"]
    finally:
        await holder.rollback()
        await holder.close()
    await _drain(r)
    assert [(v, at) for v, at, _ in await _points(rig)][-1] == (0.7, _at(frames[0]))
    assert await _owed(rig) == []


async def test_a_stamp_whose_custody_insert_fails_does_not_commit(rig):
    """The atomic boundary: with the table gone the INSERT fails inside the
    stamp's own scope, and the stamp rolls back with it."""
    await _seed_with_prior_point(rig)
    async with rig.maker() as session:
        await session.execute(text("ALTER TABLE owed_chart_points RENAME TO parked"))
        await session.commit()
    r, frames = _refresher(rig)
    await r.refresh([1], flush_started=1000)
    async with rig.maker() as session:
        stored = (await session.get(Event, 1)).win_probability_sources
    assert "polymarket" not in (stored or {}), "the stamp did not commit"
    assert not frames and not r._last_written_value
    async with rig.maker() as session:
        await session.execute(text("ALTER TABLE parked RENAME TO owed_chart_points"))
        await session.commit()
    await r.refresh([1], flush_started=1030)
    await _drain(r)
    assert [f["source_value"] for f in frames] == [0.7]
    assert [(v, at) for v, at, _ in await _points(rig)][-1] == (0.7, _at(frames[0]))
    assert await _owed(rig) == []


async def test_held_writer_past_memory_bound_pays_every_point_and_the_quiet_final(
    rig,
):
    """Lane1's countercase on real rows: ordinary backlog 1, memory bound 2,
    the chart writer held on a real snapshot row lock while three quotes land
    25 s apart and the venue then goes quiet. Every headline commits promptly
    even with another session's uncommitted custody INSERT open; the third
    point lives in its row alone; all three are paid at their own times."""
    await _seed_with_prior_point(rig)
    r, frames = _refresher(rig)
    r._history_limit, r._history_spill_limit = 1, 1
    holder = rig.maker()
    await holder.execute(select(WinProbSnapshot).with_for_update())
    other = rig.maker()
    await other.execute(
        OwedChartPoint.__table__.insert().values(
            source="kalshi", event_id=99, value=0.5, reading={}
        )
    )
    took = []
    try:
        for at, value in ((1000, 0.40), (1025, 0.50), (1050, 0.60)):
            await _quote(rig, value)
            started = time.monotonic()
            await asyncio.wait_for(r.refresh([1], flush_started=at), 1)
            took.append(time.monotonic() - started)
        assert [f["source_value"] for f in frames] == [0.40, 0.50, 0.60]
        assert max(took) < 0.5, took
        assert len(r._history) <= 2 and r.stats["history_custody_only"] >= 1
        assert [row.value for row in await _owed(rig)] == [0.40, 0.50, 0.60]
    finally:
        await other.rollback()
        await other.close()
        await holder.rollback()
        await holder.close()
    await _drain(r)
    paid = [(v, at) for v, at, _ in await _points(rig)][1:]
    assert paid == [(f["source_value"], _at(f)) for f in frames]
    assert await _owed(rig) == []


async def test_a_lost_commit_acknowledgement_never_writes_a_point_twice(rig):
    """The chart transaction commits (point written, row deleted) and the
    client is told it failed: the retry finds the row settled."""
    await _seed_with_prior_point(rig)
    lost = []

    def lose_ack(session):
        if not lost and session.info.get("chart"):
            lost.append(True)
            return True
        return False

    r, frames = _refresher(rig, factory=_factory(rig, lose_ack=lose_ack))
    real = r._chart_custody.settle

    async def settle(session, custody_id):
        session.info["chart"] = True
        return await real(session, custody_id)

    r._chart_custody.settle = settle
    await r.refresh([1], flush_started=1000)
    await _drain(r)
    assert lost, "the acknowledgement was lost once"
    assert r.stats["history_already_paid"] == 1
    assert [(v, at, n) for v, at, n in await _points(rig)][1:] == [
        (0.7, _at(frames[0]), 1)
    ]
    assert await _owed(rig) == []


async def test_a_stamp_whose_commit_acknowledgement_is_lost_still_pays_its_point(
    rig,
):
    """The stamp's COMMIT stores the stamp and its custody row, and the client
    is told it failed: the refresher cannot know, so its next drain reads
    custody and pays the stored point once, at the stored observation time."""
    await _seed_with_prior_point(rig)
    lost = []

    def lose_ack(session):
        if not lost and session.info.get("stamp"):
            lost.append(True)
            return True
        return False

    r, frames = _refresher(rig, factory=_factory(rig, lose_ack=lose_ack))
    real = r._chart_custody.record

    async def record(session, *args):
        session.info["stamp"] = True
        return await real(session, *args)

    r._chart_custody.record = record
    await _custody_settled(r)
    await r.refresh([1], flush_started=1000)
    assert lost and not frames, "the client saw the stamp fail"
    async with rig.maker() as session:
        stored = (await session.get(Event, 1)).win_probability_sources["polymarket"]
    assert [row.value for row in await _owed(rig)] == [0.7]
    await _drain(r)
    paid = [(v, at, n) for v, at, n in await _points(rig)][1:]
    assert paid == [(0.7, datetime.fromisoformat(stored["updated_at"]), 1)]
    assert await _owed(rig) == []


@pytest.mark.parametrize("overlap", [False, True], ids=["read-first", "read-overlaps"])
async def test_a_lost_acknowledgement_during_an_empty_custody_read_still_pays(
    rig, overlap
):
    """CERT-4203: the run's first custody read returns no rows and has not yet
    finished when a stamp commits its custody row and loses the COMMIT
    acknowledgement. That read began before the row existed, so it must not
    conclude the table is drained: the next quiet drain pays the stored point
    at its own time. `read-first` is the control, the same loss after the read
    has finished."""
    await _seed_with_prior_point(rig)
    lost = []

    def lose_ack(session):
        if not lost and session.info.get("stamp"):
            lost.append(True)
            return True
        return False

    r, _ = _refresher(rig, factory=_factory(rig, lose_ack=lose_ack))
    real_record = r._chart_custody.record

    async def record(session, *args):
        session.info["stamp"] = True
        return await real_record(session, *args)

    r._chart_custody.record = record
    read_done, release = asyncio.Event(), asyncio.Event()
    real_load = r._chart_custody.load

    async def load(*args):
        rows = await real_load(*args)
        read_done.set()
        if overlap:
            await release.wait()
        return rows

    r._chart_custody.load = load
    await r.refresh_pending(flush_started=999)
    await asyncio.wait_for(read_done.wait(), 1)
    if not overlap:
        await r._history_task
    await r.refresh([1], flush_started=1000)
    assert lost, "the client saw the stamp fail"
    async with rig.maker() as session:
        stored = (await session.get(Event, 1)).win_probability_sources["polymarket"]
    assert [row.value for row in await _owed(rig)] == [0.7]
    release.set()
    await asyncio.wait_for(r._history_task, 1)
    r._chart_custody.load = real_load
    await _drain(r)
    paid = [(v, at, n) for v, at, n in await _points(rig)][1:]
    assert paid == [(0.7, datetime.fromisoformat(stored["updated_at"]), 1)]
    assert await _owed(rig) == []


async def _custody_settled(r):
    """The run's first custody read finishes before the case begins."""
    await _drain(r)
    assert not r._custody_backlog


async def test_a_restart_pays_the_dead_runs_rows_once_at_their_own_times(rig):
    """A run killed while its chart writer was held leaves its rows; a fresh
    refresher of the source, with no hand-off, starts by loading them."""
    await _seed_with_prior_point(rig)
    dead, frames = _refresher(rig)
    holder = rig.maker()
    await holder.execute(select(WinProbSnapshot).with_for_update())
    try:
        for at, value in ((1000, 0.40), (1025, 0.50)):
            await _quote(rig, value)
            await asyncio.wait_for(dead.refresh([1], flush_started=at), 1)
        if dead._history_task is not None:
            dead._history_task.cancel()  # killed: no drain, no hand-off
            await asyncio.gather(dead._history_task, return_exceptions=True)
    finally:
        await holder.rollback()
        await holder.close()
    assert [row.value for row in await _owed(rig)] == [0.40, 0.50]
    fresh, _ = _refresher(rig)
    await _drain(fresh)
    paid = [(v, at, n) for v, at, n in await _points(rig)][1:]
    assert paid == [(f["source_value"], _at(f), 1) for f in frames]
    assert await _owed(rig) == []


async def test_two_drains_overlapping_on_the_same_rows_pay_each_once(rig):
    """A restart's new process can load rows the old one is still paying:
    the DELETE in the chart transaction is the claim."""
    await _seed_with_prior_point(rig)
    dead, frames = _refresher(rig)
    holder = rig.maker()
    await holder.execute(select(WinProbSnapshot).with_for_update())
    try:
        for at, value in ((1000, 0.40), (1025, 0.50), (1050, 0.60)):
            await _quote(rig, value)
            await asyncio.wait_for(dead.refresh([1], flush_started=at), 1)
        if dead._history_task is not None:
            dead._history_task.cancel()
            await asyncio.gather(dead._history_task, return_exceptions=True)
    finally:
        await holder.rollback()
        await holder.close()
    first, _ = _refresher(rig, stamp_lock_timeout_ms=2000)
    second, _ = _refresher(rig, stamp_lock_timeout_ms=2000)
    await asyncio.gather(_drain(first), _drain(second))
    paid = [(v, at, n) for v, at, n in await _points(rig)][1:]
    assert paid == [(f["source_value"], _at(f), 1) for f in frames]
    assert (
        first.stats["snapshots_written"] + second.stats["snapshots_written"] == 3
    )
    assert await _owed(rig) == []
    async with rig.maker() as session:
        assert (await session.execute(
            select(func.count(OwedChartPoint.id))
            .where(OwedChartPoint.source == "polymarket")
        )).scalar() == 0


# ── #10090: a deleted event does not owe a chart write forever ───────────────


async def _dead_run_owes_two_events(rig):
    """Events 1 and 2, each with a prior point; a run killed while its chart
    writer was held leaves one custody row per event."""
    await seed(rig, 2)
    async with rig.maker() as session:
        for eid in (1, 2):
            session.add(WinProbSnapshot(
                event_id=eid, source="polymarket",
                captured_at=datetime.now(timezone.utc) - timedelta(seconds=60),
                home_win_probability=0.30, away_win_probability=0.70,
                reading_count=1,
            ))
        await session.commit()
    dead, frames = _refresher(rig)
    holder = rig.maker()
    await holder.execute(select(WinProbSnapshot).with_for_update())
    try:
        await asyncio.wait_for(dead.refresh([1, 2], flush_started=1000), 1)
        if dead._history_task is not None:
            dead._history_task.cancel()
            await asyncio.gather(dead._history_task, return_exceptions=True)
    finally:
        await holder.rollback()
        await holder.close()
    assert sorted(row.event_id for row in await _owed(rig)) == [1, 2]
    return {f["event_id"]: f for f in frames}


async def _delete_event(rig, eid):
    async with rig.maker() as session:
        await session.execute(delete(WinProbSnapshot).where(WinProbSnapshot.event_id == eid))
        await session.execute(delete(FuturesOutcome).where(FuturesOutcome.market_id == eid))
        await session.execute(delete(FuturesMarket).where(FuturesMarket.id == eid))
        await session.execute(delete(Event).where(Event.id == eid))
        await session.commit()


async def _event_points(rig, eid):
    async with rig.maker() as session:
        rows = (await session.execute(
            select(WinProbSnapshot.home_win_probability, WinProbSnapshot.captured_at)
            .where(WinProbSnapshot.event_id == eid)
            .order_by(WinProbSnapshot.captured_at)
        )).all()
    return [(float(v), at) for v, at in rows]


def _by_event(attempts):
    """Per event, in order: (verify_event, committed, still owed after). The two
    events' rows load in their commit order, which the dead run does not fix."""
    out = {}
    for eid, verify, ok, owed in attempts:
        out.setdefault(eid, []).append((verify, ok, eid in owed))
    return out


def _spy_attempts(r, rig):
    """(event, verify_event, committed, events still owed after) per attempt."""
    attempts = []
    real = r._write_owed_snapshots

    async def spy(owed, now, factory, **kwargs):
        ok = await real(owed, now, factory, **kwargs)
        attempts.append((
            owed[0][0], kwargs.get("verify_event", False), ok,
            sorted(row.event_id for row in await _owed(rig)),
        ))
        return ok

    r._write_owed_snapshots = spy
    return attempts


async def test_a_deleted_events_point_fails_once_on_the_real_fk_then_retires(rig, caplog):
    """The event row is deleted after its stamp committed the custody row. The
    fresh run's first attempt raises the REAL FK and keeps the row; its retry
    finds the row gone and retires the point. The sibling is paid throughout."""
    frames = await _dead_run_owes_two_events(rig)
    await _delete_event(rig, 1)
    fresh, _ = _refresher(rig)
    attempts = _spy_attempts(fresh, rig)
    await _drain(fresh)
    assert _by_event(attempts) == {
        1: [(False, False, True), (True, True, False)],
        2: [(False, True, False)],
    }
    assert "win_prob_snapshots_event_id_fkey" in caplog.text, "the real FK failed attempt 1"
    assert fresh.stats.get("history_event_gone", 0) == 1
    assert await _owed(rig) == []
    assert await _event_points(rig, 1) == []
    assert (await _event_points(rig, 2))[-1] == (0.7, _at(frames[2]))


async def test_a_present_events_failed_point_is_written_on_its_retry(rig):
    """Legitimate debt: attempt 1 times out on a held chart row of a PRESENT
    event; the retry looks the row up, finds it and writes normally."""
    frames = await _dead_run_owes_two_events(rig)
    fresh, _ = _refresher(rig)
    attempts = _spy_attempts(fresh, rig)
    holder = rig.maker()
    await holder.execute(
        select(WinProbSnapshot).where(WinProbSnapshot.event_id == 1).with_for_update()
    )
    try:
        await fresh.refresh_pending(flush_started=time.monotonic() + 10_000)
        await asyncio.wait_for(fresh._history_task, 5)
    finally:
        await holder.rollback()
        await holder.close()
    assert _by_event(attempts) == {1: [(False, False, True)], 2: [(False, True, False)]}
    await _drain(fresh)
    assert _by_event(attempts)[1][1:] == [(True, True, False)]
    assert fresh.stats.get("history_event_gone", 0) == 0
    assert (await _event_points(rig, 1))[-1] == (0.7, _at(frames[1]))
    assert await _owed(rig) == []


async def test_a_failed_commit_of_a_retirement_keeps_the_row_and_counts_nothing(rig):
    frames = await _dead_run_owes_two_events(rig)
    await _delete_event(rig, 1)
    failing = [True]

    @contextlib.asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            try:
                yield session
                if failing[0] and session.info.get("retire"):
                    failing[0] = False
                    raise ConnectionError("COMMIT failed before reaching the server")
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    fresh, _ = _refresher(rig, factory=factory)
    real = fresh._write_owed_snapshots

    async def marked(owed, now, factory_, **kwargs):
        @contextlib.asynccontextmanager
        async def tagged():
            async with factory_() as session:
                session.info["retire"] = kwargs.get("verify_event", False)
                yield session

        return await real(owed, now, tagged, **kwargs)

    fresh._write_owed_snapshots = marked
    attempts = _spy_attempts(fresh, rig)
    await _drain(fresh)
    assert not failing[0], "the retirement's COMMIT failed once"
    assert _by_event(attempts) == {
        1: [(False, False, True), (True, False, True), (True, True, False)],
        2: [(False, True, False)],
    }
    assert fresh.stats.get("history_event_gone", 0) == 1
    assert await _owed(rig) == []
    assert (await _event_points(rig, 2))[-1] == (0.7, _at(frames[2]))


# ── #10090: the chart writer's series lookups read one row, not the series ───
#
# Production 2026-10-30 ~21:04Z, `pg_stat_statements` over 21.8 s: the ordered
# writer's previous-row lookup (`captured_at <= $3 ORDER BY captured_at DESC
# LIMIT 1 FOR UPDATE`) took 237 ms per call, 226 ms of it disk reads (167
# blocks), and every other statement of the point's transaction took under
# 1 ms. The only index that leads with the event was `(event_id, source)`, so
# each lookup fetched the event's whole series from the heap and sorted it.
# One Polymarket chart point cost ~310 ms, the writer paid ~3.2 a second, the
# stamps owed about as many, and `owed_chart_points` held 17,1xx Polymarket
# rows: its live chart points landed ~95 minutes after their stamps.

LONG_SERIES = 3000
LATER_ROWS = 20000


def _rows_examined(plan) -> int:
    """Rows the plan's leaf scans produced or discarded, over all loops."""
    if "Plans" in plan:
        return sum(_rows_examined(child) for child in plan["Plans"])
    loops = plan.get("Actual Loops", 1)
    return loops * (
        plan.get("Actual Rows", 0)
        + plan.get("Rows Removed by Filter", 0)
        + plan.get("Rows Removed by Index Recheck", 0)
    )


async def _seed_long_series(rig):
    """Event 1: a pre-game Polymarket line, one point a minute for two days,
    last moved two hours ago. Since then the table kept growing on other
    events, so neither the event's rows nor the newest rows are a short scan."""
    await seed(rig, 3)
    last_move = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    async with rig.maker() as session:
        await session.execute(
            text(
                "INSERT INTO win_prob_snapshots (event_id, source, captured_at,"
                " home_win_probability, away_win_probability, reading_count)"
                " SELECT 1, 'polymarket', CAST(:at AS timestamptz) - make_interval(mins => g), 0.5, 0.5, 1"
                " FROM generate_series(0, CAST(:n AS integer) - 1) g"
            ),
            {"at": last_move, "n": LONG_SERIES},
        )
        await session.execute(
            text(
                "INSERT INTO win_prob_snapshots (event_id, source, captured_at,"
                " home_win_probability, away_win_probability, reading_count)"
                " SELECT 2 + g % 2, CASE WHEN g % 3 = 0 THEN 'kalshi' ELSE 'polymarket' END,"
                " CAST(:at AS timestamptz) + make_interval(secs => g * 0.25), 0.4, 0.6, 1"
                " FROM generate_series(1, CAST(:n AS integer)) g"
            ),
            {"at": last_move, "n": LATER_ROWS},
        )
        await session.execute(text("ANALYZE win_prob_snapshots"))
        await session.commit()
    return last_move


@contextlib.contextmanager
def _captured_series_lookups(rig):
    seen = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FROM win_prob_snapshots" in statement and "LIMIT" in statement:
            seen.append((statement, parameters))

    event.listen(rig.engine.sync_engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(rig.engine.sync_engine, "before_cursor_execute", capture)


async def _examined(rig, statement, parameters) -> int:
    async with rig.engine.connect() as conn:
        raw = (
            await conn.exec_driver_sql(
                "EXPLAIN (ANALYZE, FORMAT JSON) " + statement, parameters
            )
        ).scalar_one()
        await conn.rollback()
    plan = json.loads(raw) if isinstance(raw, str) else raw
    return _rows_examined(plan[0]["Plan"])


async def _write_capturing_lookups(rig, *, commit, **kwargs):
    """Run the real chart helper once; return its series lookups. Uncommitted
    (`commit=False`) the table is left exactly as seeded, so a lookup can be
    measured against the rows it actually faced."""
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    with _captured_series_lookups(rig) as seen:
        async with rig.maker() as session:
            point, is_new = await _create_or_update_win_prob_snapshot(
                session, event_id=1, source="polymarket",
                home_win_probability=0.55, away_win_probability=0.45,
                max_gap_seconds=60, **kwargs,
            )
            assert is_new
            if commit:
                session.add(point)
                await session.commit()
            else:
                await session.rollback()
    return seen


async def test_the_ordered_writers_previous_row_lookup_reads_one_row_not_the_series(rig):
    last_move = await _seed_long_series(rig)
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    seen = await _write_capturing_lookups(
        rig, commit=False, observed_at=observed_at,
        game_state={"poll_type": "ws_fast_lane"},
    )
    previous = [s for s in seen if "captured_at <=" in s[0]]
    following = [s for s in seen if "captured_at >" in s[0]]
    assert len(previous) == 1 and len(following) == 1, seen
    # The cost: one index entry per lookup. Without an index that ends in
    # captured_at behind (event_id, source), the cheapest plan still walks the
    # event's 3,000 rows (and sorts them) or the 20,000 newer rows of others.
    assert await _examined(rig, *previous[0]) <= 2
    assert await _examined(rig, *following[0]) <= 2

    # The write itself is unchanged: the two-hour-old point is closed at the
    # observation and the new point sits at its own time.
    await _write_capturing_lookups(
        rig, commit=True, observed_at=observed_at,
        game_state={"poll_type": "ws_fast_lane"},
    )
    async with rig.maker() as session:
        tail = (
            await session.execute(
                select(WinProbSnapshot.captured_at, WinProbSnapshot.valid_until)
                .where(WinProbSnapshot.event_id == 1)
                .order_by(WinProbSnapshot.captured_at.desc())
                .limit(2)
            )
        ).all()
    assert [tuple(r) for r in tail] == [(observed_at, None), (last_move, observed_at)]


async def test_the_polls_latest_row_lookup_reads_one_row_not_the_series(rig):
    """The same index serves the unordered (poll) path's newest-row read."""
    await _seed_long_series(rig)
    seen = await _write_capturing_lookups(
        rig, commit=False, game_state={"poll_type": "live_fast"},
    )
    assert len(seen) == 1, seen
    assert await _examined(rig, *seen[0]) <= 2
