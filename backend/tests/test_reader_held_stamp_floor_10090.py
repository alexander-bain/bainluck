"""#10090 held stamp floor — a live game a reader holds open is due again
READER_HELD_STAMP_FLOOR_S (0.5 s) after its last stamp, not the refresher's
floor (2 s).

Ship: a reader holding a live game open sees each Polymarket price move
within about a second, not after the 2-second stamp floor.

Production 16:16-16:21Z 2026-10-31 (v6005 `667df791`, 4 held Polymarket
games): held recv -> stamp p50 3.52 s, held -> stamp p50 2.78 s.

Proved here: only `_due`'s floor moves, only for a LIVE event in the held set,
only while at most READER_HELD_FAST_MAX are held, never above the refresher's
own floor; the switch, `READER_HELD_STAMP_FLOOR_S=2`, an unreadable value or a
failing held source keep 2 s; the held set is read only inside the floor; and
the door admits held debt at the lower floor while unheld debt waits.
Not proved: production latency (speed's readout).
"""

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_admitted_debt_slots_10090 import _Gated, _settle

pytestmark = pytest.mark.asyncio


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(lbr, "_mono", lambda: now["t"])
    monkeypatch.delenv(lbr.STAMP_READER_FIRST_ENV, raising=False)
    monkeypatch.delenv(lbr.READER_HELD_STAMP_FLOOR_ENV, raising=False)
    return now


class _Source:
    def __init__(self, ids):
        self.ids = frozenset(ids)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.ids


def _refresher(held=(7,), live=(7, 8), floor=2.0):
    r = lbr.LiveBlendRefresher("polymarket", min_refresh_interval_s=floor)
    r.reader_held = _Source(held)
    r._live_event_ids.update(live)
    return r


def _stamped_at(r, clock, event_id, t):
    clock["t"] = t
    assert r._due(event_id, t)
    r._last_refresh_at[event_id] = t


def _due_at(r, clock, event_id, t):
    clock["t"] = t
    return r._due(event_id, t)


async def test_the_defaults():
    assert lbr.READER_HELD_STAMP_FLOOR_S == 0.5
    assert lbr.READER_HELD_FAST_MAX == 8
    assert lbr.DEFAULT_MIN_REFRESH_INTERVAL_S == 2.0


async def test_a_held_live_game_is_due_half_a_second_after_its_stamp(clock):
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    assert not _due_at(r, clock, 7, 1000.4)
    # Strawman (before): not due until 1002.0.
    assert _due_at(r, clock, 7, 1000.5)


async def test_an_unheld_live_game_keeps_the_two_second_floor(clock):
    r = _refresher()
    _stamped_at(r, clock, 8, 1000.0)
    assert not _due_at(r, clock, 8, 1000.6)
    assert not _due_at(r, clock, 8, 1001.9)
    assert _due_at(r, clock, 8, 1002.0)


async def test_a_held_game_that_is_not_live_keeps_the_two_second_floor(clock):
    r = _refresher(held=(9,), live=(7,))
    _stamped_at(r, clock, 9, 1000.0)
    assert not _due_at(r, clock, 9, 1000.6)
    assert _due_at(r, clock, 9, 1002.0)


async def test_the_switch_off_restores_two_seconds(clock, monkeypatch):
    monkeypatch.setenv(lbr.STAMP_READER_FIRST_ENV, "0")
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    assert not _due_at(r, clock, 7, 1000.6)
    assert _due_at(r, clock, 7, 1002.0)


@pytest.mark.parametrize("value", ["2", "3.5", "nope", "-1", "nan", "inf"])
async def test_a_floor_of_two_or_more_or_an_unreadable_one_restores_two_seconds(
    clock, monkeypatch, value,
):
    monkeypatch.setenv(lbr.READER_HELD_STAMP_FLOOR_ENV, value)
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    assert not _due_at(r, clock, 7, 1000.6)
    assert not _due_at(r, clock, 7, 1001.9)
    assert _due_at(r, clock, 7, 1002.0)


async def test_the_floor_env_sets_the_held_floor(clock, monkeypatch):
    monkeypatch.setenv(lbr.READER_HELD_STAMP_FLOOR_ENV, "1.0")
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    assert not _due_at(r, clock, 7, 1000.6)
    assert _due_at(r, clock, 7, 1001.0)


async def test_a_blank_floor_env_is_the_default(clock, monkeypatch):
    monkeypatch.setenv(lbr.READER_HELD_STAMP_FLOOR_ENV, " ")
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    assert _due_at(r, clock, 7, 1000.5)


