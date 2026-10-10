"""#8129: earlier completed groups release rows and publish stored probabilities.

Actual application reader/resolver/orientation/stamp/snapshot and PG revision
trigger. Delivery is an observer seam, not a Redis or browser receipt. Failure
injections occur before COMMIT; they do not cover ambiguous acknowledgments.
Each case owns a random schema on the explicitly supplied disposable database.

e0b52e11ed: every due event now commits in its own write transaction (the
groups of four this file was written against are gone), with three fresh
workers (6d8b493900/fe0aa54fbf: a queued fresh event rereads in its own
session) and old debt prepared once then stamped in order. Failures are keyed
to the EVENT whose transaction fails, not to a session attempt number, and the
invariants are asserted per event: a failed or cancelled transaction leaves
only its own event owed with its slots undone, every committed event stays
authoritative, and nothing is double counted. An event whose commit was
bookkept (written value, chart slot and receipt recorded) is never re-owed.
The one allowed overlap is the ambiguous sibling seam: a worker cancelled
after its COMMIT but before that synchronous bookkeeping leaves a committed,
unbookkept event owed, a redundant re-stamp bounded by the other workers.
"""

import asyncio
import contextlib
import contextvars
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event as sa_event, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Event,
    FuturesMarket,
    FuturesOutcome,
    OddsSnapshot,
    Sport,
    WinProbSnapshot,
)
from app.services.database import Base
from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


@pytest.fixture
async def rig():
    schema = "blend8129_" + uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "futures_markets",
            "futures_outcomes",
            "win_prob_snapshots",
            "odds_snapshots",
        )
    ]
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=wanted)
        yield SimpleNamespace(engine=engine, maker=maker)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed(rig, count=12, *, unproven=False):
    now = datetime.now(timezone.utc)
    async with rig.maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        for eid in range(1, count + 1):
            session.add(
                Event(
                    id=eid,
                    sport_id=sport.id,
                    home_team_name="Chicago Cubs",
                    away_team_name="Miami Marlins",
                    commence_time=now - timedelta(minutes=30),
                    status="live",
                    win_probability_sources={},
                    opening_home_probability=0.5,
                )
            )
            session.add(
                FuturesMarket(
                    id=eid,
                    source="polymarket",
                    external_id=f"game-{eid}",
                    sport_id=sport.id,
                    event_id=eid,
                    name=(
                        "Chicago Cubs vs Miami Marlins"
                        if unproven
                        else "Miami Marlins vs Chicago Cubs"
                    ),
                    status="open",
                    category="game",
                    market_type="duel",
                )
            )
        await session.flush()
        for eid in range(1, count + 1):
            session.add(
                FuturesOutcome(
                    id=eid,
                    market_id=eid,
                    external_id=f"home-{eid}",
                    name="Yes" if unproven else "Chicago Cubs",
                    current_probability=0.7,
                    rank=1,
                    last_updated=now,
                )
            )
        await session.commit()


#: The events of the stamp transaction the current task is running (set
#: around `_refresh_batch`); empty in the preparation read's session.
_STAMPING = contextvars.ContextVar("blend8129_stamping", default=())


def refresher(
    rig, *, fail_commit_event=None, cancel_commit_event=None, fail_prepare=None,
):
    calls = []
    r = None

    @contextlib.asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            attempt = len(calls) + 1
            calls.append(attempt)
            try:
                yield session
                if attempt == fail_prepare:
                    raise RuntimeError("preparation exit failure")
                stamping = _STAMPING.get()
                if fail_commit_event in stamping:
                    raise RuntimeError("before outer COMMIT")
                if cancel_commit_event in stamping:
                    # Its chart-point slot was taken inside this transaction.
                    r.slot_at_cancel.append(cancel_commit_event in r._last_snapshot_at)
                    raise asyncio.CancelledError()
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    r = LiveBlendRefresher(
        "polymarket", session_factory=factory, min_refresh_interval_s=0
    )
    r.slot_at_cancel = []
    real_batch = r._refresh_batch

    async def batch(event_ids, *args, **kwargs):
        token = _STAMPING.set(tuple(event_ids))
        try:
            return await real_batch(event_ids, *args, **kwargs)
        finally:
            _STAMPING.reset(token)

    r._refresh_batch = batch
    r.receipts = TailReceipts("polymarket")
    frames = []
    resolved = []
    original_resolve = r.receipts.resolve

    def resolve(*args):
        resolved.append(set(args[0]))
        return original_resolve(*args)

    r.receipts.resolve = resolve

    async def publish(batch):
        # Independent readback AFTER commit: frames never assert provisional DB
        # values, and receipt/cache facts must exist before delivery awaits.
        async with rig.maker() as observer:
            for frame in batch:
                eid = frame["event_id"]
                event = await observer.get(Event, eid)
                assert (
                    event.win_probability_sources["polymarket"]["value"]
                    == frame["source_value"]
                )
                assert event.win_probability_sources_rev == frame["rev"][str(eid)]
                assert eid in r._last_written_value
                frames.append(frame)

    r._publish = publish
    return r, frames, calls, resolved, publish


