"""#10090 — queued non-live admitted events of one cohort share one stamp transaction.

Production 15:37–15:44Z 2026-10-29 (Kalshi worker-ws, v5950): the run's one
refresh was open 39–47 s of every minute, admitting each later flush's cohort
onto FRESH_STAMP_WORKERS session slots. About half of its ~300 attempts a
minute stamped nothing (`unobserved` + `no_reading`), and every attempt paid its
own session, read and COMMIT. `ADMITTED_STAMP_BATCH` (env, and the
`admitted_stamp_batch` speed switch) lets one worker turn take up to that many
queued events of the same cohort into one transaction, each in its own
savepoint. Today's value is 1: one event, one transaction, unchanged.

Bounds pinned here: a live game is never in a batch and never waits behind one
that formed while it was queued; queue order is kept; only one cohort (one
flush clock, one stored wall) shares a transaction; a failed batch leaves every
event owed exactly as a failed singleton does and switches the trial off.
"""

import asyncio
from contextlib import asynccontextmanager
from copy import copy

import pytest

import app.tasks.live_blend_refresh as lbr
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import OFF
from tests.test_admitted_debt_slots_10090 import _Gated, _finish, _running_call, _settle

BATCH = "admitted_stamp_batch"


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(lbr, "_mono", lambda: 1000.0)


class _Recorded(_Gated):
    """`_Gated`, keeping each `_refresh_batch` call's events as one group."""

    def __init__(self, blocked=()):
        super().__init__(blocked)
        self.groups: list[list[int]] = []

    async def _refresh_batch(self, event_ids, now, **kw):
        self.groups.append(list(event_ids))
        await super()._refresh_batch(event_ids, now, **kw)


def _own_groups(r):
    """The admitted groups, without the running call's own held stamp (99)."""
    return [group for group in r.groups if group != [99]]


@pytest.fixture
def batch_trial(monkeypatch):
    """An `admitted_stamp_batch` alternation whose current arm the test sets."""
    arm = {"value": 4, "tripped": [], "reads": 0}

    class _Trial:
        def value(self, name, default, at=None):
            if name != BATCH:
                return default
            arm["reads"] += 1
            return default if arm["tripped"] else arm["value"]

        def trip(self, name, error):
            arm["tripped"].append((name, error))

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(lbr, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(lbr, "ADMITTED_STAMP_BATCH", 1)
    return arm


# ── today: one event, one transaction ────────────────────────────────────────


async def test_todays_setting_stamps_each_admitted_event_alone():
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    assert r.admit_fresh(range(1, 7), flush_started=1001) == frozenset(range(1, 7))
    await _settle()
    assert _own_groups(r) == [[1], [2], [3], [4], [5], [6]]
    await _finish(r, task)


async def test_the_setting_is_one_by_default():
    assert lbr.ADMITTED_STAMP_BATCH == 1
    assert sw.today(BATCH) == 1


# ── a batch above one ────────────────────────────────────────────────────────


async def test_a_raised_batch_takes_the_queue_head_in_order(batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r.admit_fresh(range(1, 7), flush_started=1001)
    await _settle()
    # Three workers start; the first takes four, the second the rest.
    assert _own_groups(r) == [[1, 2, 3, 4], [5, 6]]
    assert r.finished == [1, 2, 3, 4, 5, 6]
    assert not r.pending_event_ids()
    await _finish(r, task)


async def test_a_live_game_is_never_batched_and_goes_first(batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11})
    r.admit_fresh([1, 2, 3, 10, 11], flush_started=1001)
    await _settle()
    assert _own_groups(r) == [[10], [11], [1, 2, 3]]
    await _finish(r, task)


async def test_a_non_live_head_taken_while_a_live_game_waits_is_stamped_alone(
        batch_trial, monkeypatch):
    # ADMITTED_LIVE_RUN lets a waiting non-live event go after N live stamps;
    # that turn must not hold a worker longer than today's.
    monkeypatch.setattr(lbr, "ADMITTED_LIVE_RUN", 1)
    monkeypatch.setattr(lbr, "FRESH_STAMP_WORKERS", 1)
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12})
    r.admit_fresh([1, 2, 3, 10, 11, 12], flush_started=1001)
    await _settle()
    assert _own_groups(r) == [[10], [1], [11], [2], [12], [3]]
    await _finish(r, task)


