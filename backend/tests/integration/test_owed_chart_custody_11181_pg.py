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
  overlapping on the same rows each write every point exactly once.
"""

import asyncio
import contextlib
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Event, FuturesOutcome, OwedChartPoint, WinProbSnapshot
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
    async with rig.maker() as session:
        return (
            await session.execute(select(OwedChartPoint).order_by(OwedChartPoint.id))
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
        assert (await session.execute(select(func.count(OwedChartPoint.id)))).scalar() == 0
