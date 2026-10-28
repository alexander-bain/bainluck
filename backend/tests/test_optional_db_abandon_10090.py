"""#10090 WORST bucket 1 — optional reads are abandoned at their deadline, not cancelled.

Production 2026-10-28 21:49–21:59Z: worker-ws cut its normal ACK settlement,
durable normal recovery and preview capacity reads off at their deadline by
cancelling the in-flight asyncpg execute (~225 in ten minutes). SQLAlchemy
handles that cancel as a disconnect and discards the pooled connection, so all
9–10 of worker-ws's Postgres backends were under 78 s old on a dyno up 90
minutes, and Kalshi's slowest flush spent up to 8.9 s in checkout and
connection setup. `LIVE_BLEND_ABANDON_OPTIONAL_DB=1` keeps the deadline and the
TimeoutError but lets the read finish on its own task. Off, nothing changes.
The observation preview read is PR #11700's and is untouched here. The
connection half is proven on real Postgres in
`tests/integration/test_optional_db_abandon_pg_10090.py`.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import pytest

from app.tasks import live_blend_refresh as lbr
from app.tasks.live_blend_refresh import (
    FRESH_STAMP_WORKERS,
    OPTIONAL_DB_ABANDON_ENV,
    LiveBlendRefresher,
)
from tests.test_live_blend_refresh import _Result

pytestmark = pytest.mark.asyncio


@pytest.fixture
def abandon(monkeypatch):
    monkeypatch.setenv(OPTIONAL_DB_ABANDON_ENV, "1")


def refresher():
    r = LiveBlendRefresher("polymarket")
    opened = []

    class Session:
        async def execute(self, statement, params=None):
            return _Result()

    @asynccontextmanager
    async def factory():
        opened.append(True)
        yield Session()

    r._session_factory = factory
    return r, opened


class Body:
    """A read that finishes when told to, recording how it ended."""

    def __init__(self, value="graph"):
        self.value = value
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.ended = None

    async def __call__(self):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.ended = "cancelled"
            raise
        self.ended = "finished"
        return self.value


@pytest.mark.parametrize("setting", [None, "", "0", "off"])
async def test_off_is_the_old_timeout_and_cancels_the_read(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    else:
        monkeypatch.setenv(OPTIONAL_DB_ABANDON_ENV, setting)
    r, _ = refresher()
    body = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, body)
    assert body.ended == "cancelled"
    assert r.optional_db_abandoned == 0 and not r._optional_db_running
    assert not r._optional_db_busy()


async def test_on_releases_the_caller_at_the_deadline_and_the_read_finishes(abandon):
    r, _ = refresher()
    body = Body()
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, body)
    assert loop.time() - started < .5
    # Not cancelled: still running, holding the optional share.
    assert body.ended is None and r._optional_db_busy()
    assert r.optional_db_abandoned == 1
    # Every kind's next opportunity passes without starting another read.
    for kind in ("normal_read", "normal_ack"):
        second = Body()
        with pytest.raises(TimeoutError):
            await r._optional_db(kind, .02, second)
        assert not second.started.is_set()
    body.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert body.ended == "finished"
    assert not r._optional_db_busy() and not r._optional_db_limits


async def test_on_returns_a_read_that_finishes_in_time_and_raises_its_error(abandon):
    r, _ = refresher()
    body = Body("rows")
    body.release.set()
    assert await r._optional_db("normal_read", .5, body) == "rows"

    async def broken():
        raise ValueError("query failed")

    with pytest.raises(ValueError):
        await r._optional_db("normal_read", .5, broken)
    assert r.optional_db_abandoned == 0 and not r._optional_db_running


async def test_on_a_cancelled_caller_cancels_and_joins_its_read(abandon):
    r, _ = refresher()
    body = Body()
    caller = asyncio.create_task(r._optional_db("normal_ack", 5, body))
    await body.started.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert body.ended == "cancelled"
    assert not r._optional_db_running


async def test_on_a_read_that_never_finishes_is_cancelled_at_the_limit(abandon, monkeypatch):
    monkeypatch.setattr(lbr, "OPTIONAL_DB_ABANDON_LIMIT_S", .1)
    r, _ = refresher()
    body = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, body)
    for _ in range(100):
        if body.ended:
            break
        await asyncio.sleep(.01)
    assert body.ended == "cancelled"
    assert not r._optional_db_busy() and not r._optional_db_limits


async def test_on_a_late_failure_is_retrieved_and_logged(abandon, caplog):
    r, _ = refresher()
    release = asyncio.Event()

    async def fails_late():
        await release.wait()
        raise ValueError("late")

    with pytest.raises(TimeoutError):
        await r._optional_db("normal_ack", .02, fails_late)
    with caplog.at_level(logging.WARNING, logger="app.tasks.live_blend_refresh"):
        release.set()
        for _ in range(5):
            await asyncio.sleep(0)
    assert "abandoned optional read failed" in caplog.text
    assert not r._optional_db_running


async def test_on_drain_history_cancels_and_joins_an_abandoned_read(abandon):
    r, _ = refresher()
    body = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, body)
    await r.drain_history()
    assert body.ended == "cancelled"
    assert not r._optional_db_running and not r._optional_db_limits


async def test_busy_recovery_read_opens_no_session(abandon):
    r, opened = refresher()
    held = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, held)
    r._normal_acked = {1: 5}
    await asyncio.wait_for(r._recover_normal_prices(), 1)
    assert not opened, "recovery opened a session while its last read was finishing"
    # The ACK is kept for the next opportunity, not dropped.
    assert r._normal_acked == {1: 5}
    held.release.set()
    await asyncio.sleep(0)


async def test_busy_ack_settlement_keeps_the_ack(abandon):
    r, opened = refresher()
    held = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_ack", .02, held)
    await r._settle_normal_recovery({(1, 7)})
    assert not opened
    assert r._normal_acked == {1: 7}
    held.release.set()
    await asyncio.sleep(0)


async def test_off_busy_checks_are_inert(monkeypatch):
    """Off, nothing is ever registered, so every busy check reads False."""
    monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    r, _ = refresher()
    assert r._session_slots._value == FRESH_STAMP_WORKERS
    assert not r._optional_db_busy()
    # PR #11700's detached observation reads count only with the switch on, so
    # off stays exactly what master (with or without #11700) does.
    r._detached_reads = {asyncio.get_running_loop().create_future()}
    assert not r._optional_db_busy()




# ── one optional share across every kind, composed with PR #11700 ────────────


class SlotBody(Body):
    """A read that holds a session slot, as every real optional read does."""

    def __init__(self, r):
        super().__init__()
        self.r = r

    async def __call__(self):
        async with self.r._session_slot():
            return await super().__call__()


async def _two_stamps_enter(r):
    """Two fresh stamps acquire session slots at once, without waiting."""
    async with asyncio.timeout(.1):
        async with r._session_slot(), r._session_slot():
            return True


async def _every_optional_kind_passes(r, opened):
    r._normal_acked = {}
    await r._settle_normal_recovery({(1, 7)})
    assert r._normal_acked == {1: 7}
    await asyncio.wait_for(r._recover_normal_prices(), 1)
    assert r._normal_acked == {1: 7}
    capacity = Body()
    with pytest.raises(TimeoutError):
        await r._optional_db_in_pass("preview_capacity", lambda gate: capacity())
    assert not capacity.started.is_set()
    assert not opened, "an optional kind opened a session while the share was taken"


async def test_on_one_abandoned_read_holds_the_whole_optional_share(abandon):
    """lane1b 2255Z: the optional kinds together leave two slots for fresh stamps."""
    r, opened = refresher()
    held = SlotBody(r)
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, held)
    assert held.ended is None
    assert r._session_slots._value == FRESH_STAMP_WORKERS - 1
    await _every_optional_kind_passes(r, opened)
    assert await _two_stamps_enter(r)
    assert r.optional_db_abandoned == 1
    held.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert r._session_slots._value == FRESH_STAMP_WORKERS and not r._optional_db_busy()


async def test_on_a_detached_observation_read_takes_the_optional_share(abandon):
    """Composed with PR #11700: its detached read counts against the same share."""
    r, opened = refresher()
    observation = SlotBody(r)
    task = asyncio.create_task(observation())
    r._detached_reads = {task}
    await observation.started.wait()
    assert r._optional_db_busy()
    await _every_optional_kind_passes(r, opened)
    assert await _two_stamps_enter(r)
    observation.release.set()
    await task
    assert not r._optional_db_busy()