def stage(r, ids):
    r.receipts.stage(
        [r.receipts.note_input(eid, eid, 0.7, kind="changed") for eid in ids]
    )


async def committed_events(rig):
    """The events whose polymarket stamp the database actually kept."""
    async with rig.maker() as session:
        events = (await session.execute(select(Event))).scalars().all()
    return {e.id for e in events if "polymarket" in e.win_probability_sources}


async def cancelled_accounting(rig, r, *, owed_at_least):
    """A cancelled refresh: nothing uncommitted is lost, and a committed stamp
    is re-owed only from the ambiguous seam (a worker cancelled after its
    COMMIT but before its bookkeeping costs "one redundant re-stamp, never a
    lost one"; at most the other FRESH_STAMP_WORKERS - 1 workers can be in
    that window). A bookkept commit is past that seam and is never owed."""
    from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS

    kept = await committed_events(rig)
    async with rig.maker() as session:
        snapshots = set(
            (await session.execute(select(WinProbSnapshot.event_id))).scalars()
        )
    owed = set(r.pending_event_ids())
    assert set(range(1, 13)) - kept <= owed, "an uncommitted event was lost"
    assert owed_at_least <= owed
    written = set(r._last_written_value)
    # Before the size bound: a re-owed bookkept event also inflates
    # `redundant`, and which siblings sit in the seam depends on timing.
    assert not owed & written, f"bookkept event re-owed: {sorted(owed & written)}"
    redundant = owed & kept
    assert len(redundant) <= FRESH_STAMP_WORKERS - 1, redundant
    assert kept == snapshots  # each kept stamp kept its chart point with it
    assert written == set(r._last_snapshot_at) <= kept
    assert redundant == kept - written  # only the unbookkept commits overlap
    assert r.stats["stamped"] == len(r._last_written_value)
    return kept, redundant


async def accounting(rig, r, expected):
    async with rig.maker() as session:
        events = (await session.execute(select(Event))).scalars().all()
        kept = {e.id for e in events if "polymarket" in e.win_probability_sources}
        snapshots = set(
            (await session.execute(select(WinProbSnapshot.event_id))).scalars()
        )
    assert (
        kept
        == snapshots
        == set(r._last_written_value)
        == set(r._last_snapshot_at)
        == set(expected)
    )
    assert r.stats["stamped"] == len(expected)


@pytest.mark.parametrize("count", [1, 3, 4, 5, 12])
async def test_actual_due_count_selects_path(rig, count):
    await seed(rig, count)
    r, frames, calls, resolved, _ = refresher(rig)
    # Incoming count=1; admitted retries/deferred determine the path.
    r.adopt_pending(range(2, count + 1))
    stage(r, range(1, count + 1))
    await r.refresh([1])
    # One event owns its transaction (the singleton path). Otherwise the fresh
    # event stamps in its own session and the debt is prepared once, then each
    # debt event commits in its own transaction.
    assert len(calls) == (1 if count == 1 else 1 + 1 + (count - 1))
    assert [f["event_id"] for f in frames] == list(range(1, count + 1))
    assert set().union(*resolved) == set(range(1, count + 1))
    assert not r.pending_event_ids()
    await accounting(rig, r, range(1, count + 1))


@pytest.mark.parametrize("cancel", [False, True])
async def test_preparation_session_failure_preserves_staged_debt(rig, cancel):
    await seed(rig, 8)
    r, frames, calls, _, _ = refresher(rig, fail_prepare=1)
    r._lock_retry.add(3)
    stage(r, range(1, 9))
    if cancel:
        original = r._read_groups

        async def read(session, ids):
            await original(session, ids)
            raise asyncio.CancelledError()

        r._read_groups = read
        with pytest.raises(asyncio.CancelledError):
            await r.refresh(range(1, 9))
    else:
        await r.refresh(range(1, 9))
    assert r.pending_event_ids() == set(range(1, 9))
    assert r._lock_retry == {3} and 3 not in r._last_refresh_at
    assert r._due(3, 0)
    assert not frames and calls == [1]
    assert not r._last_written_value and not r._last_snapshot_at
    assert not hasattr(r, "_lab_groups")
    assert set(r.receipts._open) == set(range(1, 9))
    await accounting(rig, r, ())


