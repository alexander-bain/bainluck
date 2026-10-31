"""#10090 — queued LIVE admitted events of one cohort share one stamp transaction
(`ADMITTED_LIVE_BATCH`, speed switch `admitted_live_batch`; Fable's prototype).

Production 16:01-16:35Z 2026-10-31 (Polymarket worker-ws, v6005 `667df791`,
~180 live games on the Saturday slate): every PM minute line read
`stamp_tx` = `events` — one event per transaction — 600-740 transactions a
minute on three workers ~97% busy with ~250 attempts queued, so each live
game's turn came every ~15-20 s (`stamp_wait_reason` STAMPED
`admitted_age_s` p50 13-21 s). `_admitted_batch` batches non-live heads only,
and only while no live game waits, which on that slate is never. Today's value
is 1: one event, one transaction, unchanged.

Bounds pinned here (the control is RED on `667df791`, GREEN with the change):
a live batch is the picked live game plus the head live games of ITS cohort
only (one flush clock, one stored wall), in queue order; two cohorts never
share a transaction; a game no longer live ends the batch; the extra events
count against ADMITTED_LIVE_RUN as their own picks would, so a waiting pre-game
event keeps today's turn; a reader-held pick taken from the middle of the queue
is joined only by head events of its own cohort; a failed live batch leaves
every event owed exactly as a failed singleton does and trips the LIVE switch,
not the non-live one; with the setting at 1 the order is byte-identical to
today's; and the real transaction opens one session, one COMMIT, a savepoint
per event, every frame published after the COMMIT.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

import app.tasks.live_blend_refresh as lbr
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import OFF
from tests.test_admitted_debt_slots_10090 import _finish, _running_call, _settle
from tests.test_admitted_stamp_batch_10090 import (
    _Recorded, _own_groups, _rows, _warm_orientation, _window,
)

LIVE_BATCH = "admitted_live_batch"
NON_LIVE_BATCH = "admitted_stamp_batch"


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(lbr, "_mono", lambda: 1000.0)


@pytest.fixture
def live_batch_trial(monkeypatch):
    """An `admitted_live_batch` alternation whose current arm the test sets;
    the non-live batch stays at today's 1 unless the test says otherwise."""
    arm = {"value": 4, "non_live": 1, "tripped": [], "reads": 0}

    class _Trial:
        def value(self, name, default, at=None):
            if name == LIVE_BATCH:
                arm["reads"] += 1
                return default if arm["tripped"] else arm["value"]
            if name == NON_LIVE_BATCH:
                return arm["non_live"]
            return default

        def trip(self, name, error):
            arm["tripped"].append((name, error))

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(lbr, "_optional_db_trial", lambda: _Trial())
    # `raising=False`: on a sha without the setting the control below still
    # runs, and is RED on its assertion rather than on this fixture.
    monkeypatch.setattr(lbr, "ADMITTED_LIVE_BATCH", 1, raising=False)
    monkeypatch.setattr(lbr, "ADMITTED_STAMP_BATCH", 1)
    return arm


# ── the control: RED on 667df791, GREEN with the change ──────────────────────


async def test_live_games_of_one_cohort_at_the_head_share_one_transaction(live_batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12, 13, 14})
    assert r.admit_fresh([10, 11, 12, 13, 14], flush_started=1001) == frozenset(
        {10, 11, 12, 13, 14})
    await _settle()
    # Three workers start; the first takes four, the second the rest.
    assert _own_groups(r) == [[10, 11, 12, 13], [14]]
    assert sorted(r.finished) == [10, 11, 12, 13, 14]
    assert not r.pending_event_ids()
    await _finish(r, task)


async def test_todays_setting_stamps_each_live_event_alone(live_batch_trial):
    live_batch_trial["value"] = 1
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12, 13})
    r.admit_fresh([10, 11, 12, 13], flush_started=1001)
    await _settle()
    assert _own_groups(r) == [[10], [11], [12], [13]]
    await _finish(r, task)


