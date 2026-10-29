"""#10090 `lock_retry_past_withdrawal` — a Polymarket price whose stamp lost a
row-lock race is retried within seconds, not held behind a withdrawal that is
only BUFFERED.

With `owed_past_withdrawal` (#11746) and `lock_retry_prompt` (#11742) both on,
a lock retry whose prompt was due still stayed out of every drain and door
while its event had a buffered withdrawal (lane1b's both-on probe, 19:55Z
review of #11746): the prompt was kept, never spent, and never taken. On the
busy wide-book games every flush re-buffers one, so it never cleared. PM lock
holds were 22.9% of held seconds (ranking 1746Z), on exactly those games.

On, a lock retry passes a buffered withdrawal as `owed_past_withdrawal` passes
throttle-deferred debt: its price is committed, and a withdrawal that lands
after the stamp is ordered after it by the same-event fence. `_due` still
gates it. A fresh cohort, an unfinished price write and an unstamped bridged
cohort still wait. Off (today, and any switch error) is exactly the
composition's behaviour, whatever the other two switches say.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import OFF
from tests.test_lock_retry_prompt_10090 import locking
from tests.test_owed_past_withdrawal_10090 import (
    _committed, _flushes, _owed_with_rearriving_books,
)
from tests.test_single_event_commit_10090 import rig

pytestmark = pytest.mark.asyncio

NAME = "lock_retry_past_withdrawal"
OTHERS = ("owed_past_withdrawal", "lock_retry_prompt")


@pytest.fixture
def trial(monkeypatch):
    """Alternations of this switch and the two it composes with; the test sets
    each one's current arm. ``reads`` counts this switch's reads."""
    arm = {"value": 1, "others": 1, "reads": 0, "error": None}

    class _Trial:
        def value(self, name, default, at=None):
            if name in OTHERS:
                return arm["others"]
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


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(blend_mod, "_mono", lambda: now[0])
    return now


async def _lock_skip_beside_owed_debt(monkeypatch, clock):
    """Event 1's stamp gives up on a row lock (a prompt is scheduled when
    `lock_retry_prompt` is on); event 2 is throttle-deferred debt. Both events
    then keep a buffered withdrawal; event 3 ticks fresh every flush, so each
    flush allows one old attempt (FRESH_FLUSH_PENDING_ATTEMPTS)."""
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    x = rig(monkeypatch, count=3)
    locked = {1}
    locking(x, locked)
    await x.r.refresh([1], flush_started=clock[0])
    assert x.r._lock_retry == {1}
    locked.clear()                                  # the holder commits
    x.r.keep_owed({2})
    return x


async def _withdrawing_flushes(x, clock, n):
    for _ in range(n):
        clock[0] += 2.0                             # past the 1 s prompt delay
        await x.r.refresh(
            [3], flush_started=clock[0], defer_event_ids={1, 2},
            withdrawing_event_ids={1, 2},
        )


# ── off: the composition's behaviour, whatever the other two say ─────────────


@pytest.mark.parametrize("error", [False, True], ids=["off", "switch-error"])
@pytest.mark.parametrize("others", [0, 1])
async def test_off_a_lock_retry_waits_behind_a_buffered_withdrawal(
        monkeypatch, trial, clock, others, error):
    trial.update(value=0, others=others, error=RuntimeError("redis") if error else None)
    x = await _lock_skip_beside_owed_debt(monkeypatch, clock)
    await _withdrawing_flushes(x, clock, 3)
    assert trial["reads"] >= 1                      # consulted, and it said no
    assert 1 not in x.committed
    # The throttle-deferred neighbour passes exactly when #11746 says so.
    assert (2 in x.committed) == bool(others)
    assert x.r.pending_event_ids() == (frozenset({1}) if others else frozenset({1, 2}))
    assert x.r.owed_beside({1, 2}, {1, 2}) == frozenset()
    # #11742's prompt is kept, not spent.
    assert (1 in x.r._lock_prompt_at) == bool(others)
    assert x.r._lock_prompt_taken.get(1, 0) == 0
    clock[0] += 2.0
    await x.r.refresh([3], flush_started=clock[0])   # the buffer cleared
    assert 1 in x.committed
    assert x.r._lock_prompt_taken.get(1, 0) == (1 if others else 0)


# ── on ───────────────────────────────────────────────────────────────────────


async def test_on_the_prompt_is_taken_by_the_first_flush_beside_the_owed_neighbour(
        monkeypatch, trial, clock):
    """lane1b's both-on probe, flipped: the first flush after the prompt is
    due takes it as fresh, outside the one-attempt allowance, while the
    throttle-deferred neighbour still stamps as debt."""
    x = await _lock_skip_beside_owed_debt(monkeypatch, clock)
    await _withdrawing_flushes(x, clock, 1)
    assert sorted(x.committed) == [1, 2, 3]
    assert x.r._lock_prompt_taken.get(1) == 1
    assert 1 not in x.r._lock_prompt_at
    assert x.r.pending_event_ids() == frozenset()


async def test_on_without_a_prompt_the_retry_is_owed_debt_like_any_other(
        monkeypatch, trial, clock):
    """Prompts off, #11746 off: the retry passes the withdrawal as debt and
    takes the flush's one old attempt; the neighbour keeps today's exclusion."""
    trial["others"] = 0
    x = await _lock_skip_beside_owed_debt(monkeypatch, clock)
    await _withdrawing_flushes(x, clock, 1)
    assert sorted(x.committed) == [1, 3]
    assert x.r._lock_prompt_taken == {}
    await _withdrawing_flushes(x, clock, 1)         # a spare old attempt
    assert 2 not in x.committed
    assert x.r.pending_event_ids() == frozenset({2})


async def test_on_a_fresh_cohort_keeps_its_exclusion(monkeypatch, trial):
    """A lock retry committed again this call (its fresh cohort) still waits
    for its own withdrawal."""
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 32)
    x = rig(monkeypatch, count=3)
    x.r._lock_retry |= {1, 2}
    await x.r.refresh(
        [2], flush_started=1000, defer_event_ids={1, 2}, withdrawing_event_ids={1, 2},
    )
    assert x.committed == [1]
    assert x.r.pending_event_ids() == frozenset({2})


async def test_on_the_door_admits_a_due_prompt_past_the_withdrawal(monkeypatch, trial):
    """A running call's door (`admit_fresh`) takes the due prompt beside the
    cohort, outside the debt slots; the cohort it still defers is not taken,
    though it is a lock retry with a due prompt too. Off, the prompt stays out
    and is kept."""
    for on in (0, 1):
        trial["value"] = on
        x = rig(monkeypatch, count=3, block=True, blocked=(3,))
        x.r._lock_retry |= {1, 2}                   # 2 is also the cohort
        x.r._lock_prompt_at.update({1: 0.0, 2: 0.0})  # both due
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
            assert owned == frozenset()             # the cohort is deferred
            assert (1 in x.r._admission.events) == bool(on)
            assert 2 not in x.r._admission.events
            assert x.r._admission.debts == set()    # a prompt, not a debt slot
        finally:
            x.release.set()
            await asyncio.wait_for(call, 2)
        assert sorted(x.committed) == ([1, 3] if on else [3])
        assert (1 in x.r._lock_prompt_at) == (not on)
        assert 2 in x.r._lock_prompt_at             # the cohort's is kept
        assert x.r.pending_event_ids() == (frozenset({2}) if on else frozenset({1, 2}))


async def test_on_the_door_keeps_a_due_prompt_whose_write_is_unfinished(
        monkeypatch, trial):
    """calibration's review of 884dce30: the door's prompt path and its debt
    slots keep a lock retry whose price write is unfinished (in
    ``defer_event_ids`` but not in ``withdrawing_event_ids``) out, with the
    switch on, while the withdrawing one passes. Kills the mutants that judge
    either door site against the whole deferred set (CM1, CM5)."""
    trial["value"] = 1
    x = rig(monkeypatch, count=4, block=True, blocked=(3,))
    x.r._lock_retry |= {1, 4}
    x.r._lock_prompt_at.update({1: 0.0, 4: 0.0})       # both due
    call = asyncio.create_task(
        x.r.refresh([3], flush_started=1000, defer_event_ids={1, 4})
    )
    try:
        while x.r._admission is None:
            await asyncio.sleep(0)
        x.r.admit_fresh(
            [], flush_started=1001, defer_event_ids={1, 4},
            withdrawing_event_ids={1},                  # 4's write is unfinished
        )
        assert 1 in x.r._admission.events
        assert 4 not in x.r._admission.events
    finally:
        x.release.set()
        await asyncio.wait_for(call, 2)
    assert 4 not in x.committed
    assert 4 in x.r._lock_prompt_at                    # not spent
    assert 4 in x.r.pending_event_ids()


async def test_nothing_withdrawing_or_no_retry_withdrawing_reads_no_switch(
        monkeypatch, trial):
    x = rig(monkeypatch, count=3)
    x.r._lock_retry.add(1)
    x.r.keep_owed({2})
    await x.r.refresh([], flush_started=1000, defer_event_ids={1, 2})
    assert x.r._lock_retry_past({2}) == set()       # not a lock retry
    assert x.r._lock_retry_past({1}, fresh={1}) == set()
    assert trial["reads"] == 0


# ── the real Polymarket flush ────────────────────────────────────────────────


def _lock_retry_with_rearriving_books(monkeypatch, *, peer):
    """`test_owed_past_withdrawal_10090`'s busy book, but event 1's committed
    price is owed as a row-lock skip whose prompt is due, as `_refresh_batch`
    leaves one (in `_lock_retry`, not `_throttle_deferred`)."""
    p, x, withdrawals = _owed_with_rearriving_books(monkeypatch, peer=peer)
    x.r._throttle_deferred.discard(1)
    x.r._lock_retry.add(1)
    x.r._lock_prompt_at[1] = 0.0
    return p, x, withdrawals


@pytest.mark.parametrize("peer", [False, True], ids=["quiet", "peer-writes"])
@pytest.mark.parametrize("on", [0, 1])
async def test_a_lock_retry_is_stamped_past_a_buffered_withdrawal(
        monkeypatch, trial, on, peer):
    trial["value"] = on
    p, x, withdrawals = _lock_retry_with_rearriving_books(monkeypatch, peer=peer)
    await _committed(p)
    await _flushes(p, 1, peer=peer)
    # On, the first flush takes the due prompt (a later call forgets the run
    # of skips once the retry is no longer owed).
    assert x.r._lock_prompt_taken.get(1, 0) == on
    await _flushes(p, 5, peer=peer, start=1001)
    assert 5 <= len(withdrawals) <= 6
    if on:
        # Stamped once, by the first flush, as its prompt.
        assert x.committed.count(1) == 1
        assert x.r.pending_event_ids() == frozenset()
    else:
        # The composition: six flushes, the committed price still owed and
        # its due prompt never taken.
        assert trial["reads"] >= 1                  # consulted, and it said no
        assert 1 not in x.committed
        assert x.r.pending_event_ids() == frozenset({1})
        assert 1 in x.r._lock_prompt_at
    if peer:
        assert 2 in x.committed


def _unfinished_write_of_event_1(p):
    """Outcome 2 (event 1) has a newer price this flush cannot write: its row
    lock refuses the chunk. Returns the chunks attempted."""
    ns = p.ns
    ns["price_buffer"][2] = 0.45
    ns["input_marks"][2] = blend_mod.InputMark(
        seq=99, event_id=1, outcome_id=2, probability=0.45, kind="price",
        recv_wall=1099, recv_mono=199, venue_ts_ms=None, event_ordinal=99,
    )
    write = ns["write_chunk"]
    chunks = []

    async def lock_held(chunk, **kwargs):
        chunks.append(sorted(chunk))
        if 2 in chunk:
            return None                             # the row lock refused it
        return await write(chunk, **kwargs)

    ns["write_chunk"] = lock_held
    return chunks


@pytest.mark.parametrize("peer", [False, True], ids=["tail", "chunk"])
async def test_on_an_unfinished_price_write_still_defers_the_lock_retry(
        monkeypatch, trial, peer):
    """A write of the event this flush could not finish is not a buffered
    withdrawal: the retry still waits for it, on the quiet tail and on the
    chunk path beside a peer's fresh write (lane1b's #11746 M7 site)."""
    p, x, _ = _lock_retry_with_rearriving_books(monkeypatch, peer=peer)
    await _committed(p)
    write = p.ns["write_chunk"]
    chunks = _unfinished_write_of_event_1(p)
    await _flushes(p, 3, peer=peer)
    assert any(2 in chunk for chunk in chunks)  # its write was refused
    if peer:
        assert 2 in x.committed                     # the chunk path ran
    assert 1 not in x.committed
    assert 1 in x.r.pending_event_ids()
    # The holder commits: the write lands, and the retry is stamped although
    # its leg's books keep buffering a withdrawal.
    p.ns["write_chunk"] = write
    await _flushes(p, 2, peer=peer, start=1003)
    assert 1 in x.committed


