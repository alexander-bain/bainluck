"""#10090 — a running call's door stamps up to ADMITTED_DEBT_SLOTS owed events.

Production 2026-10-28 23:16:43.5Z (worker-ws v5939, Polymarket): 24 events were
held at one instant (origin=throttle, lock_retries=0). The 16 that had no later
input closed in strictly ascending event-id order, one at a time, over 4.4 s to
27.5 s — the order `admit_fresh` gives debt with no continuation. While a call
keeps admitting a busy slate no new `refresh` starts, so the per-flush attempt
count (`FRESH_FLUSH_PENDING_ATTEMPTS`, raised by R7) is never spent there; the
door's single debt slot is the whole drain. The slot count is a setting whose
default is today's one.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import app.tasks.live_blend_refresh as lbr

BACKEND = Path(__file__).resolve().parents[1]


class _Gated(lbr.LiveBlendRefresher):
    """Records each stamp; the events in ``blocked`` wait for ``release``."""

    def __init__(self, blocked=()):
        super().__init__("polymarket", min_refresh_interval_s=0)
        self.started: list[int] = []
        self.finished: list[int] = []
        self.blocked = set(blocked)
        self.release = asyncio.Event()

    async def _refresh_batch(
        self, event_ids, now, *, prepared=None, on_committed=None, publish_committed=None
    ):
        self.started.extend(event_ids)
        for event_id in event_ids:
            self._last_refresh_at[event_id] = now
        if self.blocked.intersection(event_ids):
            await self.release.wait()
        self.finished.extend(event_ids)
        if on_committed is not None:
            on_committed(event_ids)


async def _settle():
    for _ in range(50):
        await asyncio.sleep(0)


async def _running_call(r):
    """A call whose own stamp (event 99) is held, so its door stays open."""
    task = asyncio.create_task(r.refresh([99], flush_started=1000))
    await _settle()
    assert r.admitting() and r.started == [99]
    return task


async def _finish(r, task):
    r.release.set()
    await task
    assert r._admission is None


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(lbr, "_mono", lambda: 1000.0)


async def test_todays_door_takes_one_owed_event_per_admission_whatever_the_attempt_count(
    monkeypatch,
):
    # R7's raised attempt count: spent by a NEW refresh, never by the door.
    monkeypatch.setattr(lbr, "FRESH_FLUSH_PENDING_ATTEMPTS", 3)
    r = _Gated(blocked={99})
    task = await _running_call(r)
    r.adopt_pending(range(1, 7))
    assert r.admit_fresh((), flush_started=1001) == frozenset()
    await _settle()
    assert r.finished == [1]
    r.admit_fresh((), flush_started=1002)
    await _settle()
    assert r.finished == [1, 2]
    assert r.pending_event_ids() == frozenset({3, 4, 5, 6})
    await _finish(r, task)


async def test_raised_debt_slots_stamp_that_many_owed_events_per_admission(monkeypatch):
    monkeypatch.setattr(lbr, "ADMITTED_DEBT_SLOTS", 3, raising=False)
    r = _Gated(blocked={99})
    task = await _running_call(r)
    r.adopt_pending(range(1, 7))
    assert r.admit_fresh((), flush_started=1001) == frozenset()
    await _settle()
    # Same rotation order as one slot, three at a time.
    assert r.finished == [1, 2, 3]
    assert r.pending_event_ids() == frozenset({4, 5, 6})
    r.admit_fresh((), flush_started=1002)
    await _settle()
    assert r.finished == [1, 2, 3, 4, 5, 6]
    assert not r.pending_event_ids()
    await _finish(r, task)


async def test_debt_slots_bound_concurrent_owed_stamps_not_admissions(monkeypatch):
    monkeypatch.setattr(lbr, "ADMITTED_DEBT_SLOTS", 3, raising=False)
    r = _Gated(blocked={99, 1})
    task = await _running_call(r)
    r.adopt_pending(range(1, 9))
    r.admit_fresh((), flush_started=1001)
    await _settle()
    assert r.started == [99, 1, 2, 3] and r.finished == [2, 3]
    # Owed event 1 still holds a slot: two free, so two more, never a fourth.
    r.admit_fresh((), flush_started=1002)
    await _settle()
    assert r.started == [99, 1, 2, 3, 4, 5]
    assert r.pending_event_ids() == frozenset({6, 7, 8})
    assert r._admission.debts == {1}
    await _finish(r, task)
    assert sorted(r.finished) == [1, 2, 3, 4, 5, 99]


async def test_debt_slots_skip_a_held_or_unfinished_event_as_one_slot_does(monkeypatch):
    monkeypatch.setattr(lbr, "ADMITTED_DEBT_SLOTS", 3, raising=False)
    r = _Gated(blocked={99})
    task = await _running_call(r)
    r.adopt_pending([1, 2, 3, 4, 99])
    # 99 is still held by the call; 2 is still being written by its caller.
    r.admit_fresh((), flush_started=1001, defer_event_ids={2})
    await _settle()
    assert r.finished == [1, 3, 4]
    assert r.pending_event_ids() == frozenset({2, 99})
    await _finish(r, task)


def _imported_slots(raw):
    env = {k: v for k, v in os.environ.items() if k != "ADMITTED_DEBT_SLOTS"}
    if raw is not None:
        env["ADMITTED_DEBT_SLOTS"] = raw
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, app.tasks.live_blend_refresh as m; "
            "print(json.dumps(m.ADMITTED_DEBT_SLOTS))",
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1]), out.stderr


@pytest.mark.parametrize(
    "raw, expected",
    [(None, 1), ("", 1), ("two", 1), ("2", 2), ("3", 3), ("0", 1), ("9", 3)],
)
def test_slots_are_read_once_at_import_and_clamped_to_the_stamp_workers(raw, expected):
    slots, stderr = _imported_slots(raw)
    assert slots == expected and type(slots) is int
    if raw in ("two", "0", "9"):
        assert "ADMITTED_DEBT_SLOTS" in stderr


class _Slotted(_Gated):
    """Each stamp holds one of the run's three session slots, as the real
    `_refresh_batch` does, so the call's own held stamp (99) takes one."""

    async def _refresh_batch(
        self, event_ids, now, *, prepared=None, on_committed=None, publish_committed=None
    ):
        async with self._session_slot():
            await super()._refresh_batch(
                event_ids, now, prepared=prepared, on_committed=on_committed,
                publish_committed=publish_committed,
            )


@pytest.mark.parametrize("slots, started", [
    # Argon Rank 2: owed LIVE events ride their own allowance (not the one
    # debt slot), so with one slot too they queue behind the fresh cohort.
    (1, [99, 50, 1, 2]),
    (2, [99, 50, 1, 2]),
    (3, [99, 50, 1, 2]),
])
async def test_debt_queues_behind_the_cohort_that_let_it_in(monkeypatch, slots, started):
    # live review of 6a448ae0: owed live events with LOWER ids than a fresh live
    # cohort were queued ahead of it (one sorted list); with 2-3 slots and the
    # call's own stamp holding a session slot, the fresh price never started.
    monkeypatch.setattr(lbr, "ADMITTED_DEBT_SLOTS", slots, raising=False)
    r = _Slotted(blocked={99, 1, 2, 3})
    task = await _running_call(r)
    r._live_event_ids.update({1, 2, 3, 50})
    r.adopt_pending([1, 2, 3])
    assert r.admit_fresh([50], flush_started=1001) == frozenset({50})
    await _settle()
    assert r.started == started
    await _finish(r, task)
