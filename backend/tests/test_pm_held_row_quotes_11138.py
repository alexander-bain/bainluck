"""#11138 — `HeldRowQuotes`: a held price row's received quote, ordered by the DB clock.

PILLARS: TRUTH / FORMATTING. SHIP: a held event page shows the correct changed
blended probability within one second even while a background transaction
holds the Polymarket price row.

The real-PostgreSQL flush/stamp/restart/release behaviour is
`tests/integration/test_pm_held_price_row_stamps_received_quote_11138_pg.py`;
these are the pure rules it relies on, plus the two mixed-cohort cases lane1's
review found against the first DB-bound candidate (2026-10-17):

* B1 — a newer tick on ONE leg during the chunk's awaits must not drop that
  leg while its siblings are held: the bound travels with the chunk snapshot
  (`bound_for`), so the stamp reads one snapshot or none;
* B2 — a row at/after its bound defers EVERY held leg of that event
  (`overlay_event`), never only itself.

Ordering is by a completed `clock_timestamp()` sample frozen when the input is
accepted, so the worker's wall clock may be wrong by a day and nothing moves.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import (
    PREPARED_EVENT_FIELDS,
    PREPARED_MARKET_FIELDS,
    PREPARED_OUTCOME_FIELDS,
    HeldRowQuotes,
    LiveBlendRefresher,
)
from app.utils.aggregation import observation_basis, reading_regresses_stored_observation

BACKEND = Path(__file__).resolve().parents[1]


def outcome(value=0.60, stamp=100.0, oid=3):
    return SimpleNamespace(
        id=oid, current_probability=value,
        last_updated=datetime.fromtimestamp(stamp, timezone.utc),
    )


def mark(oid=3, seq=1, value=0.82, wall=999999.0):
    return SimpleNamespace(outcome_id=oid, seq=seq, probability=value, recv_wall=wall)


def accept(held, oid=3, seq=1, value=0.82, wall=999999.0):
    """`_mark_input`'s order: the mark is noted, then the flush snapshots it."""
    m = mark(oid, seq, value, wall)
    held.note_input(m)
    return m


def snapshot(held, marks):
    """The call site's chunk snapshot: price and frozen bound, under one lock."""
    return {m.outcome_id: (m.probability, held.bound_for(m)) for m in marks}


# ── ordering: the DB clock, never the worker's ─────────────────────────────


@pytest.mark.parametrize("wall", [-86400.0, 0.0, 86400.0, 1e12])
def test_worker_clock_skew_cannot_suppress_a_held_quote_or_poison_a_later_reading(wall):
    held = HeldRowQuotes()
    held._database_bound = 101.0
    m = accept(held, wall=wall)
    assert held.hold(snapshot(held, [m])) == {3}
    row = outcome()
    row = held.overlaid(row)
    assert row.current_probability == 0.82
    assert row.last_updated.timestamp() == 101.0
    stored = {"polymarket": {"value": 0.82, "observed_value": 0.82,
                             "observed_basis": {"3": 101.0}}}
    assert reading_regresses_stored_observation(stored, "polymarket", {"3": 100.0})
    assert not reading_regresses_stored_observation(stored, "polymarket", {"3": 102.0})
    # A restarted consumer holds no quote; the committed basis still refuses
    # the stale reading in the ordinary guard (real SQL: the _pg file).
    restarted = HeldRowQuotes()
    row = outcome()
    row = restarted.overlaid(row)
    assert row.current_probability == 0.60


def test_a_later_sample_never_re_dates_an_accepted_input():
    held = HeldRowQuotes()
    held._database_bound = 101.0
    m = accept(held)
    held._database_bound = 200.0  # a later retry's completed sample
    assert held.bound_for(m) == 101.0
    held.hold(snapshot(held, [m]))
    row = outcome(0.84, 102.0)  # a newer DB value landed after the input
    row = held.overlaid(row)
    assert (row.current_probability, row.last_updated.timestamp()) == (0.84, 102.0)