async def test_on_a_read_reaching_its_deadline_after_the_share_was_taken_is_cancelled(abandon):
    """Two kinds time out together: the second costs its connection, as off does."""
    r, _ = refresher()
    first = SlotBody(r)
    caller = asyncio.create_task(r._optional_db("normal_ack", .2, first))
    await first.started.wait()
    later = SlotBody(r)
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_read", .02, later)
    assert later.ended is None and r.optional_db_abandoned == 1
    with pytest.raises(TimeoutError) as raised:
        await caller
    assert not isinstance(raised.value, lbr.OptionalDbAbandoned)
    assert first.ended == "cancelled" and r.optional_db_abandoned == 1
    assert r._session_slots._value == FRESH_STAMP_WORKERS - 1
    assert await _two_stamps_enter(r)
    later.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert r._session_slots._value == FRESH_STAMP_WORKERS


async def test_on_a_capacity_read_reaching_its_pass_deadline_after_the_share_was_taken_is_cancelled(
    abandon,
):
    r, _ = refresher()
    held = SlotBody(r)
    reading = SlotBody(r)

    async def body(gate):
        gate.reading = True
        return await reading()

    caller = asyncio.create_task(r._optional_db_in_pass("preview_capacity", body))
    await reading.started.wait()
    with pytest.raises(TimeoutError):
        await r._optional_db("normal_ack", .02, held)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert reading.ended == "cancelled" and r.optional_db_abandoned == 1
    assert await _two_stamps_enter(r)
    held.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert r._session_slots._value == FRESH_STAMP_WORKERS


