"""#10090 — the idle bound: a quiet source's lower bound stays fresh.

SHIP: the first genuine observation after a quiet interval promptly advances
the held page's observation timestamp. Root's page maximum (run
20261021T111728): samples ran only after a phase committed, so the PM input at
venue 11:18:01.262 previewed the 11:17:59.866 sample left by its previous
phase. `HeldRowQuotes` now keeps one idle task per process that refreshes the
same sample while the owner's preview events receive inputs.

Unchanged semantics, pinned here: a bound is a sample that COMPLETED before the
input was accepted, frozen at `note_input`; a retry or later sample never
re-dates it; the existing timeout and backoff apply; one read at a time.
Virtual clock: `_now`/`_sleep` are swapped, so nothing here waits on wall time
except the one real 0.15 s timeout case.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import HeldRowQuotes

EV, OTHER = 7, 8


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    async def sleep(self, seconds):
        # Only the test driver moves time; a sleeper wakes once it passes.
        wake = self.t + seconds
        while self.t < wake:
            await asyncio.sleep(0)


class FakeDB:
    """`sessions` for `sample_database_clock`: counts reads and overlap."""

    def __init__(self, clock):
        self.clock = clock
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.gates: list = []  # per-call asyncio.Event, consumed in call order
        self.hold_exit: asyncio.Event | None = None  # session cleanup waits for it
        self.values: list = []  # per-call clock value; default 1000 + virtual t

    def __call__(self):
        return self._session()

    @asynccontextmanager
    async def _session(self):
        self.calls += 1
        gate = self.gates.pop(0) if self.gates else None
        value = self.values.pop(0) if self.values else None
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield SimpleNamespace(execute=lambda stmt: self._read(gate, value))
        finally:
            if self.hold_exit is not None:
                await self.hold_exit.wait()  # a slow session exit, even when cancelled
            self.active -= 1

    async def _read(self, gate, value):
        if gate is not None:
            await gate.wait()
        v = value if value is not None else 1000.0 + self.clock.t
        return SimpleNamespace(scalar_one=lambda: datetime.fromtimestamp(v, tz=timezone.utc))


def _held(clock, events=(EV,)):
    held = HeldRowQuotes()
    held._now = clock.now
    held._sleep = clock.sleep
    held.preview_events = lambda: frozenset(events)
    return held


_seq = iter(range(1, 10_000))


def _mark(event_id=EV, oid=101, p=0.46):
    return SimpleNamespace(outcome_id=oid, seq=next(_seq), probability=p, event_id=event_id)


async def _settle():
    for _ in range(8):
        await asyncio.sleep(0)


async def _run_until(clock, t, step=0.01):
    """Advance virtual time to `t` in small steps, letting every task run."""
    while clock.t < t - 1e-9:
        clock.t = min(t, clock.t + step)
        await _settle()


async def _phase(held, db, clock, at):
    """An input at `at`, then its phase's post-commit sample (the consumers' order)."""
    await _run_until(clock, at)
    mark = _mark()
    held.note_input(mark)
    await held.sample_database_clock(db)
    return mark


class TestIdleBound:
    async def test_the_first_input_after_a_quiet_spell_gets_a_fresh_bound(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)  # the consumer's startup sample
        await _phase(held, db, clock, 0.02)
        await _run_until(clock, 2.0)
        late = _mark()
        held.note_input(late)
        # Without the idle task the bound would be the 0.02 phase sample.
        assert held.bound_for(late) >= 1000.0 + 2.0 - HeldRowQuotes.IDLE_SAMPLE_S
        assert held.bound_for(late) <= 1000.0 + clock.t
        assert held.idle_samples >= 6
        held.close()

    async def test_an_accepted_input_is_never_redated_by_a_later_sample(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)  # the consumer's startup sample
        mark = await _phase(held, db, clock, 0.01)
        frozen = held.bound_for(mark)
        await _run_until(clock, 3.0)
        assert held.idle_samples > 0 and held._database_bound > frozen
        assert held.bound_for(mark) == frozen
        held.close()

    async def test_a_sample_in_flight_when_an_input_arrives_is_not_its_bound(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)
        old = held._database_bound
        gate = asyncio.Event()
        db.gates.append(gate)
        clock.t = 0.5
        reading = asyncio.create_task(held.sample_database_clock(db))
        await asyncio.sleep(0)
        assert db.active == 1
        mark = _mark()
        held.note_input(mark)  # accepted while the read is in flight
        gate.set()
        assert await reading is True
        assert held._database_bound > old
        assert held.bound_for(mark) == old
        after = _mark()
        held.note_input(after)
        assert held.bound_for(after) == held._database_bound
        held.close()


class TestNoDuplicateReads:
    async def test_no_idle_read_while_a_phase_read_is_in_flight(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)
        await _phase(held, db, clock, 0.01)
        await _run_until(clock, 1.0)
        gate = asyncio.Event()
        db.gates.append(gate)
        phase = asyncio.create_task(held.sample_database_clock(db))  # held in flight
        await _settle()
        calls = db.calls
        await _run_until(clock, 2.0)  # idle reads fall due meanwhile
        assert held.idle_skips > 0 and db.calls == calls and db.max_active == 1
        gate.set()
        assert await phase is True
        await _run_until(clock, 2.5)
        assert db.calls > calls  # the idle task resumes after the phase's read
        held.close()

    async def test_no_idle_read_while_inputs_are_owed_their_phase_samples(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)
        await _run_until(clock, 0.01)
        held.note_input(_mark())  # owed: no sample started after it
        await _run_until(clock, HeldRowQuotes.IDLE_PHASE_GRACE_S - 0.05)
        # Within the grace the idle task leaves the read to that phase.
        assert held.idle_samples == 0
        await held.sample_database_clock(db)  # that phase's post-commit sample
        # Busy source: every input's phase samples itself; the idle task adds nothing.
        for _ in range(40):
            await _phase(held, db, clock, clock.t + 0.1)
        assert held.idle_samples == 0
        held.close()

    async def test_an_older_idle_read_never_replaces_a_newer_phase_sample(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        idle_gate = asyncio.Event()
        db.gates.append(idle_gate)
        db.values.extend([1500.0, 2000.0])
        clock.t = 1.0
        idle = asyncio.create_task(held.sample_database_clock(db))  # starts first
        await asyncio.sleep(0)
        assert await held.sample_database_clock(db) is True  # the phase's, after commit
        assert held._database_bound == 2000.0
        idle_gate.set()
        assert await idle is True
        assert held._database_bound == 2000.0


class TestBoundsAndLifecycle:
    async def test_a_timeout_backs_off_and_the_idle_task_reads_nothing_meanwhile(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)
        await _phase(held, db, clock, 0.01)
        await _run_until(clock, 0.5)
        await held.sample_database_clock(db)  # fresh: no idle read is due at this instant
        # Virtual time stands still while the real 0.15 s timeout fires on the next read.
        db.gates.append(asyncio.Event())  # never set
        calls0 = db.calls
        assert await held.sample_database_clock(db) is False
        assert held.sample_failures == 1 and db.calls == calls0 + 1
        until = held._sample_backoff_until
        assert until == pytest.approx(clock.t + HeldRowQuotes.SAMPLE_RECOVERY_S)
        calls = db.calls
        held.note_input(_mark())
        await held.sample_database_clock(db)  # inside backoff: no read
        assert db.calls == calls
        await _run_until(clock, until - 0.01)
        assert db.calls == calls  # the idle task reads nothing in the window
        await _run_until(clock, until + 1.0)
        assert db.calls > calls  # resumes after the window
        held.close()

    async def test_the_sampler_stops_by_itself_restarts_on_input_and_close_cancels(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)
        await _phase(held, db, clock, 0.01)
        task = held._idle_task
        assert task is not None and not task.done()
        await _run_until(clock, HeldRowQuotes.IDLE_ACTIVE_S + 1, step=0.05)
        assert task.done() and not task.cancelled()
        stopped_at = db.calls
        await _run_until(clock, clock.t + 10)
        assert db.calls == stopped_at  # no reads once inputs stopped
        held.note_input(_mark())
        assert held._idle_task is not task and not held._idle_task.done()
        again = held._idle_task
        held.note_input(_mark())
        assert held._idle_task is again  # one task per process
        held.close()
        await asyncio.sleep(0)
        assert again.cancelled()

    async def test_no_preview_event_no_sampler(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock, events=())
        await held.sample_database_clock(db)
        await _phase(held, db, clock, 0.01)
        assert held._idle_task is None
        held2 = _held(clock, events=(EV,))
        await held2.sample_database_clock(db)
        held2.note_input(_mark(event_id=OTHER))
        assert held2._idle_task is None
        default = HeldRowQuotes()  # an owner that installs nothing
        await default.sample_database_clock(db)
        default.note_input(_mark())
        assert default._idle_task is None

    async def test_quiet_read_cost_is_bounded_and_one_at_a_time(self):
        clock = Clock()
        db = FakeDB(clock)
        held = _held(clock)
        await held.sample_database_clock(db)
        await _phase(held, db, clock, 0.01)
        calls = db.calls
        await _run_until(clock, 10.0)
        idle = db.calls - calls
        assert idle == held.idle_samples
        assert 10.0 / HeldRowQuotes.IDLE_SAMPLE_S - 6 <= idle <= 10.0 / HeldRowQuotes.IDLE_SAMPLE_S + 1
        assert db.max_active == 1
        held.close()


class TestOwnerWiring:
    def test_the_refresher_installs_its_current_preview_events(self, monkeypatch):
        from app.tasks.live_blend_refresh import LiveBlendRefresher
        from app.utils import blend_preview

        monkeypatch.delenv("LIVE_BLEND_PREVIEW_SOURCES", raising=False)
        monkeypatch.setenv(blend_preview.SOURCE_ENV, "kalshi")
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, str(EV))
        refresher = LiveBlendRefresher("kalshi")
        refresher.held_quotes = HeldRowQuotes()
        assert set(refresher.held_quotes.preview_events()) == {EV}
        off = LiveBlendRefresher("polymarket")  # not the preview source
        off.held_quotes = HeldRowQuotes()
        assert set(off.held_quotes.preview_events()) == set()
        monkeypatch.delenv(blend_preview.SOURCE_ENV)
        unset = LiveBlendRefresher("kalshi")  # default off
        unset.held_quotes = HeldRowQuotes()
        assert set(unset.held_quotes.preview_events()) == set()
        assert unset.held_quotes is not None and LiveBlendRefresher("kalshi").held_quotes is None


# ------------------------------------------------- lifecycle (812 review REVISE)


def _owner(monkeypatch, source="kalshi"):
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from app.utils import blend_preview

    monkeypatch.delenv("LIVE_BLEND_PREVIEW_SOURCES", raising=False)
    monkeypatch.setenv(blend_preview.SOURCE_ENV, source)
    monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, str(EV))
    return LiveBlendRefresher(source)


async def _active(owner, clock):
    """Install a HeldRowQuotes through the REAL setter and get its sampler running."""
    db = FakeDB(clock)
    held = HeldRowQuotes()
    held._now, held._sleep = clock.now, clock.sleep
    owner.held_quotes = held
    await held.sample_database_clock(db)  # the consumer's startup sample
    await _phase(held, db, clock, clock.t + 0.01)
    await _run_until(clock, clock.t + 1.0)
    assert held._idle_task is not None and not held._idle_task.done() and held.idle_samples > 0
    return held, db


class TestLifecycleWiring:
    async def test_replacing_held_quotes_closes_the_old_sampler_and_the_run_reaps_it(self, monkeypatch):
        from app.tasks.live_blend_refresh import reap_stopped_loops

        clock = Clock()
        owner = _owner(monkeypatch)
        old, old_db = await _active(owner, clock)
        task = old._idle_task
        new, _new_db = await _active(owner, clock)  # the reviewer's countercase: replacement
        assert old._closed and old._idle_task is None
        assert await reap_stopped_loops("kalshi", ()) == 0
        assert task.done()
        reads = old_db.calls
        old.note_input(_mark())  # the abandoned instance never restarts
        await _run_until(clock, clock.t + 5.0)
        assert old._idle_task is None and old_db.calls == reads
        assert not new._closed and not new._idle_task.done()  # the successor is untouched
        new.close()

    async def test_consumer_teardown_closes_and_joins_the_sampler(self, monkeypatch):
        from app.tasks.live_blend_refresh import hand_off_pending, reap_stopped_loops

        clock = Clock()
        owner = _owner(monkeypatch, "polymarket")
        held, db = await _active(owner, clock)
        task = held._idle_task
        # The consumers' teardown order: hand off, then reap the stopped loops.
        hand_off_pending(owner)
        assert held._closed
        assert await reap_stopped_loops("polymarket", ()) == 0
        assert task.done()
        reads = db.calls
        held.note_input(_mark())
        await _run_until(clock, clock.t + 5.0)
        assert held._idle_task is None and db.calls == reads

    async def test_a_read_in_flight_at_teardown_is_cancelled_and_publishes_nothing(self, monkeypatch):
        from app.tasks.live_blend_refresh import hand_off_pending, reap_stopped_loops

        clock = Clock()
        owner = _owner(monkeypatch)
        held, db = await _active(owner, clock)
        db.gates.append(asyncio.Event())  # the next idle read never answers
        before_calls, bound = db.calls, held._database_bound
        for _ in range(200):
            clock.t += 0.01
            await _settle()
            if db.calls > before_calls:
                break
        assert held._sampling == 1  # the idle read is in flight
        task = held._idle_task
        hand_off_pending(owner)
        assert await reap_stopped_loops("kalshi", ()) == 0
        assert task.cancelled() and held._sampling == 0
        assert held._database_bound == bound  # a cancelled read publishes nothing

    async def test_a_second_cancellation_during_teardown_leaves_no_sampler_running(self, monkeypatch):
        from app.tasks.live_blend_refresh import hand_off_pending, reap_stopped_loops

        clock = Clock()
        owner = _owner(monkeypatch)
        held, db = await _active(owner, clock)
        task = held._idle_task

        async def teardown():
            try:
                await asyncio.sleep(3600)  # stands in for the drain a cancellation lands on
            finally:
                hand_off_pending(owner)
                await reap_stopped_loops("kalshi", ())

        run = asyncio.create_task(teardown())
        await _settle()
        run.cancel()
        await _settle()
        run.cancel()  # a second cancellation lands on the reap's await
        with pytest.raises(asyncio.CancelledError):
            await run
        await _settle()
        assert task.done() and held._closed
        reads = db.calls
        await _run_until(clock, clock.t + 5.0)
        assert db.calls == reads

    def test_both_consumers_tear_down_through_hand_off_then_reap(self):
        """The lifecycle above rides wiring the consumers already have."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "app" / "tasks"
        for name in ("kalshi_ws.py", "polymarket_ws.py"):
            text = (root / name).read_text()
            hand_off = text.index("hand_off_pending(blend_refresher)")
            reap = text.index("await reap_stopped_loops(", hand_off)
            assert hand_off < reap, name


