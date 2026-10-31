"""#10090 — the queued attempts a PM catalog handover sheds are the next call's
FRESH population when `handover_fresh` is on (Fable's Part A control).

Production 16:01-16:41Z 2026-10-31 (Polymarket worker-ws, v6005 `667df791`,
~180 live games): every catalog handover (16:04:11, 16:08:35, 16:11:40,
16:25:52, 16:31:21, 16:40:58) shed 115-244 queued stamp attempts back to debt
(`PM_HANDOVER_SHED_QUEUED`, the default). Debt drains at most one shared rider
and one live rider per door admission, each slot held until its rider's stamp
RETURNS from the back of a ~250-deep queue — about two events per queue turn —
plus one old attempt per fresh-bearing `refresh`. 57% of the hour's moved live
receipt chains, and 33 of its 40 worst, carried a shed instant as `held_wall`:
a moving game paid one extra queue turn, a quiet game 30-160 s.

The control (RED on `667df791`, GREEN with the change): after a shed, with
`handover_fresh` on, the next fresh-bearing call stamps every shed event as
its own fresh population instead of one per call; off is today's debt.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks.speed_switches import OFF
from tests.test_kalshi_fresh_admission_10090 import _held_reads
from tests.test_single_event_commit_10090 import rig as refresher_rig, settle_until

pytestmark = pytest.mark.asyncio

NAME = "handover_fresh"


@pytest.fixture
def trial(monkeypatch):
    """A `handover_fresh` alternation whose current arm the test sets."""
    arm = {"value": 1, "reads": 0}

    class _Trial:
        def value(self, name, default, at=None):
            if name != NAME:
                return default
            arm["reads"] += 1
            return arm["value"]

        def trip(self, name, error):
            pass

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    return arm


async def _call_with_queue(monkeypatch):
    """Call on game 1 held in its UPDATE; 2, 3, 4 admitted and held in their
    reads on the three stamp workers; 5 and 6 admitted with no free worker;
    7 never admitted (the next flush's fresh price)."""
    x = refresher_rig(monkeypatch, count=7, block=True, blocked=(1,))
    holds = _held_reads(x, 2, 3, 4)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    await settle_until(lambda: "update" in x.commands)
    for event_id, at in ((2, 1002), (3, 1004), (4, 1006), (5, 1008), (6, 1010)):
        assert x.r.admit_fresh([event_id], flush_started=at) == {event_id}
    window = x.r._admission
    await settle_until(lambda: list(window.queue) == [5, 6])
    return x, holds, running, window


def _release(x, holds):
    x.release.set()
    for hold in holds.values():
        hold.set()


@pytest.mark.parametrize("on", [1, 0])
async def test_shed_attempts_are_the_next_calls_fresh_population_when_on(
    monkeypatch, trial, on,
):
    trial["value"] = on
    x, holds, running, window = await _call_with_queue(monkeypatch)
    try:
        assert x.r.shed_queued() == {5, 6}
        assert window.closed and not window.queue and not window.live_queue
        assert x.r.pending_event_ids() == frozenset({5, 6})
        assert not x.r._failed_hold_until  # owed now, never held 5 s
        assert not running.done()  # the running attempts are not cancelled
    finally:
        _release(x, holds)
    await asyncio.wait_for(running, 2)
    assert sorted(x.published) == [1, 2, 3, 4]
    assert x.r.pending_event_ids() == frozenset({5, 6})
    assert x.r._admission is None and x.r.stats["errors"] == 0
    # The next flush carries a fresh price (7): a fresh-bearing call stamps
    # its fresh population and at most FRESH_FLUSH_PENDING_ATTEMPTS old ones.
    await asyncio.wait_for(x.r.refresh([7], flush_started=1020), 2)
    if on:
        # The shed attempts ARE the call's fresh population: all stamped now.
        assert sorted(x.published) == [1, 2, 3, 4, 5, 6, 7]
        assert x.r.pending_event_ids() == frozenset()
        assert x.r._carried_fresh == set()
    else:
        # Today: the fresh price and ONE old attempt; the other waits a call.
        assert sorted(x.published) == [1, 2, 3, 4, 5, 7]
        assert x.r.pending_event_ids() == frozenset({6})
    assert x.r.stats["errors"] == 0


@pytest.mark.parametrize("on", [1, 0])
async def test_every_shed_attempt_is_carried_not_only_the_first(monkeypatch, trial, on):
    # Authority N2 on 574fa549 (mutant M4, carrying `shed[:1]`, survived the
    # two-event control above: today's one old attempt covers the second).
    # Their probe P1: seven shed attempts, so a partial carry leaves debt owed.
    trial["value"] = on
    x = refresher_rig(monkeypatch, count=12, block=True, blocked=(1,))
    holds = _held_reads(x, 2, 3, 4)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    await settle_until(lambda: "update" in x.commands)
    for i, event_id in enumerate(range(2, 12)):
        assert x.r.admit_fresh([event_id], flush_started=1002 + 2 * i) == {event_id}
    window = x.r._admission
    await settle_until(lambda: len(window.queue) == 7)
    try:
        assert x.r.shed_queued() == frozenset(range(5, 12))
    finally:
        _release(x, holds)
    await asyncio.wait_for(running, 2)
    assert x.r.pending_event_ids() == frozenset(range(5, 12))
    await asyncio.wait_for(x.r.refresh([12], flush_started=1030), 2)
    if on:
        assert sorted(x.published) == list(range(1, 13))
        assert x.r.pending_event_ids() == frozenset()
    else:
        # Today: the fresh price and ONE old attempt; six stay owed (P1 reads
        # 7-11 owed only after a second call drains one more).
        assert sorted(x.published) == [1, 2, 3, 4, 5, 12]
        assert x.r.pending_event_ids() == frozenset(range(6, 12))
    assert x.r.stats["errors"] == 0


async def test_shed_reads_the_arm_once_and_an_empty_shed_carries_nothing(
    monkeypatch, trial,
):
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=(1,))
    assert x.r.shed_queued() == frozenset()  # no call: nothing shed, nothing carried
    assert x.r._carried_fresh == set() and trial["reads"] == 0
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        assert x.r.shed_queued() == frozenset()  # an empty queue: the door still closes
        assert x.r._carried_fresh == set() and trial["reads"] == 0
    finally:
        x.release.set()
    await asyncio.wait_for(running, 2)
    assert x.published == [1] and x.r.pending_event_ids() == frozenset()