async def test_an_event_that_went_live_after_admission_ends_the_batch(batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r.admit_fresh([1, 2, 3, 4], flush_started=1001)
    r._live_event_ids.add(3)  # its latest read said live before a worker ran
    await _settle()
    assert _own_groups(r) == [[1, 2], [3], [4]]
    await _finish(r, task)


async def test_two_cohorts_never_share_a_transaction(batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r.admit_fresh([1, 2], flush_started=1001)
    r.admit_fresh([3, 4], flush_started=1002)
    await _settle()
    assert _own_groups(r) == [[1, 2], [3, 4]]
    await _finish(r, task)


async def test_the_arm_is_read_only_when_a_turn_could_batch(batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.add(10)
    r.admit_fresh([10], flush_started=1001)
    r.admit_fresh([1], flush_started=1002)
    await _settle()
    assert _own_groups(r) == [[10], [1]]
    assert batch_trial["reads"] == 0
    await _finish(r, task)


async def test_today_value_of_the_arm_batches_nothing(batch_trial):
    batch_trial["value"] = 1
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r.admit_fresh(range(1, 5), flush_started=1001)
    await _settle()
    assert _own_groups(r) == [[1], [2], [3], [4]]
    await _finish(r, task)


async def test_a_batch_admitted_beside_a_held_event_skips_only_that_event(batch_trial):
    # A fenced event is not admitted (the same-event fence is unchanged).
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    assert r.admit_fresh([99, 1, 2], flush_started=1001) == frozenset({1, 2})
    await _settle()
    assert _own_groups(r) == [[1, 2]]
    await _finish(r, task)


# ── failure: owed as a singleton's, trial off ────────────────────────────────


async def test_a_failed_batch_leaves_every_event_owed_and_switches_the_trial_off(
        batch_trial):
    r = _Recorded(blocked={99})
    real = r._refresh_batch
    failed = []

    async def batch(event_ids, now, **kw):
        if len(event_ids) > 1 and not failed:
            failed.append(list(event_ids))
            r.groups.append(list(event_ids))
            raise RuntimeError("batch failed")
        return await real(event_ids, now, **kw)

    r._refresh_batch = batch
    task = await _running_call(r)
    r.admit_fresh(range(1, 7), flush_started=1001)
    await _settle()
    assert failed == [[1, 2, 3, 4]]
    assert [name for name, _ in batch_trial["tripped"]] == [BATCH]
    assert {1, 2, 3, 4} <= r.pending_event_ids()
    # Held exactly as a failed singleton is: not due again at once.
    assert all(not r._due(eid, 1001) for eid in (1, 2, 3, 4))
    await _finish(r, task)
    # The rest of the trial in this process is today's one event per stamp.
    r2_groups = _own_groups(r)[1:]
    assert all(len(group) == 1 for group in r2_groups)


async def test_a_failed_singleton_under_todays_setting_trips_nothing(batch_trial):
    batch_trial["value"] = 1
    r = _Recorded(blocked={99})
    real = r._refresh_batch

    async def batch(event_ids, now, **kw):
        if event_ids == [1]:
            raise RuntimeError("stamp failed")
        return await real(event_ids, now, **kw)

    r._refresh_batch = batch
    task = await _running_call(r)
    r.admit_fresh(range(1, 4), flush_started=1001)
    await _settle()
    assert batch_trial["tripped"] == []
    assert 1 in r.pending_event_ids()
    await _finish(r, task)


async def test_a_batch_cancelled_mid_stamp_leaves_every_event_owed(batch_trial):
    r = _Recorded(blocked={99, 2})
    task = await _running_call(r)
    r.admit_fresh([1, 2, 3], flush_started=1001)
    await _settle()
    assert _own_groups(r) == [[1, 2, 3]]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert {1, 2, 3} <= r.pending_event_ids()
    # A cancellation is not a failure: no hold, due again at once.
    assert all(r._due(eid, 1001) for eid in (1, 2, 3))


# ── the switch's limits ──────────────────────────────────────────────────────


@pytest.mark.parametrize("mode, kwargs", [
    ("ab", {"half": 0}),                              # a worker constant has no per-game arm
    ("alternate", {"a": 2, "b": 4, "period_s": 60}),  # neither arm is today's
    ("alternate", {"a": 1, "b": 9, "period_s": 60}),  # above the bound
    ("alternate", {"a": 0, "b": 1, "period_s": 60}),
])
def test_a_batch_trial_outside_the_limits_is_refused(mode, kwargs):
    assert sw.validate(BATCH, mode, **kwargs) is not None


def test_a_batch_alternation_of_today_and_four_is_accepted():
    assert sw.validate(BATCH, "alternate", a=1, b=4, period_s=60) is None


def test_a_batch_alternation_keeps_the_workers_own_setting_on_one_arm(monkeypatch):
    monkeypatch.setattr(lbr, "ADMITTED_STAMP_BATCH", 2)
    assert sw.validate(BATCH, "alternate", a=1, b=4, period_s=60) is not None
    assert sw.validate(BATCH, "alternate", a=2, b=4, period_s=60) is None


def test_a_switch_read_error_reads_the_setting(monkeypatch):
    def broken():
        raise RuntimeError("switchboard down")

    monkeypatch.setattr(lbr, "_optional_db_trial", broken)
    monkeypatch.setattr(lbr, "ADMITTED_STAMP_BATCH", 1)
    assert lbr._admitted_stamp_batch() == 1


# ── the real stamp: one session, a savepoint each, one COMMIT ────────────────


def _rows(count, status="scheduled"):
    from tests.test_live_blend_refresh import _event_and_market

    event, market = _event_and_market()
    rows = []
    for event_id in range(1, count + 1):
        e, m = copy(event), copy(market)
        e.id = m.event_id = event_id
        e.status = status
        m.id = 10 * event_id
        rows.append((m, e))
    return rows


def _real_refresher(monkeypatch, count):
    from tests.test_live_blend_refresh import (
        NormalRecoverySession, _one_event_refresher, _RecordingSession,
        is_normal_recovery_owner,
    )

    session = _RecordingSession(_rows(count), [], {
        "polymarket": {"value": 0.9, "updated_at": "2026-10-29T15:40:00+00:00"},
    })
    session.returned_rev = 42
    r, _ = _one_event_refresher(monkeypatch, session)

    def unavailable_preview_client():
        raise ConnectionError("offline stamp control")

    monkeypatch.setattr(r, "_client", unavailable_preview_client)
    opened, committed, published = [], [], []

    @asynccontextmanager
    async def factory():
        if is_normal_recovery_owner(r):
            yield NormalRecoverySession()
            return
        opened.append(True)
        yield session
        committed.append(True)

    async def publish(frames):
        # Nothing reaches the wire before its transaction committed.
        assert committed
        published.extend(frame["event_id"] for frame in frames)

    r._session_factory = factory
    monkeypatch.setattr(r, "_publish", publish)
    r._last_snapshot_at = {event_id: 999.0 for event_id in range(1, count + 1)}
    return r, session, opened, committed, published


def _warm_orientation(r, count):
    """Each event's inversion verdict cached: no cold orientation read."""
    r._inversion.update({event_id: (1e9, False) for event_id in range(1, count + 1)})


def _logged(session):
    """Record the session's text statements and savepoint edges, in order."""
    log = []
    execute, begin_nested = session.execute, session.begin_nested

    async def logged_execute(statement, *args, **kwargs):
        if hasattr(statement, "text"):
            log.append(statement.text)
        return await execute(statement, *args, **kwargs)

    def logged_begin_nested():
        inner = begin_nested()

        class _Edge:
            async def __aenter__(self):
                log.append("SAVEPOINT")
                return await inner.__aenter__()

            async def __aexit__(self, *exc):
                log.append("ROLLBACK TO" if exc[0] else "RELEASE")
                return await inner.__aexit__(*exc)

        return _Edge()

    session.execute, session.begin_nested = logged_execute, logged_begin_nested
    return log


def _window(r, event_ids):
    window = lbr._FreshAdmission(1001.0, 1001.0, event_ids)
    window.clocks.update(dict.fromkeys(event_ids, 1001.0))
    window.admitted.update(event_ids)

    async def publish(frames):
        await r._publish(frames)

    window.publish = publish
    return window


async def test_a_real_batch_opens_one_session_and_stamps_each_event_in_a_savepoint(
        monkeypatch):
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 4)
    _warm_orientation(r, 4)
    window = _window(r, [1, 2, 3, 4])
    await r._stamp_admitted(window, [1, 2, 3, 4])
    await r.drain_history()
    assert len(opened) == 1 and len(committed) == 1
    assert len(session.updates) == 4 and r.stats["stamped"] == 4
    assert session.savepoints == ["release"] * 4
    assert sorted(published) == [1, 2, 3, 4]
    assert window.completed == {1, 2, 3, 4} and not window.failed
    assert window.holding == set()


async def test_todays_real_singletons_open_one_session_each(monkeypatch):
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 4)
    window = _window(r, [1, 2, 3, 4])
    for event_id in (1, 2, 3, 4):
        await r._stamp_admitted(window, [event_id])
    await r.drain_history()
    assert len(opened) == 4 and len(committed) == 4
    assert len(session.updates) == 4 and r.stats["stamped"] == 4
    # One event owns its transaction: no savepoint, as before.
    assert session.savepoints == []
    assert sorted(published) == [1, 2, 3, 4]


async def test_todays_real_singleton_cold_read_takes_no_savepoint_and_no_reset(
        monkeypatch):
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 2)
    log = _logged(session)
    window = _window(r, [1, 2])
    for event_id in (1, 2):
        await r._stamp_admitted(window, [event_id])
    assert session.savepoints == []
    assert not any("TO DEFAULT" in line for line in log)
    assert r.stats["stamped"] == 2


