"""#10090 `owed_past_withdrawal` — a committed price whose stamp is owed is no
longer held behind a withdrawal that is only BUFFERED.

Production 2026-10-29 (v5954, 15:46-18:01Z): Polymarket throttle-origin holds
were 32% of held seconds, 12-48 s each, on the busiest live games (15336448
47.9 s, 15331111 45.1 s). Across 2,932 live event-minutes, none with fewer than
100 refused (wide-book) inputs a minute held a committed price 3 s or more;
with 2,000+ refused a minute and 1,000-3,000 accepted, 13 of 97 did. Every wide
book buffers a withdrawal for its leg (`handle_price`), and every debt drain
excluded the event while one was buffered (`unfinished_events`), although no
write of it had started and most priced nothing out. A new book arrived during
each flush's withdrawal write, so the event stayed excluded flush after flush.

On, a drain stamps such a throttle-deferred event: its price is committed, and
a withdrawal that does land is ordered after the stamp by the same-event fence
and owes its own stamp. A fresh cohort and a lock retry wait as before. Off
(today, and any switch error) is exactly today's behaviour.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import OFF
from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_single_event_commit_10090 import rig

pytestmark = pytest.mark.asyncio

NAME = "owed_past_withdrawal"


@pytest.fixture
def trial(monkeypatch):
    """An `owed_past_withdrawal` alternation whose current arm the test sets."""
    arm = {"value": 1, "reads": 0, "error": None}

    class _Trial:
        def value(self, name, default, at=None):
            if name != NAME:
                return default
            arm["reads"] += 1
            if arm["error"] is not None:
                raise arm["error"]
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
    return arm


def _owed_with_rearriving_books(monkeypatch, *, peer):
    """Event 1's cohort is committed and its stamp owed. Its leg draws a new
    wide book during every withdrawal write, and none prices anything out.
    With ``peer`` an unrelated game (event 2) writes a fresh price each flush."""
    p, x = paired(monkeypatch, blocked=())
    ns = p.ns
    for oid in list(ns["price_buffer"]):
        if not peer or oid in (1, 2):
            ns["price_buffer"].pop(oid)
            ns["input_marks"].pop(oid, None)
    x.r.keep_owed({1})
    books = ns["withdraw_buffer"]
    books.clear()
    books[1] = (0.01, 0.99)
    withdrawals = []

    async def withdraw(session, selected):
        withdrawals.append(sorted(selected))
        books[1] = (0.02, 0.98 - len(withdrawals) / 1000)
        return []

    ns["withdraw_book_refuted_prices"] = withdraw
    return p, x, withdrawals


async def _committed(p):
    assert await p.ns["write_chunk"]({1: 0.6, 2: 0.4})


async def _flushes(p, n, *, peer, start=1000):
    ns = p.ns
    for i in range(n):
        if peer:
            ns["price_buffer"].update({900: 0.7 + i / 100, 901: 0.3 - i / 100})
        await asyncio.wait_for(ns["flush_prices"](flush_started=start + i), 2)
        await ns["catalog_boundary"].join_stamps()


# ── the control: the real flush, on and off ──────────────────────────────────


@pytest.mark.parametrize("peer", [False, True], ids=["quiet", "peer-writes"])
@pytest.mark.parametrize("on", [0, 1])
async def test_an_owed_price_is_stamped_past_a_buffered_withdrawal(
        monkeypatch, trial, on, peer):
    trial["value"] = on
    p, x, withdrawals = _owed_with_rearriving_books(monkeypatch, peer=peer)
    await _committed(p)
    await _flushes(p, 6, peer=peer)
    # One withdrawal pass a flush; on, a pass may wait one flush behind the
    # event's running stamp (`join_stamp_reading`), never be dropped.
    assert 5 <= len(withdrawals) <= 6
    if on:
        # Stamped once, by the first flush; nothing owed after it.
        assert x.committed.count(1) == 1
        assert x.r.pending_event_ids() == frozenset()
    else:
        # Today: six flushes, the committed price still owed.
        assert 1 not in x.committed
        assert x.r.pending_event_ids() == frozenset({1})
    if peer:
        assert 2 in x.committed                     # the peer is stamped either way


@pytest.mark.parametrize("on", [0, 1])
async def test_a_paid_stamp_is_not_restarted_by_books_that_keep_arriving(
        monkeypatch, trial, on):
    """No hot loop: once the owed stamp is paid, books that keep arriving owe
    nothing, so later flushes open no stamp, and they note exactly the flush
    work they note with the switch off (the withdrawal passes)."""
    trial["value"] = on
    p, x, _ = _owed_with_rearriving_books(monkeypatch, peer=False)
    await _committed(p)
    await _flushes(p, 1, peer=False)
    assert x.committed == ([1] if on else [])
    work = p.ns["catalog_boundary"].flush_work
    sessions = len(x.sessions)
    await _flushes(p, 4, peer=False, start=1001)
    assert x.committed == ([1] if on else [])
    assert len(x.sessions) == sessions
    assert p.ns["catalog_boundary"].flush_work - work == 4


async def test_on_the_quiet_flush_hands_the_drain_to_the_owner_and_returns(
        monkeypatch, trial):
    """As for any owed stamp (`test_pm_quiet_debt_owner_10090`): the quiet
    flush starts the drain as the stamp owner's task and returns while that
    stamp waits on its row, and it notes the work so the cadence runs again."""
    p, x, _ = _owed_with_rearriving_books(monkeypatch, peer=False)
    await _committed(p)
    blocked = asyncio.Event()
    stamp = x.r._refresh_batch

    async def parked(ids, *args, **kwargs):
        if 1 in ids:
            await blocked.wait()
        return await stamp(ids, *args, **kwargs)

    x.r._refresh_batch = parked
    work = p.ns["catalog_boundary"].flush_work
    assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000), 2) is True
    owner = p.ns["catalog_boundary"].stamps
    assert owner.task is not None and not owner.task.done()
    assert p.ns["catalog_boundary"].flush_work > work
    blocked.set()
    await p.ns["catalog_boundary"].join_stamps()
    assert x.committed == [1]


async def test_on_an_unfinished_price_write_still_defers_the_owed_stamp(monkeypatch, trial):
    """A write of the event this flush could not finish (a lock-held leg) is
    not a buffered withdrawal: the drain still waits for it."""
    p, x, _ = _owed_with_rearriving_books(monkeypatch, peer=False)
    await _committed(p)
    ns = p.ns
    ns["price_buffer"][2] = 0.45
    ns["input_marks"][2] = blend_mod.InputMark(
        seq=99, event_id=1, outcome_id=2, probability=0.45, kind="price",
        recv_wall=1099, recv_mono=199, venue_ts_ms=None, event_ordinal=99,
    )
    write = ns["write_chunk"]

    async def lock_held(chunk, **kwargs):
        if 2 in chunk:
            return None                             # the row lock refused it
        return await write(chunk, **kwargs)

    ns["write_chunk"] = lock_held
    await _flushes(p, 3, peer=False)
    assert 1 not in x.committed
    assert 1 in x.r.pending_event_ids()


# ── the refresher's rule ─────────────────────────────────────────────────────


async def test_on_a_lock_retry_and_a_fresh_cohort_keep_their_exclusion(monkeypatch, trial):
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 32)  # no budget cut
    x = rig(monkeypatch, count=3)
    # All three owed; 2 also a lock retry (a refused retry stays in both sets),
    # 3 also this call's fresh cohort (an owed event committed again).
    x.r.keep_owed({1, 2, 3})
    x.r._lock_retry.add(2)
    await x.r.refresh(
        [3], flush_started=1000, defer_event_ids={1, 2, 3},
        withdrawing_event_ids={1, 2, 3},
    )
    assert x.committed == [1]
    assert x.r.pending_event_ids() == frozenset({2, 3})


async def test_on_the_door_takes_withdrawing_debt_but_not_the_cohort(monkeypatch, trial):
    """A running call's door (`admit_fresh`) may take an owed event deferred
    only by a buffered withdrawal; the cohort the caller still defers is not
    admitted."""
    monkeypatch.setattr(blend_mod, "ADMITTED_DEBT_SLOTS", 3)  # room for both
    x = rig(monkeypatch, count=3, block=True, blocked=(3,))
    x.r.keep_owed({1, 2})                           # 2 owed AND the cohort
    # Started while 1 and 2 were still deferred, so the call took neither.
    call = asyncio.create_task(
        x.r.refresh([3], flush_started=1000, defer_event_ids={1, 2})
    )
    try:
        while x.r._admission is None:
            await asyncio.sleep(0)
        owned = x.r.admit_fresh(
            [2], flush_started=1001, defer_event_ids={1, 2},
            withdrawing_event_ids={1, 2},
        )
        assert owned == frozenset()
        assert x.r._admission.debts == {1}
    finally:
        x.release.set()
        await asyncio.wait_for(call, 2)
    assert sorted(x.committed) == [1, 3]
    assert x.r.pending_event_ids() == frozenset({2})


async def test_off_and_a_switch_error_are_todays_exclusion(monkeypatch, trial):
    for arm in ({"value": 0, "error": None}, {"value": 1, "error": RuntimeError("redis")}):
        trial.update(arm)
        x = rig(monkeypatch, count=2)
        x.r.keep_owed({1})
        await x.r.refresh(
            [], flush_started=1000, defer_event_ids={1}, withdrawing_event_ids={1},
        )
        assert x.committed == []
        assert x.r.pending_event_ids() == frozenset({1})
        assert x.r.owed_beside({1}, {1}) == frozenset()


async def test_nothing_withdrawing_reads_no_switch(monkeypatch, trial):
    x = rig(monkeypatch, count=2)
    x.r.keep_owed({1})
    await x.r.refresh([], flush_started=1000, defer_event_ids={1})
    assert x.r.owed_beside({1}) == frozenset()
    assert x.r._past_withdrawal({2}) == set()       # not owed: nothing to pass
    assert trial["reads"] == 0


async def test_the_switch_is_on_the_board_and_off_today():
    spec = sw.SPECS[NAME]
    assert spec == {"modes": ("alternate",), "values": (0, 1), "today": 0}
    assert blend_mod.OWED_PAST_WITHDRAWAL_SWITCH == NAME