async def test_group_outer_failure_rolls_back_only_current_group(rig):
    await seed(rig)
    r, frames, _, resolved, _ = refresher(rig, fail_commit_event=6)
    stage(r, range(1, 13))
    await r.refresh(range(1, 13))
    expected = set(range(1, 13)) - {6}
    assert {f["event_id"] for f in frames} == expected
    assert r.pending_event_ids() == {6}
    # Each committed event resolved its own receipt at its own commit.
    assert sorted(map(sorted, resolved)) == [[eid] for eid in sorted(expected)]
    assert set(r.receipts._open) == {6}
    assert r.receipts._open[6].commit_failures == 1
    await accounting(rig, r, expected)


async def test_partial_delivery_cancel_keeps_committed_group_authoritative(rig):
    await seed(rig)
    r, frames, calls, resolved, publish = refresher(rig)
    stage(r, range(1, 13))

    first = []

    async def partial(batch):
        # The first committed event's COMMIT and receipt have finished.
        # Deliver its frame, then cancel at an awaited transport seam.
        if not first:
            first.extend(f["event_id"] for f in batch)
            assert set(first) <= set().union(*resolved)
            await publish(batch[:1])
            raise asyncio.CancelledError()
        await publish(batch)

    r._publish = partial
    with pytest.raises(asyncio.CancelledError):
        await r.refresh(range(1, 13))
    kept, redundant = await cancelled_accounting(rig, r, owed_at_least=set())
    assert first and set(first) <= kept - redundant and len(kept) < 12
    assert [f["event_id"] for f in frames][:1] == first[:1]
    assert {f["event_id"] for f in frames} <= kept
    # The delivered event stays authoritative: delivery, not stamping, was
    # interrupted, so it is never turned into debt.
    assert not set(first) & r.pending_event_ids()
    assert set(first) <= r.receipts._live_events <= kept
    # Existing delivery contract has no replay buffer. Stamp completion is not
    # proof the remaining three frames arrived and cannot be turned into debt.


async def test_cancel_midgroup_restores_provisional_slots(rig):
    await seed(rig)
    # Event 6's transaction is cancelled at its COMMIT, after it took its
    # provisional chart-point slot (the per-event form of a group-mate's).
    r, frames, _, _, _ = refresher(rig, cancel_commit_event=6)
    stage(r, range(1, 13))
    with pytest.raises(asyncio.CancelledError):
        await r.refresh(range(1, 13))
    assert r.slot_at_cancel == [True], "the cancelled stamp held a slot"
    kept, _ = await cancelled_accounting(rig, r, owed_at_least={6})
    assert 6 not in kept
    # The cancelled transaction's provisional slot followed it out.
    assert 6 not in r._last_snapshot_at and 6 not in r._last_written_value
    assert {f["event_id"] for f in frames} <= kept


async def test_earlier_group_releases_rows_before_later_lock_timeout(rig):
    await seed(rig)
    r, frames, _, resolved, publish = refresher(rig)
    stage(r, range(1, 13))
    holder = await rig.engine.connect()
    transaction = await holder.begin()
    await holder.execute(text("UPDATE events SET home_score=42 WHERE id=6"))
    released = asyncio.Event()

    async def first_group(batch):
        await publish(batch)
        if batch and batch[0]["event_id"] == 1:
            assert {1} in resolved  # event 1's own commit has resolved
            async with rig.maker() as sibling:
                await sibling.execute(text("SET LOCAL lock_timeout='100ms'"))
                await sibling.execute(text("UPDATE events SET away_score=1 WHERE id=1"))
                await sibling.rollback()
            released.set()

    r._publish = first_group
    try:
        await asyncio.wait_for(r.refresh(range(1, 13)), 5)
        assert released.is_set()
        assert r.pending_event_ids() == {6}
        await accounting(rig, r, set(range(1, 13)) - {6})
    finally:
        await transaction.rollback()
        await holder.close()
    await r.refresh_pending()
    assert not r.pending_event_ids()
    await accounting(rig, r, range(1, 13))


