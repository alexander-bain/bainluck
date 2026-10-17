"""Same-game progress under a real held history row; original chart chronology."""

import asyncio
import contextlib
import time
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


# #11138 / #10090 — a full chart backlog must not hold a fresh quote's stamp.
#
# Production v5763, 2026-10-17, event 15331223 (Kubka–Salkova): a Kalshi quote
# .375 reached the Mac at 13:01:22.274 and the held page at 28.163 (5.889 s),
# while Polymarket kept publishing (revisions 2394–2398 still blended the old
# Kalshi .270). Kalshi's own chart-point writer was blocked 5.364 s on a
# `win_prob_snapshots ... FOR UPDATE` for another event (14870017, ended
# 27.900); revision 2399 committed 134 ms later. Insert order of the arm's chart
# rows puts its queued points at 58–64 from 13:01:05 to 13:02:00 — the
# `HISTORY_POINT_LIMIT` (64) ceiling — and every late Kalshi case of the capture
# falls inside that plateau. At the ceiling a due stamp waited for the chart
# writer before its session opened, and three such stamps occupy every fresh
# worker, so an event owing no point waited behind them.
#
# This rig reproduces that on real Postgres at a limit of one: the head point's
# row is held by another transaction; three events owe a point; a fourth, the
# quoted one, owes none and is queued behind them; Polymarket stamps the same
# event meanwhile. Delivery is the refresher's publish seam after COMMIT, not a
# Redis, browser or phone receipt.

HELD = 5  # the chart head whose row another transaction holds
OWING = (1, 2, 3)  # due for a chart point; they occupy all three fresh workers
QUOTED = 4  # owes no point; queued behind them, as 15331223 was
PM_MARKET = 10
HOLD_S = 1.5
DEADLINE_S = 1.0


async def _arrange(rig):
    await seed(rig, 5)
    prior = datetime.now(timezone.utc) - timedelta(seconds=60)
    async with rig.maker() as session:
        for eid in range(1, 6):
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == eid)
                .values(
                    source="kalshi",
                    external_id=f"KXMLBGAME-26OCT1{eid}CHCMIA-CHC",
                )
            )
        await session.execute(update(FuturesOutcome).values(current_probability=0.27))
        session.add(
            FuturesMarket(
                id=PM_MARKET,
                source="polymarket",
                external_id="game-pm-4",
                sport_id=(await session.get(Event, QUOTED)).sport_id,
                event_id=QUOTED,
                name="Miami Marlins vs Chicago Cubs",
                status="open",
                category="game",
                market_type="duel",
            )
        )
        await session.flush()
        session.add(
            FuturesOutcome(
                id=PM_MARKET,
                market_id=PM_MARKET,
                external_id="home-pm-4",
                name="Chicago Cubs",
                current_probability=0.36,
                rank=1,
                last_updated=prior,
            )
        )
        session.add(
            WinProbSnapshot(
                event_id=HELD,
                source="kalshi",
                captured_at=prior,
                home_win_probability=0.30,
                away_win_probability=0.70,
                reading_count=1,
            )
        )
        await session.commit()


async def _quote(rig, outcome_id, value):
    async with rig.maker() as session:
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == outcome_id)
            .values(current_probability=value, last_updated=datetime.now(timezone.utc))
        )
        await session.commit()