async def test_on_a_withdrawal_that_lands_after_the_stamp_is_still_fenced(
        monkeypatch, trial):
    """While the passed lock retry's stamp waits on its row, the next flush's
    withdrawal of that event stays buffered (`join_stamp_reading`); it is
    written by the first flush after the stamp returns."""
    p, x, withdrawals = _lock_retry_with_rearriving_books(monkeypatch, peer=False)
    await _committed(p)
    blocked = asyncio.Event()
    stamp = x.r._refresh_batch
    stamping = []

    async def parked(ids, *args, **kwargs):
        if 1 in ids:
            stamping.append(1)
            await blocked.wait()
        return await stamp(ids, *args, **kwargs)

    x.r._refresh_batch = parked
    flush = p.ns["flush_prices"]
    assert await asyncio.wait_for(flush(flush_started=1000), 2) is True
    owner = p.ns["catalog_boundary"].stamps
    assert owner.task is not None and not owner.task.done()
    while not stamping:
        await asyncio.sleep(0)
    before = len(withdrawals)
    await asyncio.wait_for(flush(flush_started=1001), 2)
    assert len(withdrawals) == before               # fenced behind the stamp
    assert p.ns["withdraw_buffer"]                  # still buffered, not dropped
    blocked.set()
    await p.ns["catalog_boundary"].join_stamps()
    assert x.committed == [1]
    await asyncio.wait_for(flush(flush_started=1002), 2)
    await p.ns["catalog_boundary"].join_stamps()
    assert len(withdrawals) == before + 1           # written after it


async def test_the_switch_is_on_the_board_and_off_today():
    spec = sw.SPECS[NAME]
    assert spec == {"modes": ("alternate",), "values": (0, 1), "today": 0}
    assert blend_mod.LOCK_RETRY_PAST_WITHDRAWAL_SWITCH == NAME
