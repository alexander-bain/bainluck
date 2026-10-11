"""Same-game progress under a real held history row; original chart chronology."""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.models.models import Event, FuturesMarket, FuturesOutcome, WinProbSnapshot
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.tasks.snapshots import _create_or_update_win_prob_snapshot
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig, seed

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_next_quote_commits_and_frames_while_real_old_chart_row_is_locked(
    rig, monkeypatch, source
):
    from app.tasks.kalshi_ws import _KalshiPriceOwner
    from app.tasks.polymarket_ws import _PMStampOwner

    await seed(rig, 1)
    prior = datetime.now(timezone.utc) - timedelta(seconds=60)
    async with rig.maker() as session:
        await session.execute(
            update(FuturesMarket).values(
                source=source,
                external_id=(
                    "KXMLBGAME-26OCT11CHCMIA-CHC" if source == "kalshi" else "game-1"
                ),
            )
        )
        await session.execute(update(FuturesOutcome).values(current_probability=0.40))
        session.add(
            WinProbSnapshot(
                event_id=1,
                source=source,
                captured_at=prior,
                home_win_probability=0.30,
                away_win_probability=0.70,
                reading_count=1,
            )
        )
        await session.commit()

    @contextlib.asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    # A known finite lock bound leaves ample room for the ordering control;
    # the default 500ms contract is separately pinned by the unit guards.
    r = LiveBlendRefresher(source, session_factory=factory, stamp_lock_timeout_ms=2000)
    frames, history_entered, history_finished = [], asyncio.Event(), asyncio.Event()

    async def publish(batch):
        async with rig.maker() as observer:
            event = await observer.get(Event, 1)
            for frame in batch:
                assert (
                    event.win_probability_sources[source]["value"]
                    == frame["source_value"]
                )
                assert event.win_probability_sources_rev == frame["rev"]["1"]
                frames.append(frame)

    async def chart(*args, **kwargs):
        history_entered.set()
        result = await _create_or_update_win_prob_snapshot(*args, **kwargs)
        history_finished.set()
        return result

    r._publish = publish
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    holder = rig.maker()
    await holder.execute(select(WinProbSnapshot).with_for_update())
    owner = _KalshiPriceOwner() if source == "kalshi" else _PMStampOwner(r)
    first = asyncio.create_task(r.refresh([1], flush_started=1000))
    if source == "kalshi":
        owner.stamping, owner.stamping_events, owner.stamping_fresh = first, {1}, {1}
        join = lambda: owner.join_stamp(r)
    else:
        owner.task, owner.events, owner.fresh = first, {1}, {1}
        join = owner.join
    try:
        await asyncio.wait_for(history_entered.wait(), 1)
        assert len(frames) == 1 and not history_finished.is_set()
        await asyncio.wait_for(join(), 0.5)
        async with rig.maker() as session:
            await session.execute(
                update(FuturesOutcome).values(
                    current_probability=0.60, last_updated=datetime.now(timezone.utc)
                )
            )
            await session.commit()
        await asyncio.wait_for(r.refresh([1], flush_started=1002), 0.5)
        assert [frame["source_value"] for frame in frames] == [0.40, 0.60]
        assert frames[1]["rev"]["1"] > frames[0]["rev"]["1"]
        assert not history_finished.is_set() and not r.pending_event_ids()
    finally:
        await holder.rollback()
        await holder.close()
        await asyncio.gather(first, return_exceptions=True)
        await r.drain_history()
    async with rig.maker() as session:
        points = (
            (
                await session.execute(
                    select(WinProbSnapshot).order_by(WinProbSnapshot.captured_at)
                )
            )
            .scalars()
            .all()
        )
    assert len(points) == 2 and float(points[-1].home_win_probability) == 0.40
    assert points[-1].captured_at == datetime.fromisoformat(frames[0]["updated_at"])
    assert not r._history and r.stats["snapshots_written"] == 1


