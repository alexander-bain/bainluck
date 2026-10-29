"""#10090 `handover_fresh` — a committed cohort a catalog handover carries over is
stamped as the next call's fresh population, not as old debt.

Production 2026-10-29 15:36:25Z (v5950): a timer handover's drain fenced the game
flush, so the bridged writer's last committed cohort (18 events, 30 of the 36
held Polymarket chains that window pre-game) went to `_PMBridgeWriter.transfer`
→ `keep_owed`: old debt, every receipt chain `origin=throttle` with the transfer
instant as `stored_wall`. FRESH_FLUSH_PENDING_ATTEMPTS=3 let about three through
per call, so the drain took 10.5 s (13:31, 14:05 and 14:30 the same shape).

On, `keep_committed` carries those events and the next `refresh` that finds one
due stamps it fresh: live first, on the fixed workers, outside the allowance.
Off (today, and any switch error) is exactly `keep_owed`.
"""

import asyncio

import pytest

from app.tasks import polymarket_ws as pm
import app.tasks.live_blend_refresh as blend_mod
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import OFF
from tests.test_single_event_commit_10090 import rig

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


def _statuses(count, live=()):
    return {eid: "live" if eid in live else "scheduled" for eid in range(1, count + 1)}


# ── the control: one call stamps the carried cohort, today it drains by one ──


@pytest.mark.parametrize("on", [0, 1])
async def test_a_handover_cohort_is_stamped_by_the_next_call_not_one_per_call(
        monkeypatch, trial, on):
    trial["value"] = on
    x = rig(monkeypatch, count=7, statuses=_statuses(7, live={7}))
    x.r.keep_committed({1, 2, 3, 4, 5, 6})
    assert trial["reads"] == 1                      # once per carried cohort
    await x.r.refresh([7], flush_started=1000)
    if on:
        assert sorted(x.committed) == [1, 2, 3, 4, 5, 6, 7]
        assert x.r.pending_event_ids() == frozenset()
        assert x.r._carried_fresh == set()
    else:
        # Today: the fresh price, then ONE old attempt under the allowance.
        assert sorted(x.committed) == [1, 7]
        assert x.r.pending_event_ids() == frozenset({2, 3, 4, 5, 6})
    # The live fresh price is never queued behind the carried cohort.
    assert x.committed[0] == 7


async def test_a_quiet_flush_stamps_the_carried_cohort_too(monkeypatch, trial):
    x = rig(monkeypatch, count=5)
    x.r.keep_committed({1, 2, 3, 4, 5})
    await x.r.refresh_pending(flush_started=1000)
    assert sorted(x.committed) == [1, 2, 3, 4, 5]
    assert x.r.pending_event_ids() == frozenset()
    assert x.r._carried_fresh == set()


async def test_keep_committed_records_exactly_what_keep_owed_records(monkeypatch, trial):
    trial["value"] = 1
    x = rig(monkeypatch, count=3)
    x.r.keep_committed([2])
    assert x.r._throttle_deferred == {2}
    assert x.r.stats["throttled"] == 1
    assert x.r._carried_fresh == {2}
    trial["value"] = 0
    x.r.keep_committed([3])
    assert x.r._throttle_deferred == {2, 3}
    assert x.r._carried_fresh == {2}                 # off: debt only


async def test_a_carried_event_not_yet_due_stays_carried_for_a_later_call(monkeypatch, trial):
    x = rig(monkeypatch, count=4, statuses=_statuses(4, live={4}))
    x.r.min_refresh_interval_s = 5.0
    x.r._last_refresh_at[3] = 999.0                  # 3's floor runs to 1004
    x.r.keep_committed({1, 2, 3})
    await x.r.refresh([4], flush_started=1000)
    assert sorted(x.committed) == [1, 2, 4]
    assert x.r._carried_fresh == {3}
    assert x.r.pending_event_ids() == frozenset({3})
    await x.r.refresh((), flush_started=1004.5)
    assert sorted(x.committed) == [1, 2, 3, 4]
    assert x.r._carried_fresh == set()
    assert x.r._pending_attempts == 0                # stamped fresh, not old


async def test_a_carried_event_that_is_no_longer_owed_is_forgotten(monkeypatch, trial):
    x = rig(monkeypatch, count=3)
    x.r.keep_committed({1, 2})
    x.r._throttle_deferred.discard(2)                # stamped by another path
    await x.r.refresh([3], flush_started=1000)
    assert sorted(x.committed) == [1, 3]
    assert x.r._carried_fresh == set()


async def test_a_carried_event_the_caller_still_writes_stays_owed_and_carried(
        monkeypatch, trial):
    x = rig(monkeypatch, count=3)
    x.r.keep_committed({1, 2})
    await x.r.refresh([3], flush_started=1000, defer_event_ids={2})
    assert sorted(x.committed) == [1, 3]
    assert x.r._carried_fresh == {2}
    assert x.r.pending_event_ids() == frozenset({2})


def test_the_handover_arm_is_off_on_any_switch_error(monkeypatch):
    def broken():
        raise RuntimeError("switchboard unreadable")

    monkeypatch.setattr(blend_mod, "_optional_db_trial", broken)
    assert blend_mod._handover_fresh() is False


# ── the hand-over itself: transfer carries through `keep_committed` ──────────


def test_transfer_hands_a_committed_cohort_to_keep_committed():
    calls = []

    class Refresher:
        def keep_committed(self, events, *, marks=()):
            calls.append(("committed", set(events), list(marks)))

        def keep_owed(self, events, *, marks=()):
            raise AssertionError("transfer prefers keep_committed")

        def adopt_pending(self, events):
            raise AssertionError("keep_committed carries the marks")

    w = pm._PMBridgeWriter()
    w._complete([900, 901], {900: "m900", 901: "m901"}, {2})
    assert w.transfer(Refresher()) == 1
    assert calls == [("committed", {2}, ["m900", "m901"])]


def test_transfer_still_keeps_owed_on_a_refresher_without_keep_committed():
    kept = []

    class Refresher:
        def keep_owed(self, events, *, marks=()):
            kept.append((set(events), list(marks)))

    w = pm._PMBridgeWriter()
    w._complete([900], {900: "m900"}, {2})
    assert w.transfer(Refresher()) == 1
    assert kept == [({2}, ["m900"])]


# ── the switchboard entry ─────────────────────────────────────────────────────


@pytest.mark.parametrize("mode, kwargs", [
    ("ab", {"half": 0}),                                  # a hand-over has no per-game arm
    ("alternate", {"a": 1, "b": 1, "period_s": 60}),      # no today arm
    ("alternate", {"a": 0, "b": 2, "period_s": 60}),
])
def test_a_handover_trial_outside_the_limits_is_refused(mode, kwargs):
    assert sw.validate(NAME, mode, **kwargs) is not None


def test_a_handover_alternation_of_off_and_on_is_accepted():
    assert sw.validate(NAME, "alternate", a=0, b=1, period_s=60) is None
    assert sw.today(NAME) == 0
    assert NAME in sw.SWITCHES