def test_no_completed_sample_means_no_fast_path_and_a_later_one_cannot_retrofit_it():
    held = HeldRowQuotes()
    m = accept(held)
    held._database_bound = 101.0
    assert held.bound_for(m) is None
    assert held.hold(snapshot(held, [m])) == set()
    row = outcome()
    row = held.overlaid(row)
    assert row.current_probability == 0.60


def test_bound_for_answers_only_the_exact_input_it_froze():
    held = HeldRowQuotes()
    held._database_bound = 101.0
    first = accept(held, seq=1, value=0.82)
    assert held.bound_for(first) == 101.0
    held._database_bound = 102.0
    second = accept(held, seq=2, value=0.84)
    assert held.bound_for(first) is None  # superseded by seq 2
    assert held.bound_for(second) == 102.0
    assert held.bound_for(mark(seq=2, value=0.85)) is None  # value disagrees
    assert held.bound_for(None) is None


def test_newer_quote_replaces_the_held_one_and_an_old_snapshot_cannot_come_back():
    held = HeldRowQuotes()
    held._database_bound = 101.0
    old = snapshot(held, [accept(held)])
    assert held.hold(old) == {3}
    held._database_bound = 102.0
    new = snapshot(held, [accept(held, seq=2, value=0.84)])
    assert held.hold(new) == {3}
    row = outcome()
    row = held.overlaid(row)
    assert (row.current_probability, row.last_updated.timestamp()) == (0.84, 102.0)
    assert held.hold(new) == set()


@pytest.mark.parametrize("stamp", [101.0, 101.000001, 102.0])
def test_a_row_at_or_after_the_bound_is_kept(stamp):
    held = HeldRowQuotes()
    held._database_bound = 101.0
    held.hold(snapshot(held, [accept(held)]))
    row = outcome(0.84, stamp)
    row = held.overlaid(row)
    assert (row.current_probability, row.last_updated.timestamp()) == (0.84, stamp)


def test_an_undated_row_takes_the_held_quote_and_its_basis_is_the_bound():
    held = HeldRowQuotes()
    held._database_bound = 102.0
    held.hold(snapshot(held, [accept(held, oid=1)]))
    undated = SimpleNamespace(id=1, current_probability=0.6, last_updated=None)
    older, other = outcome(oid=1), outcome(oid=2)
    undated, older, other = (held.overlaid(r) for r in (undated, older, other))
    assert undated.current_probability == older.current_probability == 0.82
    assert other.current_probability == 0.60
    # The stamp's per-row basis is the bound: a later stamp built from the
    # still-held row (basis 100) is older and `observation_admits_clause`
    # refuses it.
    assert observation_basis([older])["1"] == 102.0 > observation_basis([outcome(oid=1)])["1"]


def test_quiet_retries_create_no_new_observation():
    held = HeldRowQuotes()
    held._database_bound = 101.0
    quotes = snapshot(held, [accept(held)])
    held.hold(quotes)
    for sample in (102.0, 103.0, 104.0):
        held._database_bound = sample
        assert held.hold(quotes) == set()
        row = outcome()
        row = held.overlaid(row)
        assert row.last_updated.timestamp() == 101.0


def test_stored_precision_and_independent_release():
    held = HeldRowQuotes()
    held._database_bound = 101.0
    a = accept(held, oid=3, seq=1, value=0.8200000004)
    b = accept(held, oid=4, seq=2, value=0.18)
    quotes = snapshot(held, [a, b])
    assert held.hold(quotes) == {3, 4}
    assert held.hold({3: (0.82, 101.0), 4: (0.18, 101.0)}) == set()
    held.release(iter([3]))
    assert 3 not in held and 4 in held
    row = outcome()
    row = held.overlaid(row)
    assert row.current_probability == 0.60


# ── B1: the bound travels with the chunk snapshot ──────────────────────────


def scalar_row(eid, oid, probability, stamp):
    market = {"id": oid + 1000, "event_id": eid, "source": "polymarket"}
    event = {"id": eid, "status": "live", "completed_at": None}
    out = {"id": oid, "market_id": oid + 1000, "current_probability": probability,
           "last_updated": datetime.fromtimestamp(stamp, timezone.utc)}
    return tuple(
        obj.get(key)
        for obj, fields in (
            (market, PREPARED_MARKET_FIELDS), (event, PREPARED_EVENT_FIELDS),
            (out, PREPARED_OUTCOME_FIELDS),
        )
        for key in fields
    )