@pytest.mark.parametrize("lock_ms", [500, 5000])
async def test_fresh_kalshi_quote_publishes_while_full_chart_backlog_head_is_held(
    rig, monkeypatch, lock_ms
):
    """`lock_ms=500` is the production budget: the held chart write times out
    and retries. `5000` is a chart write that keeps waiting inside its budget,
    as production's 5.364 s statement did under per-acquisition 500 ms."""
    await _arrange(rig)

    @contextlib.asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    kalshi = LiveBlendRefresher(
        "kalshi", session_factory=factory, stamp_lock_timeout_ms=lock_ms
    )
    pm = LiveBlendRefresher("polymarket", session_factory=factory)
    kalshi._history_limit = 1  # production: 64 owed, its head held
    frames, history_entered = [], asyncio.Event()

    def publisher(source):
        async def publish(batch):
            async with rig.maker() as observer:
                for frame in batch:
                    eid = int(next(iter(frame["rev"])))
                    event = await observer.get(Event, eid)
                    assert (
                        event.win_probability_sources[source]["value"]
                        == frame["source_value"]
                    ), "a frame is published only for the committed value"
                    frames.append((source, eid, frame["source_value"], time.monotonic()))

        return publish

    async def chart(*args, **kwargs):
        if kwargs.get("event_id") == HELD:
            history_entered.set()
        return await _create_or_update_win_prob_snapshot(*args, **kwargs)

    kalshi._publish, pm._publish = publisher("kalshi"), publisher("polymarket")
    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", chart
    )
    holder = rig.maker()
    await holder.execute(
        select(WinProbSnapshot).where(WinProbSnapshot.event_id == HELD).with_for_update()
    )
    released = False
    flush = None
    try:
        # The head point: committed, published, then held at its chart row.
        await asyncio.wait_for(kalshi.refresh([HELD], flush_started=1000), 1)
        await asyncio.wait_for(history_entered.wait(), 1)
        assert kalshi._history_count == kalshi._history_limit
        # QUOTED charted 1 s ago; OWING never charted, so each is due.
        kalshi._last_snapshot_at[QUOTED] = 1001
        await asyncio.wait_for(pm.refresh([QUOTED], flush_started=1001), 1)

        # The fresh Kalshi quote (.270 -> .375) while Polymarket continues.
        for eid in (*OWING, QUOTED):
            await _quote(rig, eid, 0.375)
        started = time.monotonic()
        flush = asyncio.create_task(
            kalshi.refresh([*OWING, QUOTED], flush_started=1002)
        )
        await asyncio.sleep(0.2)
        await _quote(rig, PM_MARKET, 0.385)
        await asyncio.wait_for(pm.refresh([QUOTED], flush_started=1003), DEADLINE_S)
        deadline = started + DEADLINE_S
        while time.monotonic() < deadline and not any(
            f[:3] == ("kalshi", QUOTED, 0.375) for f in frames
        ):
            await asyncio.sleep(0.02)
        late = [
            eid for eid in (*OWING, QUOTED)
            if not any(
                f[:3] == ("kalshi", eid, 0.375) and f[3] - started < DEADLINE_S
                for f in frames
            )
        ]
        pm_values = [f[2] for f in frames if f[0] == "polymarket"]
        assert pm_values == [0.36, 0.385], "Polymarket keeps publishing meanwhile"
        assert not late, (
            f"Kalshi .375 not published within {DEADLINE_S}s for {late}: the "
            "stamp waited on a full chart backlog whose head row is held"
        )
        # #11181: past the ordinary backlog each due stamp still owes its
        # point (none waited, none dropped), within the finite spill bound.
        assert kalshi.stats["history_deferred"] == len(OWING)
        assert kalshi._history_count <= kalshi._history_limit + len(OWING)
    finally:
        await holder.rollback()
        await holder.close()
        released = True
        if flush is not None:
            await asyncio.gather(flush, return_exceptions=True)
        await kalshi.drain_history()
        await pm.drain_history()
    assert released

    # The delayed source's latest state is the stamped one, and nothing is owed.
    async with rig.maker() as session:
        event = await session.get(Event, QUOTED)
        assert event.win_probability_sources["kalshi"]["value"] == 0.375
        assert event.win_probability_sources["polymarket"]["value"] == 0.385
    assert not kalshi.pending_event_ids() and not pm.pending_event_ids()

    # The held head point lands at its original stamp time once its row frees
    # (after a retry hold under the 500 ms budget).
    if lock_ms == 500:
        for eid in kalshi._history_retry_at:
            kalshi._history_retry_at[eid] = 0.0
        await kalshi.drain_history()
    head = [f for f in frames if f[:2] == ("kalshi", HELD)]
    assert len(head) == 1
    # #11181: each point owed past the backlog was paid by the drain at its own
    # observed value, with no further quote.
    async with rig.maker() as session:
        points = (
            await session.execute(
                select(WinProbSnapshot.event_id, WinProbSnapshot.home_win_probability)
                .where(WinProbSnapshot.source == "kalshi")
                .order_by(WinProbSnapshot.id)
            )
        ).all()
    charted = {eid for eid, _ in points}
    assert charted == {HELD, *OWING}, points
    assert [float(p) for eid, p in points if eid in OWING] == [0.375] * len(OWING)
    assert not kalshi._history and not kalshi._history_count