async def test_up_to_eight_held_games_take_the_lower_floor_and_nine_do_not(clock):
    eight = set(range(1, 9))
    r = _refresher(held=eight, live=eight | {9})
    _stamped_at(r, clock, 1, 1000.0)
    assert _due_at(r, clock, 1, 1000.5)
    r.reader_held = _Source(eight | {9})
    r._last_refresh_at[1] = 1000.5
    # Strawman (no cap): due at 1001.0.
    assert not _due_at(r, clock, 1, 1001.0)
    assert _due_at(r, clock, 1, 1002.5)


async def test_the_held_floor_never_raises_a_lower_refresher_floor(clock):
    r = _refresher(floor=0.25)
    _stamped_at(r, clock, 7, 1000.0)
    # Strawman (held floor always): not due until 1000.5.
    assert _due_at(r, clock, 7, 1000.25)


async def test_on_a_long_flush_clock_the_held_floor_never_raises_a_lower_one(clock):
    r = _refresher(floor=0.25)
    _stamped_at(r, clock, 7, 1003.0)
    clock["t"] = 1003.3
    # Strawman (held floor always): 1003.3 - 1003.0 < 0.5, not due.
    assert r._due(7, 1000.0)


async def test_a_failing_or_unsized_held_source_keeps_two_seconds_and_fails_nothing(clock):
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)

    def boom():
        raise RuntimeError("redis gone")

    r.reader_held = boom
    assert not _due_at(r, clock, 7, 1000.6)

    class Unsized:
        def __contains__(self, event_id):
            return True

    r.reader_held = lambda: Unsized()
    assert not _due_at(r, clock, 7, 1000.6)
    assert _due_at(r, clock, 7, 1002.0)


async def test_the_held_set_is_read_only_inside_the_floor(clock):
    r = _refresher()
    source = r.reader_held
    assert _due_at(r, clock, 7, 1000.0)  # never stamped
    r._last_refresh_at[7] = 1000.0
    assert _due_at(r, clock, 7, 1002.0)  # past the refresher's floor
    assert _due_at(r, clock, 8, 1002.0)  # never stamped
    assert source.calls == 0
    r._last_refresh_at[8] = 1002.0
    assert not _due_at(r, clock, 8, 1002.6)  # unheld, inside the floor
    assert source.calls == 1


async def test_a_held_hold_after_a_failure_still_holds(clock):
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    r._failed_hold_until[7] = 1003.0
    assert not _due_at(r, clock, 7, 1000.6)
    assert _due_at(r, clock, 7, 1003.0)


async def test_stamp_wait_reason_reads_the_same_floor(clock):
    r = _refresher()
    _stamped_at(r, clock, 7, 1000.0)
    _stamped_at(r, clock, 8, 1000.0)
    clock["t"] = 1000.6
    assert r._due_unchanged(7, 1000.6)
    assert not r._due_unchanged(8, 1000.6)


async def test_on_a_long_flush_clock_a_held_game_is_due_a_held_floor_after_its_stamp(clock):
    # The Argon Rank 2 clause, at the held floor: a stamp beside the flush on
    # a later clock, then admissions still carrying the flush's start.
    r = _refresher()
    _stamped_at(r, clock, 7, 1003.0)
    clock["t"] = 1003.3
    assert not r._due(7, 1000.0)
    clock["t"] = 1003.5
    assert r._due(7, 1000.0)


# ── the door: held debt rides at the lower floor, unheld debt waits ─────────


async def _running_call(r, flush_started=1000.0):
    import asyncio

    task = asyncio.create_task(r.refresh([99], flush_started=flush_started))
    await _settle()
    assert r.admitting() and r.started == [99]
    return task


async def test_the_door_admits_held_live_debt_at_half_a_second_and_unheld_waits(clock):
    r = _Gated(blocked={99})
    r.min_refresh_interval_s = 2.0
    r.reader_held = lambda: frozenset({7})
    task = await _running_call(r)
    r._live_event_ids.update({7, 8})
    r._last_refresh_at[7] = 1000.0
    r._last_refresh_at[8] = 1000.0
    r.adopt_pending([7, 8])
    clock["t"] = 1000.6
    r.admit_fresh((), flush_started=1000.6)
    await _settle()
    # Strawman (2 s floor for all): neither is admitted until 1002.0.
    assert r.started == [99, 7]
    assert 8 in r.pending_event_ids()
    clock["t"] = 1002.0
    r.admit_fresh((), flush_started=1002.0)
    await _settle()
    assert r.started == [99, 7, 8]
    r.release.set()
    await task