# ── preview capacity maintenance: abandoned only while inside its read ───────


class _Row:
    def __init__(self, **values):
        self._mapping = values


class _HangingRead:
    """A capacity session whose first statement runs until released."""

    def __init__(self, row):
        self.row = row
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.ended = None
        self.closed = 0

    @asynccontextmanager
    async def factory(self):
        outer = self

        class Session:
            async def execute(self, statement, params=None):
                outer.started.set()
                try:
                    await outer.release.wait()
                except asyncio.CancelledError:
                    outer.ended = "cancelled"
                    raise
                outer.ended = "finished"

                class Result:
                    def first(self):
                        return outer.row

                return Result()

        try:
            yield Session()
        finally:
            self.closed += 1


@pytest.fixture
def capacity(monkeypatch):
    """A refresher whose policy retirement reads through `_HangingRead`."""
    from app.utils import blend_preview

    calls = {"retire_policy": [], "published": []}

    class Registry:
        def retire_policy(self, *args):
            calls["retire_policy"].append(args)
            return None

    monkeypatch.setattr(blend_preview, "registry", lambda: Registry())
    r = LiveBlendRefresher("kalshi")
    read = _HangingRead(_Row(id=1, preview_rev=3))
    r._session_factory = read.factory
    r._reservation_context_query = lambda ids: ids

    async def publish(frames, **_):
        calls["published"].append(frames)

    r._publish_previews = publish
    return r, read, calls


async def _retire_under_pass(r, budget_s=.05):
    """One policy retirement inside a pass budget, as `_maintain_preview_capacity` runs it."""
    async with asyncio.timeout(budget_s) as budget:
        await r._retire_policy_preview_event(1, 7, 0, budget.when())