class TestReapUnderCancellation:
    """903 review: a cancellation on the reap while a sampler's session exit is pending."""

    async def _unwinding(self, monkeypatch):
        from app.tasks.live_blend_refresh import hand_off_pending

        clock = Clock()
        owner = _owner(monkeypatch)
        held, db = await _active(owner, clock)
        db.gates.append(asyncio.Event())  # the next idle read never answers
        db.hold_exit = asyncio.Event()  # and its session cleanup is held open
        calls = db.calls
        for _ in range(200):
            clock.t += 0.01
            await _settle()
            if db.calls > calls:
                break
        assert held._sampling == 1
        task = held._idle_task
        hand_off_pending(owner)  # teardown: close() cancels the in-flight read
        await _settle()
        assert not task.done()  # still unwinding its session exit
        return owner, held, db, task

    async def test_a_second_cancellation_waits_for_the_sampler_then_propagates(self, monkeypatch):
        from app.tasks import live_blend_refresh as lbr

        _owner_, held, db, task = await self._unwinding(monkeypatch)
        reaper = asyncio.create_task(lbr.reap_stopped_loops("kalshi", ()))
        await _settle()
        reaper.cancel()  # the second cancellation, while the join is pending
        await _settle()
        assert not reaper.done() and not task.done()
        assert task in lbr._closing_samplers.get("kalshi", ())  # still owned
        db.hold_exit.set()  # the session exit completes
        with pytest.raises(asyncio.CancelledError):
            await reaper  # re-raised only after the join
        assert task.done() and held._sampling == 0
        assert "kalshi" not in lbr._closing_samplers

    async def test_the_reap_budget_ends_the_wait_and_keeps_ownership(self, monkeypatch):
        from app.tasks import live_blend_refresh as lbr

        _owner_, held, db, task = await self._unwinding(monkeypatch)
        assert await lbr.reap_stopped_loops("kalshi", (), timeout_s=0.05) == 1
        assert not task.done() and task in lbr._closing_samplers["kalshi"]
        db.hold_exit.set()
        assert await lbr.reap_stopped_loops("kalshi", ()) == 0  # the next reap owns it
        assert task.done() and "kalshi" not in lbr._closing_samplers