async def test_delayed_point_stitches_before_real_newer_poll_without_rewriting_poll(
    rig,
):
    await seed(rig, 1)
    at = datetime.now(timezone.utc)
    async with rig.maker() as session:
        previous = WinProbSnapshot(
            event_id=1,
            source="polymarket",
            captured_at=at - timedelta(seconds=25),
            home_win_probability=0.30,
            away_win_probability=0.70,
            valid_until=at + timedelta(seconds=10),
            reading_count=1,
        )
        following = WinProbSnapshot(
            event_id=1,
            source="polymarket",
            captured_at=at + timedelta(seconds=10),
            home_win_probability=0.80,
            away_win_probability=0.20,
            valid_until=at + timedelta(seconds=20),
            reading_count=3,
        )
        session.add_all([previous, following])
        await session.commit()
    async with rig.maker() as session:
        snapshot, new = await _create_or_update_win_prob_snapshot(
            session, 1, "polymarket", 0.40, 0.60, observed_at=at
        )
        assert new
        session.add(snapshot)
        await session.commit()
    async with rig.maker() as session:
        points = (
            (
                await session.execute(
                    select(WinProbSnapshot).order_by(WinProbSnapshot.captured_at)
                )
            )
            .scalars()
            .all()
        )
    assert [float(p.home_win_probability) for p in points] == [0.30, 0.40, 0.80]
    assert points[0].valid_until == points[1].captured_at == at
    assert points[1].valid_until == points[2].captured_at == at + timedelta(seconds=10)
    assert (
        points[2].valid_until == at + timedelta(seconds=20)
        and points[2].reading_count == 3
    )


async def test_real_rollback_leaves_original_point_retriable_at_original_time(rig):
    await seed(rig, 1)
    at = datetime.now(timezone.utc)
    async with rig.maker() as session:
        snapshot, new = await _create_or_update_win_prob_snapshot(
            session, 1, "polymarket", 0.40, 0.60, observed_at=at
        )
        assert new
        session.add(snapshot)
        await session.flush()
        await session.rollback()
    async with rig.maker() as session:
        assert (await session.execute(select(WinProbSnapshot))).scalars().all() == []
        snapshot, new = await _create_or_update_win_prob_snapshot(
            session, 1, "polymarket", 0.40, 0.60, observed_at=at
        )
        assert new
        session.add(snapshot)
        await session.commit()
    async with rig.maker() as session:
        stored = (await session.execute(select(WinProbSnapshot))).scalar_one()
        assert stored.captured_at == at and stored.reading_count == 1


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_delayed_changed_point_preserves_newer_deduplicated_poll_tail(
    rig, monkeypatch, source
):
    from app.tasks import snapshots

    await seed(rig, 1)
    at = datetime(2026, 10, 11, 0, 52, tzinfo=timezone.utc)
    delayed_at = at + timedelta(seconds=10)
    polled_at = at + timedelta(seconds=20)

    class PollClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return polled_at

    monkeypatch.setattr(snapshots, "datetime", PollClock)
    async with rig.maker() as session:
        session.add(
            WinProbSnapshot(
                event_id=1,
                source=source,
                captured_at=at,
                home_win_probability=0.40,
                away_win_probability=0.60,
                game_state={"poll_type": "live_fast"},
                reading_count=1,
            )
        )
        await session.commit()
    # The ordinary poll really deduplicates into the t0 row: no t20 row yet.
    async with rig.maker() as session:
        poll, new = await _create_or_update_win_prob_snapshot(
            session,
            1,
            source,
            0.40,
            0.60,
            max_gap_seconds=60,
        )
        assert not new and poll.captured_at == at
        assert poll.valid_until == polled_at and poll.reading_count == 2
        await session.commit()

    # A failed delayed transaction must not partially move the later evidence.
    async with rig.maker() as session:
        delayed, new = await _create_or_update_win_prob_snapshot(
            session,
            1,
            source,
            0.60,
            0.40,
            observed_at=delayed_at,
        )
        assert new
        session.add(delayed)
        await session.flush()
        await session.rollback()
    async with rig.maker() as session:
        poll = (await session.execute(select(WinProbSnapshot))).scalar_one()
        assert poll.valid_until == polled_at and poll.reading_count == 2
        delayed, new = await _create_or_update_win_prob_snapshot(
            session,
            1,
            source,
            0.60,
            0.40,
            observed_at=delayed_at,
        )
        assert new
        session.add(delayed)
        await session.commit()
    async with rig.maker() as session:
        points = (
            (
                await session.execute(
                    select(WinProbSnapshot).order_by(WinProbSnapshot.captured_at)
                )
            )
            .scalars()
            .all()
        )
    assert [p.captured_at for p in points] == [at, delayed_at, polled_at]
    assert [float(p.home_win_probability) for p in points] == [0.40, 0.60, 0.40]
    assert [float(p.away_win_probability) for p in points] == [0.60, 0.40, 0.60]
    assert points[0].valid_until == delayed_at
    assert points[1].valid_until == points[2].captured_at == polled_at
    assert points[2].valid_until == polled_at
    assert points[2].game_state == {"poll_type": "live_fast"}
    assert sum(p.reading_count for p in points) == 3