class ScalarSession:
    """Answers `_read_groups`' one statement with fixed scalar rows."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement):
        return self

    def all(self):
        return self.rows


def read(refresher, rows, event_ids):
    groups = asyncio.run(refresher._read_groups(ScalarSession(rows), event_ids))
    return {
        eid: [o.current_probability for entry in group for o in entry.outcomes]
        for eid, (_event, group) in groups.items()
    }


def test_B1_a_newer_tick_during_the_write_cannot_tear_the_held_event():
    """lane1's probe: stored .40/.30/.30, chunk .70/.18/.12, home ticks .72
    while the chunk is being written. The first candidate stamped .40/.18/.12."""
    refresher = LiveBlendRefresher("polymarket")
    refresher.held_quotes = held = HeldRowQuotes()
    held._database_bound = 100.0
    chunk = [accept(held, 11, 1, 0.70), accept(held, 12, 2, 0.18), accept(held, 13, 3, 0.12)]
    frozen = snapshot(held, chunk)  # under buffer_lock, with the marks
    # During write_chunk / the clock sample: a sample completes, home ticks.
    held._database_bound = 101.0
    accept(held, 11, 4, 0.72)
    assert held.hold(frozen) == {11, 12, 13}
    rows = [scalar_row(900, 11, 0.40, 90.0), scalar_row(900, 12, 0.30, 90.0),
            scalar_row(900, 13, 0.30, 90.0)]
    assert read(refresher, rows, [900])[900] == [0.70, 0.18, 0.12]


def test_B1_repeated_one_leg_arrivals_still_deliver_every_batch_and_the_latest():
    """Root's progress bar: a busy leg advancing on every flush must not stall
    the held event (whole-event refusal would), and each flush shows its own
    snapshot, never a tear; the next snapshot carries the newest home."""
    refresher = LiveBlendRefresher("polymarket")
    refresher.held_quotes = held = HeldRowQuotes()
    held._database_bound = 100.0
    marks = {11: accept(held, 11, 1, 0.70), 12: accept(held, 12, 2, 0.18),
             13: accept(held, 13, 3, 0.12)}
    rows = [scalar_row(900, 11, 0.40, 90.0), scalar_row(900, 12, 0.30, 90.0),
            scalar_row(900, 13, 0.30, 90.0)]
    for seq in range(4, 14):
        frozen = snapshot(held, marks.values())
        snapped_home = marks[11].probability
        held._database_bound += 1
        marks[11] = accept(held, 11, seq, round(0.70 + (seq - 3) / 1000, 6))
        held.hold(frozen)
        assert read(refresher, rows, [900])[900] == [round(snapped_home, 6), 0.18, 0.12]
    held.hold(snapshot(held, marks.values()))
    assert read(refresher, rows, [900])[900] == [0.71, 0.18, 0.12]


def test_the_call_site_snapshots_bounds_with_the_marks_under_one_lock():
    """B1 lives at the consumer's call site: the bound must be read in the same
    `buffer_lock` block that snapshots the chunk's prices and marks, and the
    held block must consume that snapshot, never the live input record."""
    source = (BACKEND / "app/tasks/polymarket_ws.py").read_text()
    assert source.count("held_quotes.bound_for(") == 1
    snap = source.index("current_chunk = {oid: price_buffer[oid] for oid in chunk_ids}")
    lock = source.rindex("async with buffer_lock:", 0, snap)
    bound = source.index("held_quotes.bound_for(")
    write = source.index("wrote = await write_chunk(", snap)
    assert lock < snap < bound < write
    # No await between the lock and the bound read: one critical section.
    assert "await" not in source[lock + len("async with buffer_lock:"):bound]
    assert "chunk_bounds[oid]" in source[write:]
    assert "_input_bounds" not in source and ".admits(" not in source


# ── B2: one ambiguous leg defers the whole event ───────────────────────────


@pytest.mark.parametrize("home_stamp,expected", [
    (99.0, [0.47, 0.28, 0.25]),   # every row predates the held inputs
    (100.0, [0.45, 0.30, 0.27]),  # equal to the bound: ambiguous, defer the event
    (100.5, [0.45, 0.30, 0.27]),  # a partial earlier write crossed the bound
])
def test_B2_the_real_group_reader_never_partially_overlays_one_event(home_stamp, expected):
    refresher = LiveBlendRefresher("polymarket")
    refresher.held_quotes = held = HeldRowQuotes()
    held._database_bound = 100.0
    frozen = snapshot(held, [accept(held, 11, 1, 0.47), accept(held, 12, 2, 0.28),
                             accept(held, 13, 3, 0.25)])
    held._database_bound = 101.0  # a retry may not re-date accepted inputs
    held.hold(frozen)
    rows = [
        scalar_row(900, 11, 0.45, home_stamp),
        scalar_row(900, 12, 0.30, 90.0),
        scalar_row(900, 13, 0.27, 90.0),
        scalar_row(901, 21, 0.62, 99.0),  # a neighbouring event is untouched
    ]
    values = read(refresher, rows, [900, 901])
    assert values[900] == expected
    assert values[901] == [0.62]


def test_B2_partial_write_then_refused_chunk_reads_one_cohort():
    """lane1's second probe: write N (now()=100.5) changed only HOME; inputs
    accepted during it froze bound 100; chunk N+1 is refused by a foreign lock.
    The first candidate stamped .45/.28/.25 — write N's home, N+1's siblings."""
    refresher = LiveBlendRefresher("polymarket")
    refresher.held_quotes = held = HeldRowQuotes()
    held._database_bound = 100.0
    frozen = snapshot(held, [accept(held, 11, 4, 0.47), accept(held, 12, 5, 0.28),
                             accept(held, 13, 6, 0.25)])
    held.hold(frozen)
    rows = [scalar_row(900, 11, 0.45, 100.5), scalar_row(900, 12, 0.30, 90.0),
            scalar_row(900, 13, 0.27, 90.0)]
    values = read(refresher, rows, [900])[900]
    assert values in ([0.45, 0.30, 0.27], [0.47, 0.28, 0.25])
    assert values == [0.45, 0.30, 0.27]


def test_overlay_event_with_no_held_leg_changes_nothing():
    held = HeldRowQuotes()
    entry = SimpleNamespace(outcomes=[outcome(0.4, 90.0, oid=1), outcome(0.6, 90.0, oid=2)])
    held.overlay_event([entry])
    assert [r.current_probability for r in entry.outcomes] == [0.4, 0.6]


def test_the_overlay_copies_and_never_mutates_the_read_row():
    """The read namespaces are not rows to write: the held price arrives on a
    copy, and the original keeps its stored value and stamp."""
    held = HeldRowQuotes()
    held._database_bound = 101.0
    held.hold(snapshot(held, [accept(held)]))
    row = outcome()
    copy = held.overlaid(row)
    assert copy is not row
    assert (copy.current_probability, copy.last_updated.timestamp()) == (0.82, 101.0)
    assert (row.current_probability, row.last_updated.timestamp()) == (0.60, 100.0)
    assert held.overlaid(outcome(oid=9)) is not None
    untouched = outcome(oid=9)
    assert held.overlaid(untouched) is untouched


# ── the optional clock read: lifecycle and cost ────────────────────────────


class _Session:
    def __init__(self, held, *, fail_exit=False, block=False):
        self.held = held
        self.fail_exit = fail_exit
        self.block = block
        self.entered = asyncio.Event()
        self.exited = False
        self.opened = 0

    async def __aenter__(self):
        self.opened += 1
        return self

    async def execute(self, query):
        self.entered.set()
        if self.block:
            await asyncio.Event().wait()
        return self

    def scalar_one(self):
        return datetime.fromtimestamp(200, timezone.utc)

    async def __aexit__(self, *args):
        assert self.held._database_bound == 100  # never published inside
        self.exited = True
        if self.fail_exit:
            raise RuntimeError("session cleanup failed")


def test_sample_is_published_only_after_a_successful_session_exit():
    held = HeldRowQuotes()
    held._database_bound = 100
    session = _Session(held)
    assert asyncio.run(held.sample_database_clock(lambda: session))
    assert session.exited and held._database_bound == 200


def test_a_failed_exit_keeps_the_previous_completed_sample():
    held = HeldRowQuotes()
    held._database_bound = 100
    session = _Session(held, fail_exit=True)
    assert not asyncio.run(held.sample_database_clock(lambda: session))
    assert session.exited and held._database_bound == 100


def test_a_timeout_releases_the_session_without_advancing_the_bound():
    held = HeldRowQuotes()
    held._database_bound = 100
    session = _Session(held, block=True)
    assert not asyncio.run(held.sample_database_clock(lambda: session))
    assert session.exited and held._database_bound == 100


def test_consumer_cancellation_propagates_and_releases_the_session():
    async def run():
        held = HeldRowQuotes()
        held._database_bound = 100
        session = _Session(held, block=True)
        task = asyncio.create_task(held.sample_database_clock(lambda: session))
        await session.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return held, session

    held, session = asyncio.run(run())
    assert session.exited and held._database_bound == 100


def test_a_timed_out_sample_backs_off_so_a_many_chunk_flush_pays_it_once():
    """Root's cost concern: the sample is awaited once per nonempty game chunk.
    One timeout must not repeat for every remaining chunk of the flush."""
    import time

    held = HeldRowQuotes()
    held._database_bound = 100
    slow = _Session(held, block=True)
    assert not asyncio.run(held.sample_database_clock(lambda: slow))
    assert held._sample_backoff_until >= time.monotonic() + HeldRowQuotes.SAMPLE_BACKOFF_S - 1
    fast = _Session(held)
    for _chunk in range(20):  # the rest of a large flush
        assert not asyncio.run(held.sample_database_clock(lambda: fast))
    assert fast.opened == 0 and held.sample_failures == 1
    held._sample_backoff_until = time.monotonic() - 0.001  # the window elapsed
    assert asyncio.run(held.sample_database_clock(lambda: fast))
    assert fast.opened == 1 and held._database_bound == 200


# ── wiring ─────────────────────────────────────────────────────────────────


def test_refresher_reads_no_overlay_unless_its_consumer_installs_one():
    assert LiveBlendRefresher("kalshi").held_quotes is None
    source = (BACKEND / "app/tasks/polymarket_ws.py").read_text()
    assert source.count("blend_refresher.held_quotes = HeldRowQuotes()") == 1
    # Every accepted input is noted with its bound, exactly where it is marked.
    assert source.count("held.note_input(mark)") == 1
    # Establish ordering before first receipt, then refresh the lower bound
    # after attempts for future inputs. Never re-date a previously accepted input.
    assert source.count("held_quotes.sample_database_clock(get_task_session)") == 2


# ── #10090: a quote the overlay would refuse is not held, so owes no stamp ──
#
# Root attempt20 (real PG, fast50, ambiguous bound): the deferred chunk still
# held .82, so its event owed a stamp the overlay refused. That stamp
# republished the stored .70 from 171 to 580 ms after the input while the event
# fence kept two retries of .82 out, and .82 published at 664 ms (attempt19,
# untraced: 1000.563 ms). A quote with no bound already took the quick path:
# no hold, no stamp, the row written at the next flush (410 ms in attempt19).


class _RowsSession:
    def __init__(self, rows, *, block=False, fail=False):
        self.rows = rows
        self.block = block
        self.fail = fail
        self.statements = []
        self.opened = 0
        self.exited = False

    async def __aenter__(self):
        self.opened += 1
        return self

    async def __aexit__(self, *args):
        self.exited = True

    async def execute(self, statement, params=None):
        self.statements.append((statement, params))
        if self.block:
            await asyncio.Event().wait()
        if self.fail:
            raise RuntimeError("canceling statement due to lock timeout")
        return self

    def all(self):
        return self.rows


def _stamp(at):
    return datetime.fromtimestamp(at, timezone.utc)


@pytest.mark.parametrize("stamp", [99.0, 99.999999, 100.0, 100.5])
def test_the_pre_hold_read_refuses_exactly_what_the_overlay_refuses(stamp):
    from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, lock_timeout_value

    reader = HeldRowQuotes()
    reader._database_bound = 100.0
    quotes = snapshot(reader, [accept(reader)])
    session = _RowsSession([(3, _stamp(stamp))])
    found = asyncio.run(reader.stored_at_or_after(lambda: session, quotes))

    overlay = HeldRowQuotes()
    overlay._database_bound = 100.0
    overlay.hold(snapshot(overlay, [accept(overlay)]))
    assert found == ({3} if overlay._ambiguous(outcome(0.70, stamp)) else set())
    assert found == ({3} if stamp >= 100.0 else set())
    # Read only, nothing held, and the relation-lock wait is bounded first.
    assert 3 not in reader and session.exited
    assert session.statements[0] == (
        SET_LOCK_TIMEOUT_SQL,
        {"ms": lock_timeout_value(HeldRowQuotes.AMBIGUITY_READ_LOCK_TIMEOUT_MS)},
    )


def test_an_undated_row_is_not_ambiguous_and_an_unchanged_quote_is_not_read_again():
    held = HeldRowQuotes()
    held._database_bound = 100.0
    quotes = snapshot(held, [accept(held)])
    undated = _RowsSession([(3, None)])
    assert asyncio.run(held.stored_at_or_after(lambda: undated, quotes)) == set()
    held.hold(quotes)
    again = _RowsSession([(3, _stamp(200.0))])
    assert asyncio.run(held.stored_at_or_after(lambda: again, quotes)) == set()
    assert again.opened == 0
    assert asyncio.run(held.stored_at_or_after(lambda: again, {})) == set()
    assert again.opened == 0


@pytest.mark.parametrize("failure", ["fail", "block"])
def test_an_unknown_read_returns_none_and_backs_off_without_moving_the_bound(failure):
    import time

    held = HeldRowQuotes()
    held._database_bound = 100.0
    quotes = snapshot(held, [accept(held)])
    session = _RowsSession([], **{failure: True})
    assert asyncio.run(held.stored_at_or_after(lambda: session, quotes)) is None
    assert session.exited
    assert held._database_bound == 100.0
    # lane1 R4: the read shares the sample's window, so it backs off both.
    assert held.sample_failures == 1
    assert held._sample_backoff_until >= time.monotonic() + HeldRowQuotes.SAMPLE_BACKOFF_S - 1


def test_a_sick_pool_costs_the_pre_hold_read_one_timeout_per_window():
    """lane1 R4 (probe sickpool.py on 84ead9a1f1): 8 lock-deferred chunks with
    a changed quote each, pool checkout never returning, one serial flush:
    the read paid 0.15 s per chunk (1.216 s) while the sample paid it once."""
    import time

    held = HeldRowQuotes()
    held._database_bound = 100.0
    quotes = snapshot(held, [accept(held)])
    opened = []

    @contextlib.asynccontextmanager
    async def hanging():
        opened.append(1)
        await asyncio.Event().wait()  # a pool checkout that never returns
        yield None

    async def flush():
        started = time.monotonic()
        answers = [await held.stored_at_or_after(hanging, quotes) for _chunk in range(8)]
        return answers, time.monotonic() - started

    answers, elapsed = asyncio.run(flush())
    assert answers == [None] * 8
    assert len(opened) == 1 and held.sample_failures == 1
    assert elapsed < 2 * HeldRowQuotes.SAMPLE_TIMEOUT_S


def test_a_read_during_an_active_sample_backoff_opens_no_session():
    import time

    held = HeldRowQuotes()
    held._database_bound = 100.0
    quotes = snapshot(held, [accept(held)])
    held._sample_backoff_until = time.monotonic() + HeldRowQuotes.SAMPLE_BACKOFF_S
    session = _RowsSession([(3, _stamp(200.0))])
    assert asyncio.run(held.stored_at_or_after(lambda: session, quotes)) is None
    assert session.opened == 0 and held.sample_failures == 0
    held._sample_backoff_until = time.monotonic() - 0.001  # the window elapsed
    assert asyncio.run(held.stored_at_or_after(lambda: session, quotes)) == {3}
    assert session.opened == 1


def _deferred_flush(stored_at_or_after, *, prior=None, batch=None):
    """The SHIPPED `_flush_prices` on #10651's rig: event 10's legs are
    deferred by a lock (`write_chunk` returns None) while held quotes are on."""
    from tests.test_polymarket_withdrawal_speed_10651 import rig

    batch = batch or {1: 0.82}
    r = rig(batch=dict(batch), mapping=dict.fromkeys(batch, 10), books={})
    held = HeldRowQuotes()
    held._database_bound = 100.0
    if prior is not None:
        held._quotes[1] = prior
    r.ns["input_marks"] = {}
    for seq, (oid, value) in enumerate(batch.items(), 1):
        m = mark(oid=oid, seq=seq, value=value)
        held.note_input(m)
        r.ns["input_marks"][oid] = m
    r.ns["blend_refresher"].held_quotes = held
    held.stored_at_or_after = functools.partial(stored_at_or_after, r)

    async def deferred(chunk, *, final=False, start_market_publish=None):
        r.trace.append(("write", list(chunk)))
        return None

    r.ns["write_chunk"] = deferred

    async def run():
        await r.ns["flush_prices"](flush_started=100)
        await r.ns["catalog_boundary"].join_stamps()

    asyncio.run(run())
    refreshed = [ids for kind, ids in r.trace if kind == "refresh" and 10 in ids]
    return held, refreshed, r


@pytest.mark.parametrize("answer,stamped", [
    (set(), True),   # the stored row predates the bound: held and stamped (#11138)
    (None, True),    # unknown: the hold stays, exactly as before
    ({1}, False),    # at/after the bound: not held, no stamp, row retried
])
def test_a_deferred_chunk_holds_and_stamps_only_what_the_overlay_can_carry(answer, stamped):
    asked = []

    async def stored_at_or_after(_r, sessions, quotes):
        asked.append(dict(quotes))
        return answer

    held, refreshed, r = _deferred_flush(stored_at_or_after)
    assert asked == [{1: (0.82, 100.0)}]
    assert (1 in held) is stamped
    assert bool(refreshed) is stamped
    # Either way the price stays buffered for the ordinary writer's next flush.
    assert r.ns["price_buffer"] == {1: 0.82}
    assert ("write", [1]) in r.trace


def test_an_ambiguous_newer_input_releases_the_older_held_quote():
    async def ambiguous(_r, sessions, quotes):
        return set(quotes)

    held, refreshed, _r = _deferred_flush(ambiguous, prior=(0.80, 90.0))
    assert 1 not in held and not refreshed


def test_a_withdrawal_during_the_read_drops_every_leg_of_its_event():
    async def withdrawn_meanwhile(r, sessions, quotes):
        assert set(quotes) == {1, 2}
        r.ns["withdraw_buffer"][2] = (0.1, 0.9)  # one leg's wide book arrives
        return set()

    held, refreshed, _r = _deferred_flush(
        withdrawn_meanwhile, batch={1: 0.82, 2: 0.18},
    )
    assert 1 not in held and 2 not in held


def test_the_pre_hold_read_runs_outside_the_buffer_lock_and_before_the_hold():
    source = (BACKEND / "app/tasks/polymarket_ws.py").read_text()
    assert source.count("held_quotes.stored_at_or_after(get_task_session, quotes)") == 1
    read = source.index("held_quotes.stored_at_or_after(get_task_session, quotes)")
    hold = source.index("held_quotes.hold(quotes)")
    quotes = source.rindex("quotes = {}", 0, read)
    lock = source.rindex("async with buffer_lock:", 0, read)
    assert lock < quotes < read < hold
    # The read is not inside the block that built the quotes.
    between = source[quotes:read]
    assert "async with buffer_lock:" not in between
    relock = source.index("async with buffer_lock:", read)
    assert relock < hold