def test_the_setting_is_one_by_default():
    assert lbr.ADMITTED_LIVE_BATCH == 1
    assert sw.today(LIVE_BATCH) == 1


async def test_two_live_cohorts_never_share_a_transaction(live_batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12, 13})
    r.admit_fresh([10, 11], flush_started=1001)
    r.admit_fresh([12, 13], flush_started=1002)
    await _settle()
    assert _own_groups(r) == [[10, 11], [12, 13]]
    await _finish(r, task)


async def test_a_game_no_longer_live_ends_the_live_batch(live_batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12, 13})
    r.admit_fresh([10, 11, 12, 13], flush_started=1001)
    r._live_event_ids.discard(12)  # its latest read said not live before a worker ran
    await _settle()
    # 12 is already in the live queue; it is stamped alone, never inside a live batch.
    assert _own_groups(r) == [[10, 11], [12], [13]]
    await _finish(r, task)


async def test_the_extra_events_count_against_the_live_run(live_batch_trial, monkeypatch):
    # Today (ADMITTED_LIVE_RUN=3, one worker): [10],[11],[12],[1],[13],[14],[15],[2].
    # With a live batch the pre-game event still goes after three live EVENTS
    # have started, never after three live TRANSACTIONS.
    monkeypatch.setattr(lbr, "FRESH_STAMP_WORKERS", 1)
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12, 13, 14, 15})
    r.admit_fresh([1, 2, 10, 11, 12, 13, 14, 15], flush_started=1001)
    await _settle()
    groups = _own_groups(r)
    assert groups[0] == [10, 11, 12]
    assert groups[1] == [1]
    assert groups[2] == [13, 14, 15]
    assert groups[3] == [2]
    await _finish(r, task)


@pytest.mark.parametrize("limit", [1, 4, 8])
async def test_a_waiting_pre_game_event_keeps_its_turn_at_every_setting(
        live_batch_trial, monkeypatch, limit):
    # Authority's probe P2 (R1 on db6cb107): one worker, 3 pre-game + 16 live
    # of one cohort. Without the live-run stop a batch overshoots the run:
    # [4,4,4] at 4 and [8,8,0] at 8 live events before each pre-game turn.
    live_batch_trial["value"] = limit
    monkeypatch.setattr(lbr, "FRESH_STAMP_WORKERS", 1)
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    live = list(range(10, 26))
    r._live_event_ids.update(live)
    r.admit_fresh([1, 2, 3] + live, flush_started=1001)
    await _settle()
    runs, n = [], 0
    for group in _own_groups(r):
        if group[0] < 10:
            runs.append(n)
            n = 0
        else:
            n += len(group)
    assert runs == [lbr.ADMITTED_LIVE_RUN] * 3
    await _finish(r, task)


async def test_a_held_pick_from_the_middle_is_joined_only_by_head_events_of_its_cohort(
        live_batch_trial):
    r = _Recorded(blocked={99})
    r.reader_held = lambda: frozenset({12})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12, 13, 14})
    r.admit_fresh([10, 11], flush_started=1001)
    r.admit_fresh([12, 13, 14], flush_started=1002)
    await _settle()
    # The held game goes first (held-first); its own cohort's head events (13, 14)
    # are a different admission from the queue head (10, 11), so it is stamped
    # alone, then 10+11 share one transaction, then 13+14.
    assert _own_groups(r) == [[12], [10, 11], [13, 14]]
    await _finish(r, task)