# ── a cold orientation read inside a batch (#11138, #837) ────────────────────


LOCK_ONLY = "SELECT set_config('lock_timeout', CAST(:ms AS text), true)"
STATEMENT_ONLY = "SELECT set_config('statement_timeout', CAST(:ms AS text), true)"
RESET = "SET LOCAL statement_timeout TO DEFAULT"


def _cold_reads(monkeypatch, log, fail=()):
    reads = []

    async def cold(session_, event_id, home_prob, source):
        reads.append(event_id)
        log.append(f"cold read {event_id}")
        if event_id in fail:
            raise RuntimeError("canceling statement due to statement timeout")
        return home_prob

    monkeypatch.setattr(
        "app.tasks.prediction_market_matching._check_and_fix_inversion", cold,
    )
    return reads


def _budget_and_edges(log):
    return [line for line in log if not line.startswith("SELECT ") or "set_config" in line]


async def test_a_batched_cold_read_runs_in_its_own_savepoint_without_the_stamp_bound(
        monkeypatch):
    # Without preview (each event read then stamped in turn), a sibling's stamp
    # has armed the whole-statement bound before the next event's cold
    # Event/OddsSnapshot reads: they go back to the resting statement timeout
    # with the lock budget alone, as in a one-event transaction, and the bound
    # is armed again for that event's UPDATE.
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 2)
    r.preview_events, r.preview = frozenset(), False
    log = _logged(session)
    reads = _cold_reads(monkeypatch, log)
    window = _window(r, [1, 2])
    await r._stamp_admitted(window, [1, 2])
    assert reads == [1, 2]
    assert _budget_and_edges(log) == [
        # event 1: lock budget, its cold read in a savepoint, then the bound
        LOCK_ONLY, "SAVEPOINT", "cold read 1", "RELEASE",
        STATEMENT_ONLY, "SAVEPOINT", "RELEASE",
        # event 2: the bound comes off before its cold read, back on for its stamp
        RESET, "SAVEPOINT", "cold read 2", "RELEASE",
        STATEMENT_ONLY, "SAVEPOINT", "RELEASE",
    ]
    assert r.stats["stamped"] == 2 and window.completed == {1, 2}