async def test_stale_refusal_preserves_revision_and_snapshot_accounting(rig):
    await seed(rig, 8)
    r, frames, _, _, _ = refresher(rig)
    stage(r, range(1, 9))
    original = r._prepare_groups

    async def prepare(ids):
        result = await original(ids)
        later = datetime.now(timezone.utc) + timedelta(seconds=30)
        async with rig.maker() as sibling:
            await sibling.execute(
                update(Event)
                .where(Event.id == 6)
                .values(
                    win_probability_sources={
                        "polymarket": {
                            "value": 0.8,
                            "observed_value": 0.8,
                            "updated_at": later.isoformat(),
                            "observed_basis": {"6": later.timestamp()},
                        }
                    }
                )
            )
            await sibling.commit()
        return result

    r._prepare_groups = prepare
    await r.refresh(range(1, 9))
    assert r.stats["stale_readings_refused"] == 1
    assert 6 not in r._last_written_value and 6 not in r._last_snapshot_at
    assert {f["event_id"] for f in frames} == set(range(1, 9)) - {6}
    async with rig.maker() as session:
        e = await session.get(Event, 6)
        assert e.win_probability_sources["polymarket"]["value"] == 0.8
        assert e.win_probability_sources_rev == 1
        assert set(
            (await session.execute(select(WinProbSnapshot.event_id))).scalars()
        ) == set(range(1, 9)) - {6}


async def test_snapshot_helper_failure_does_not_undo_stamp(rig, monkeypatch):
    await seed(rig, 8)
    r, frames, _, _, _ = refresher(rig)
    from app.tasks import snapshots

    original = snapshots._create_or_update_win_prob_snapshot

    async def snapshot(session, **kw):
        if kw["event_id"] == 6:
            raise RuntimeError("snapshot helper failure")
        return await original(session, **kw)

    monkeypatch.setattr(snapshots, "_create_or_update_win_prob_snapshot", snapshot)
    await r.refresh(range(1, 9))
    assert r.stats["stamped"] == 8 and not r.pending_event_ids()
    assert len(frames) == 8 and set(r._last_snapshot_at) == set(range(1, 9))
    async with rig.maker() as session:
        assert set(
            (await session.execute(select(WinProbSnapshot.event_id))).scalars()
        ) == set(range(1, 9)) - {6}