async def test_the_live_arm_is_read_only_when_a_live_turn_could_batch(live_batch_trial):
    r = _Recorded(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.add(10)
    r.admit_fresh([10], flush_started=1001)
    await _settle()
    r.admit_fresh([1], flush_started=1002)
    await _settle()
    assert _own_groups(r) == [[10], [1]]
    assert live_batch_trial["reads"] == 0
    await _finish(r, task)


# ── failure: owed as a singleton's, the LIVE trial off ───────────────────────


async def test_a_failed_live_batch_leaves_every_event_owed_and_trips_the_live_switch(
        live_batch_trial):
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
    r._live_event_ids.update(range(10, 16))
    r.admit_fresh(range(10, 16), flush_started=1001)
    await _settle()
    assert failed == [[10, 11, 12, 13]]
    assert [name for name, _ in live_batch_trial["tripped"]] == [LIVE_BATCH]
    assert {10, 11, 12, 13} <= r.pending_event_ids()
    # Held exactly as a failed singleton is: not due again at once.
    assert all(not r._due(eid, 1001) for eid in (10, 11, 12, 13))
    await _finish(r, task)
    # The rest of the trial in this process is today's one event per stamp.
    assert all(len(group) == 1 for group in _own_groups(r)[1:])


async def test_a_live_batch_cancelled_mid_stamp_leaves_every_event_owed(live_batch_trial):
    r = _Recorded(blocked={99, 11})
    task = await _running_call(r)
    r._live_event_ids.update({10, 11, 12})
    r.admit_fresh([10, 11, 12], flush_started=1001)
    await _settle()
    assert _own_groups(r) == [[10, 11, 12]]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert {10, 11, 12} <= r.pending_event_ids()
    # A cancellation is not a failure: no hold, due again at once.
    assert all(r._due(eid, 1001) for eid in (10, 11, 12))


# ── the switch's limits ──────────────────────────────────────────────────────


@pytest.mark.parametrize("mode, kwargs", [
    ("ab", {"half": 0}),
    ("alternate", {"a": 2, "b": 4, "period_s": 60}),
    ("alternate", {"a": 1, "b": 9, "period_s": 60}),
    ("alternate", {"a": 0, "b": 1, "period_s": 60}),
])
def test_a_live_batch_trial_outside_the_limits_is_refused(mode, kwargs):
    assert sw.validate(LIVE_BATCH, mode, **kwargs) is not None


def test_a_live_batch_alternation_of_today_and_four_is_accepted():
    assert sw.validate(LIVE_BATCH, "alternate", a=1, b=4, period_s=60) is None


def test_a_switch_read_error_reads_the_live_setting(monkeypatch):
    def broken():
        raise RuntimeError("switchboard down")

    monkeypatch.setattr(lbr, "_optional_db_trial", broken)
    monkeypatch.setattr(lbr, "ADMITTED_LIVE_BATCH", 1)
    assert lbr._admitted_live_batch_size() == 1


# ── the real stamp: one session, a savepoint each, one COMMIT, frames after it ─


def _real_live_refresher(monkeypatch, count):
    from tests.test_live_blend_refresh import (
        NormalRecoverySession, _one_event_refresher, _RecordingSession,
        is_normal_recovery_owner,
    )

    session = _RecordingSession(_rows(count, status="live"), [], {
        "polymarket": {"value": 0.9, "updated_at": "2026-10-31T16:00:00+00:00"},
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


async def test_a_real_live_batch_opens_one_session_and_stamps_each_event_in_a_savepoint(
        monkeypatch):
    monkeypatch.setattr(lbr.time, "monotonic", lambda: 1000.0)
    r, session, opened, committed, published = _real_live_refresher(monkeypatch, 4)
    _warm_orientation(r, 4)
    window = _window(r, [1, 2, 3, 4])
    await r._stamp_admitted(window, [1, 2, 3, 4], live_batch=True)
    await r.drain_history()
    assert len(opened) == 1 and len(committed) == 1
    assert len(session.updates) == 4 and r.stats["stamped"] == 4
    assert session.savepoints == ["release"] * 4
    assert sorted(published) == [1, 2, 3, 4]
    assert window.completed == {1, 2, 3, 4} and not window.failed
    assert window.holding == set()
    # The read said live: the refresher's live set follows it.
    assert {1, 2, 3, 4} <= r._live_event_ids