@pytest.mark.parametrize("setting", [None, "0"])
async def test_capacity_off_the_pass_deadline_cancels_the_read(capacity, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    else:
        monkeypatch.setenv(OPTIONAL_DB_ABANDON_ENV, setting)
    r, read, calls = capacity
    with pytest.raises(TimeoutError):
        await _retire_under_pass(r)
    assert read.ended == "cancelled" and read.closed == 1
    assert r.optional_db_abandoned == 0 and not r._optional_db_running
    assert not r._session_slots.locked() and r._session_slots._value == FRESH_STAMP_WORKERS
    assert calls == {"retire_policy": [], "published": []}


async def test_capacity_off_a_completed_read_proceeds_as_today(capacity, monkeypatch):
    monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    r, read, calls = capacity
    read.release.set()
    await _retire_under_pass(r, 1)
    assert len(calls["retire_policy"]) == 1 and calls["published"] == [[]]


async def test_capacity_on_the_pass_ends_at_its_deadline_and_the_read_finishes_then_stops(
    capacity, abandon,
):
    r, read, calls = capacity
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await _retire_under_pass(r)
    assert loop.time() - started < .5
    # The read was not cancelled; it still holds its slot and the optional share.
    assert read.ended is None and r._optional_db_busy()
    assert r.optional_db_abandoned == 1
    assert r._session_slots._value == FRESH_STAMP_WORKERS - 1
    read.release.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert read.ended == "finished" and read.closed == 1
    # A read the pass outlived proves nothing: no retirement, no publication.
    assert calls == {"retire_policy": [], "published": []}
    assert not r._optional_db_busy() and not r._optional_db_limits
    assert r._session_slots._value == FRESH_STAMP_WORKERS


async def test_capacity_on_a_completed_read_proceeds_as_today(capacity, abandon):
    r, read, calls = capacity
    read.release.set()
    await _retire_under_pass(r, 1)
    assert len(calls["retire_policy"]) == 1 and calls["published"] == [[]]
    assert r.optional_db_abandoned == 0


async def test_capacity_on_a_deadline_after_the_read_still_cancels_the_redis_work(abandon):
    """Past `read_done()` the body is in Redis work: cancelled and joined."""
    r, _ = refresher()
    redis = Body()

    async def body(gate):
        gate.reading = True
        await asyncio.sleep(0)
        gate.read_done()
        return await redis()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(.05):
            await r._optional_db_in_pass("preview_capacity", body)
    assert redis.ended == "cancelled"
    assert r.optional_db_abandoned == 0 and not r._optional_db_running


async def test_capacity_on_every_caller_cancellation_reaches_the_body_with_its_message(abandon):
    """A shutdown then the pass timeout: the body sees both, as when it was inline."""
    r, _ = refresher()
    seen = []
    entered = asyncio.Event()

    async def body(gate):
        entered.set()  # past its read: Redis work, which is never abandoned
        while True:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError as exc:
                seen.append((exc.args, asyncio.current_task().cancelling()))
                if len(seen) == 2:
                    raise

    caller = asyncio.create_task(r._optional_db_in_pass("preview_capacity", body))
    await entered.wait()
    caller.cancel("shutdown-first")
    for _ in range(3):
        await asyncio.sleep(0)
    caller.cancel("pass-timeout")
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert seen == [(("shutdown-first",), 1), (("pass-timeout",), 2)]
    assert r.optional_db_abandoned == 0 and not r._optional_db_running


async def test_capacity_on_shutdown_cancels_a_read_in_flight(abandon):
    r, _ = refresher()
    read = Body()

    async def body(gate):
        gate.reading = True
        return await read()

    caller = asyncio.create_task(r._optional_db_in_pass("preview_capacity", body))
    await read.started.wait()
    r._preview_maintenance_closed = True
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert read.ended == "cancelled"
    assert r.optional_db_abandoned == 0 and not r._optional_db_running


async def test_capacity_on_no_pass_starts_while_its_read_finishes(abandon, monkeypatch):
    r, _ = refresher()
    r._owns_preview_maintenance = True
    r._preview_maintenance_after = 0.0
    held = Body()

    async def body(gate):
        gate.reading = True
        return await held()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(.02):
            await r._optional_db_in_pass("preview_capacity", body)
    started = []

    async def maintain():
        started.append(True)

    monkeypatch.setattr(r, "_maintain_preview_capacity", maintain)
    r._start_preview_maintenance()
    assert r._preview_maintenance_task is None and not started
    held.release.set()
    for _ in range(5):
        await asyncio.sleep(0)
    r._start_preview_maintenance()
    await r._preview_maintenance_task
    assert started == [True]


async def test_capacity_on_drain_cancels_an_abandoned_read(abandon):
    r, _ = refresher()
    held = Body()

    async def body(gate):
        gate.reading = True
        return await held()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(.02):
            await r._optional_db_in_pass("preview_capacity", body)
    await r.drain_history()
    assert held.ended == "cancelled"
    assert not r._optional_db_running and not r._optional_db_limits