async def test_real_cold_orientation_later_event_view_warm_price_and_named_override(
    rig,
):
    await seed(rig, 8, unproven=True)
    r, frames, _, _, _ = refresher(rig)
    orientation_reads = []
    # Per orienting transaction (its connection), not one shared flag: the
    # fresh workers orient concurrently (6d8b493900), so a single phase label
    # set and cleared by each would drop or misattribute a sibling's reads.
    orienting = {}

    @sa_event.listens_for(rig.engine.sync_engine, "before_cursor_execute")
    def observe(conn, cursor, statement, params, context, many):
        label = orienting.get(id(conn))
        if label and statement.lstrip().upper().startswith("SELECT"):
            orientation_reads.append((label, statement))

    def track_orientation(refresher, label):
        original_oriented = refresher._oriented

        async def oriented(session, *args, **kw):
            key = id((await session.connection()).sync_connection)
            orienting[key] = label
            try:
                return await original_oriented(session, *args, **kw)
            finally:
                orienting.pop(key, None)

        refresher._oriented = oriented

    track_orientation(r, "grouped")
    async with rig.maker() as session:
        # Real sportsbook fallback: raw .7 -> .3, with actual odds rows.
        session.add(
            OddsSnapshot(
                event_id=1,
                bookmaker="orientation-control",
                home_win_probability=0.3,
                away_win_probability=0.7,
                captured_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    # 4772b51e0b: the singleton now reads its cohort in one scalar statement,
    # so no Event sits in its session's identity map and a cold unproven
    # reading pays the Event point read as well as the real odds lookup, as
    # every grouped event below does. (673c6a3860's lock budget, installed
    # just before these fallback reads, is not a read and is not counted.)
    small, _, _, _, _ = refresher(rig)
    track_orientation(small, "baseline")
    await small.refresh([3])
    baseline_reads = [
        sql for label, sql in orientation_reads
        if label == "baseline" and ("FROM odds_snapshots" in sql or "FROM events" in sql)
    ]
    assert len(baseline_reads) == 2
    assert sum("FROM odds_snapshots" in sql for sql in baseline_reads) == 1
    async with rig.maker() as session:
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == 2)
            .values(current_probability=0.9)
        )
        await session.commit()
    original = r._prepare_groups

    async def prepare(ids):
        result = await original(ids)
        # Event2 has no sportsbook price. Its later Event view supplies two
        # unanimous peers; earlier prepared Event2 deliberately has none.
        # 4772b51e0b: the one-read view carries only this source's own entry.
        assert result[2][0].win_probability_sources == {"polymarket": None}
        async with rig.maker() as session:
            await session.execute(
                update(Event)
                .where(Event.id == 2)
                .values(
                    win_probability_sources={
                        "espn": {"value": 0.02},
                        "stat_model": {"value": 0.03},
                    }
                )
            )
            await session.commit()
        assert float(result[2][1][0].outcomes[0].current_probability) == 0.9
        return result

    r._prepare_groups = prepare
    await r.refresh(range(1, 9))
    assert r._last_written_value[1] == 0.3
    assert r._last_written_value[2] == 0.1
    assert r._inversion[1][1] is True and r._inversion[2][1] is True
    # Only point reads of Event and OddsSnapshot classify fallback cost, not
    # publication observer queries. Each cold unproven event adds both reads.
    grouped_reads = [
        sql for label, sql in orientation_reads
        if label == "grouped" and ("FROM odds_snapshots" in sql or "FROM events" in sql)
    ]
    assert len(grouped_reads) == 16
    assert sum("FROM odds_snapshots" in sql for sql in grouped_reads) == 8
    assert sum("FROM events" in sql for sql in grouped_reads) == 8
    # Warm boolean cache transforms the NEW input rather than pinning .3.
    async with rig.maker() as session:
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == 1)
            .values(current_probability=0.8, last_updated=datetime.now(timezone.utc))
        )
        await session.commit()
    before = len(orientation_reads)
    await r.refresh([1])
    assert r._last_written_value[1] == 0.2
    assert len(orientation_reads) == before
    # Named proof outranks the cached flip, even while the real book says .3.
    async with rig.maker() as session:
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == 1)
            .values(
                name="Chicago Cubs",
                current_probability=0.75,
                last_updated=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    await r.refresh([1])
    assert r._last_written_value[1] == 0.75 and 1 not in r._inversion
    assert [f["source_value"] for f in frames if f["event_id"] == 1] == [0.3, 0.2, 0.75]


def _reowe_on_cancel(r, event_ids):
    """Mutant: the cancel cleanup also re-owes events that were bookkept.

    Applied through the real `_refresh_failed` once the cancelled refresh
    unwinds, not inside its cleanup call: that call is skipped when nothing
    is left unfinished, which depends on how far the workers got (#10090)."""
    real_refresh = r.refresh

    async def refresh(*args, **kwargs):
        try:
            return await real_refresh(*args, **kwargs)
        except asyncio.CancelledError as exc:
            r._refresh_failed(
                set(event_ids), set(), 0.0, None, None, None, exc, hold=False
            )
            raise

    r.refresh = refresh


@pytest.mark.parametrize("mutant", [False, True], ids=["source", "reowe-bookkept"])
async def test_later_delivery_cancel_does_not_double_count_prior_failed_group(
    rig, mutant
):
    await seed(rig)
    r, _, _, resolved, publish = refresher(rig, fail_commit_event=6)
    stage(r, range(1, 13))
    if mutant:
        _reowe_on_cancel(r, {9})

    async def partial(batch):
        await publish(batch[:1])
        if batch and batch[0]["event_id"] == 9:
            # Cancel only once event 6's failed commit has been recorded.
            async with asyncio.timeout(5):
                while 6 not in r.receipts._open:
                    await asyncio.sleep(0.005)
            raise asyncio.CancelledError()

    r._publish = partial
    with pytest.raises(asyncio.CancelledError):
        await r.refresh(range(1, 13))
    if mutant:
        # Event 9 committed, was bookkept and delivered; owing it again is
        # not the ambiguous seam, so the accounting must refuse it.
        assert 9 in r._last_written_value and 9 in r.pending_event_ids()
        with pytest.raises(AssertionError, match=r"bookkept event re-owed: \[9\]"):
            await cancelled_accounting(rig, r, owed_at_least={6})
        return
    kept, redundant = await cancelled_accounting(rig, r, owed_at_least={6})
    assert 6 not in kept and 9 in kept
    assert set().union(*resolved) <= kept
    assert kept - redundant <= set().union(*resolved)
    assert r.receipts._open[6].commit_failures == 1  # not counted twice


async def test_delivery_exception_cannot_requeue_committed_group(rig):
    await seed(rig, 8)
    r, _, _, _, _ = refresher(rig)
    stage(r, range(1, 9))

    async def fail_delivery(batch):
        # The real publisher contains Exceptions. This defensive seam pins the
        # boundary even if a future publisher lets one escape after COMMIT.
        raise RuntimeError("delivery failed after commit")

    r._publish = fail_delivery
    await r.refresh(range(1, 9))
    assert not r.pending_event_ids()
    assert not r.receipts._open
    await accounting(rig, r, range(1, 9))