async def test_with_preview_every_batched_cold_read_precedes_the_first_bound(monkeypatch):
    # The preview arm computes every event before any UPDATE, so no read ever
    # follows an armed bound and nothing is reset.
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 2)
    assert r.preview
    log = _logged(session)
    _cold_reads(monkeypatch, log)
    window = _window(r, [1, 2])
    await r._stamp_admitted(window, [1, 2])
    assert _budget_and_edges(log) == [
        LOCK_ONLY, "SAVEPOINT", "cold read 1", "RELEASE",
        "SAVEPOINT", "cold read 2", "RELEASE",
        STATEMENT_ONLY, "SAVEPOINT", "RELEASE", "SAVEPOINT", "RELEASE",
    ]
    assert r.stats["stamped"] == 2


@pytest.mark.parametrize("preview", [True, False])
async def test_a_failed_batched_cold_read_rolls_back_only_its_own_savepoint(
        monkeypatch, preview):
    # In one shared transaction an unsavepointed failed read would abort it
    # and the siblings' stamps with it; here only event 2 is lost to this try.
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 3)
    if not preview:
        r.preview_events, r.preview = frozenset(), False
    _cold_reads(monkeypatch, [], fail={2})
    window = _window(r, [1, 2, 3])
    await r._stamp_admitted(window, [1, 2, 3])
    await r.drain_history()
    assert len(opened) == 1 and len(committed) == 1
    assert session.savepoints.count("rollback") == 1
    assert len(session.updates) == 2 and r.stats["stamped"] == 2
    assert sorted(published) == [1, 3]
    assert r._dispositions[2][:1] == ("error",)


async def test_a_failed_bound_reset_fails_the_whole_batch_before_commit(monkeypatch):
    # The reset is budget setup: like a failed lock-budget SET it fails the
    # batch whole (no COMMIT), so every event stays owed.
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_refresher(monkeypatch, 2)
    r.preview_events, r.preview = frozenset(), False
    _cold_reads(monkeypatch, [])
    execute = session.execute

    async def failing_reset(statement, *args, **kwargs):
        if "TO DEFAULT" in getattr(statement, "text", ""):
            raise RuntimeError("connection lost")
        return await execute(statement, *args, **kwargs)

    session.execute = failing_reset
    window = _window(r, [1, 2])
    await r._stamp_admitted(window, [1, 2])
    assert committed == []
    assert published == []
    assert window.failed == {1, 2} and not window.completed
    assert {1, 2} <= r.pending_event_ids()
