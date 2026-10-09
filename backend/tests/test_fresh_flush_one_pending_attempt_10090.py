"""#10090 — a flush carrying fresh event IDs attempts at most one old stamp.

Old debt used to run serially behind a busy flush's fresh work for up to the
whole 1 s pending budget. Now the flush (all of its refresh calls together)
attempts one old event and leaves the rest owed in continuation order; quiet
flushes keep the full time budget, and untimed calls are unchanged.
"""

from tests.test_single_event_commit_10090 import rig


async def test_fresh_bearing_flush_attempts_one_old_event_and_keeps_the_rest_owed(monkeypatch):
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3, 4}
    await x.r.refresh([5], flush_started=1000)
    # Parent: [5, 1, 2, 3, 4] — every old stamp serially after the fresh one.
    assert x.committed == x.published == [5, 1]
    assert x.r.pending_event_ids() == frozenset({2, 3, 4})
    assert x.r._pending_continuation == [2, 3, 4]
    assert not x.r._failed_hold_until
    # The same flush's later quiet call shares the spent allowance.
    await x.r.refresh_pending(flush_started=1000)
    assert x.committed == [5, 1]
    # A quiet flush drains the rest under the existing time budget.
    await x.r.refresh_pending(flush_started=1002)
    assert x.committed == x.published == [5, 1, 2, 3, 4]
    assert not x.r.pending_event_ids()


async def test_fresh_work_after_an_old_attempt_in_the_same_flush_adds_no_old_attempt(monkeypatch):
    x = rig(monkeypatch, count=5)
    x.r._throttle_deferred = {1, 2, 3}
    await x.r.refresh_pending(flush_started=1000, defer_event_ids={2, 3})
    assert x.committed == [1]
    await x.r.refresh([5], flush_started=1000)
    assert x.committed == [1, 5]
    assert x.r.pending_event_ids() == frozenset({2, 3})


async def test_untimed_calls_keep_attempting_all_due_debt(monkeypatch):
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3, 4}
    await x.r.refresh([5])
    assert x.committed == x.published == [5, 1, 2, 3, 4]
    assert not x.r.pending_event_ids()
