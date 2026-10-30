"""#10090 — one locked price row holds back only its own event. Real Postgres.

## the ship

Live games' Polymarket prices stop freezing for minutes when some other
transaction holds a lock on one row of the same flush chunk. Production v5973
(2026-10-30 15:16-15:48Z): one held row refused the WHOLE chunk (499/500
prices) on every flush for 4.5 and 3.3 minutes, logged as `flush error (500
retained for retry)`.

## what these cases prove, against a real row lock

The SHIPPED game flush (`flush_prices` + `write_chunk`, compiled from
`app/tasks/polymarket_ws.py`), the real price statement and the real
`LiveBlendRefresher` (event stamps acknowledged only after an independent
connection reads them back). A second connection holds ONE outcome row
`FOR UPDATE` for the whole case. Events 1, 2, 3 each have one leg (outcome N),
admitted to the same chunk.

* ``test_one_held_row_holds_back_only_its_event_in_the_same_flush``: in the
  FIRST attempt events 1 and 3 commit, stamp and publish while the row is still
  held; event 2's price stays buffered (Q491), is never written and its event
  is never stamped from the old row; nothing waits on the lock and no price
  error is logged; the skip is counted. After release, the first flush that
  is not refused writes event 2, which then publishes its new value; no flush
  that began with the row already free holds it back.
* ``test_a_held_events_received_quote_reaches_the_stamp_beside_its_neighbours``:
  with the #11138 overlay wired as the consumer wires it, the held event is
  stamped from its received quote in that same flush (readers get the new
  value), its row is still old, and the overlay lets go once the row lands.

Synthetic rows on one machine: order and coherence, not production timing.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import time

import pytest
from sqlalchemy import text

from app.tasks import live_blend_refresh as blend
from app.tasks.base import get_task_session
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (  # noqa: F401
    EVENT_1_OUTCOME,
    HELD_SIBLING_OUTCOME,
    PEER_OUTCOME,
    build,
    consumer,
    hold_outcome_row,
    lock_waiters,
    start_cadence,
    stop_cadence,
    wait_for,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

HELD = PEER_OUTCOME  # event 2's leg
NEIGHBOURS = (EVENT_1_OUTCOME, HELD_SIBLING_OUTCOME)  # events 1 and 3
QUOTES = {EVENT_1_OUTCOME: 0.71, PEER_OUTCOME: 0.72, HELD_SIBLING_OUTCOME: 0.73}


async def wire_held_quotes(t, consumer):
    """The consumer's #11138 wiring, as #11138's own real-PG gate wires it:
    the map, a completed DB-clock sample before any input, and each accepted
    input noted with its frozen bound where `_mark_input` notes it."""
    held = t.r.held_quotes = blend.HeldRowQuotes()
    assert await held.sample_database_clock(
        functools.partial(get_task_session, engine=consumer)
    )
    accept = t.accept

    def accept_and_note(oid, value):
        mark = accept(oid, value)
        held.note_input(mark)
        return mark

    t.accept = accept_and_note
    return held


def record_writes(t):
    """Every `write_chunk` call: (started, chunk ids, written ids, skipped ids)."""
    calls: list[tuple[float, tuple, tuple, frozenset]] = []
    inner = t.p.ns["write_chunk"]

    async def recorded(chunk, **kwargs):
        started = time.monotonic()
        result = await inner(chunk, **kwargs)
        calls.append((
            started, tuple(sorted(chunk)),
            tuple(sorted(getattr(result, "written_ids", ()) or ())),
            frozenset(getattr(result, "skipped_ids", ()) or ()),
        ))
        return result

    t.p.ns["write_chunk"] = recorded
    return calls


async def stored_price(rig, oid) -> float:
    async with rig.engine.connect() as conn:
        return float(await conn.scalar(
            text("SELECT current_probability FROM futures_outcomes WHERE id = :id"),
            {"id": oid},
        ))


def published(t, event_id, value):
    return [at for at, eid, v, _ in t.pubs if eid == event_id and v == value]


async def run_hold(rig, consumer, monkeypatch, *, overlay):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    if overlay:
        await wire_held_quotes(t, consumer)
    else:
        t.r.held_quotes = None  # the stamp reads only the stored row
    calls = record_writes(t)
    holder, tx, holder_pid = await hold_outcome_row(rig, HELD)
    for oid, value in QUOTES.items():  # one flush admits all three
        t.accept(oid, value)
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    out: dict = {}
    waiters = 0
    try:
        async with asyncio.timeout(3.0):
            while not all(published(t, oid, QUOTES[oid]) for oid in NEIGHBOURS):
                waiters = max(waiters, await lock_waiters(rig, holder_pid))
                await asyncio.sleep(0.002)
        # Several more flushes with the row still held.
        settle_until = time.monotonic() + 0.75
        while time.monotonic() < settle_until:
            waiters = max(waiters, await lock_waiters(rig, holder_pid))
            await asyncio.sleep(0.01)
        out.update(
            held_buffered=t.p.ns["price_buffer"].get(HELD),
            held_row=await stored_price(rig, HELD),
            held_event_values=[v for _, eid, v, _ in t.pubs if eid == HELD],
            neighbour_rows=[await stored_price(rig, oid) for oid in NEIGHBOURS],
            lock_waiters_seen=waiters,
            calls_before_release=list(calls),
        )
        assert tx.is_active, "all of the above happened while the row was held"
        release_began = time.monotonic()
        await tx.rollback()
        released = time.monotonic()  # the server let go before it replied
        await wait_for(lambda: published(t, HELD, QUOTES[HELD]), timeout=3.0)
        async with asyncio.timeout(3.0):  # the row itself lands
            while await stored_price(rig, HELD) != QUOTES[HELD]:
                await asyncio.sleep(0.005)
        out.update(
            release_began=release_began,
            released=released,
            landed_row=await stored_price(rig, HELD),
            calls=list(calls),
        )
    finally:
        with contextlib.suppress(Exception):
            await tx.rollback()
        await holder.close()
        await stop_cadence(t, stop, cadence)
    out.update(
        stats=dict(t.p.ns["stats"]),
        buffer_after=dict(t.p.ns["price_buffer"]),
        pending_after=sorted(t.r.pending_event_ids()),
        held_quotes_after=(
            None if t.r.held_quotes is None else HELD in t.r.held_quotes
        ),
    )
    print("EVIDENCE", out)
    return t, out


def assert_only_its_event_was_held(out, *, overlay):
    first_started, first_chunk, first_written, first_skipped = out["calls_before_release"][0]
    # One chunk admitted all three; its FIRST attempt committed both neighbours
    # and held back only the locked event.
    assert first_chunk == (EVENT_1_OUTCOME, PEER_OUTCOME, HELD_SIBLING_OUTCOME), out
    assert first_written == NEIGHBOURS and first_skipped == {HELD}, out
    assert out["neighbour_rows"] == [QUOTES[oid] for oid in NEIGHBOURS], out
    # Q491: never dropped, never written while held; nothing waited on it.
    assert out["held_buffered"] == QUOTES[HELD], out
    assert out["held_row"] != QUOTES[HELD], out
    assert out["lock_waiters_seen"] == 0, out
    assert out["stats"]["price_rows_skipped_locked"] >= 1, out
    assert not out["stats"].get("errors"), out
    # The landing call is the one that WROTE the row, never the first to start
    # after the rollback returned: a flush that starts during the rollback's
    # round trip runs its statement after the server let go (CI, 4 of 5 runs).
    held_calls = [c for c in out["calls"] if HELD in c[1]]
    landed_at = next(i for i, c in enumerate(held_calls) if HELD in c[2])
    landing = held_calls[landed_at]
    if overlay:
        # Overlay-held, it keeps the existing re-probe floor (attempt68):
        # readers already have its quote, so the row waits at most 250 ms past
        # the release, plus one flush period.
        assert landing[0] - out["released"] <= 0.25 + 0.25 + 0.1, out
    else:
        # The first flush after release lands it: every earlier attempt
        # (skipped or probe-refused) began before the rollback returned.
        assert all(c[0] < out["released"] for c in held_calls[:landed_at]), out
    assert out["landed_row"] == QUOTES[HELD], out
    assert out["buffer_after"] == {} and out["pending_after"] == [], out


async def test_one_held_row_holds_back_only_its_event_in_the_same_flush(
    rig, consumer, monkeypatch,
):
    t, out = await run_hold(rig, consumer, monkeypatch, overlay=False)
    assert_only_its_event_was_held(out, overlay=False)
    # Its stamp waited for its row: nothing was published for event 2 while
    # the row was held (it would have republished the old row).
    assert out["held_event_values"] == [], out
    assert published(t, HELD, QUOTES[HELD]), out


async def test_a_held_events_received_quote_reaches_the_stamp_beside_its_neighbours(
    rig, consumer, monkeypatch,
):
    t, out = await run_hold(rig, consumer, monkeypatch, overlay=True)
    assert_only_its_event_was_held(out, overlay=True)
    # #11138: readers got the held event's new quote while its row was old —
    # stamped in the SAME flush as its neighbours, before the next attempt.
    assert out["held_event_values"] == [QUOTES[HELD]], out
    second_attempt = out["calls_before_release"][1][0]
    assert published(t, HELD, QUOTES[HELD])[0] < second_attempt, out
    assert out["held_quotes_after"] is False, out


# -- the statement itself (`chunk_price_update_stmt(..., skip_units=...)`) ----


async def _seed_units(rig):
    """Events 1-3 (#8129: outcome N on market N), plus event 1's second market
    (4, leg 4), event 2's prop market (5, leg 5: no event unit), and a leg (6)
    on event 1's market 1 that names event 3 — a question spanning events."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from tests.integration.test_live_blend_grouped_commit_8129_pg import seed

    await seed(rig, 3)
    async with rig.maker() as session:
        sport_id = (await session.get(FuturesMarket, 1)).sport_id
        for mid, eid, name in ((4, 1, "Total runs"), (5, 2, "Player prop")):
            session.add(FuturesMarket(
                id=mid, source="polymarket", external_id=f"market-{mid}",
                sport_id=sport_id, event_id=eid, name=name, status="open",
                category="game",
            ))
        await session.flush()
        for oid, mid in ((4, 4), (5, 5), (6, 1)):
            session.add(FuturesOutcome(
                id=oid, market_id=mid, external_id=f"leg-{oid}", name=f"Leg {oid}",
                current_probability=0.7, rank=2,
            ))
        await session.commit()


#: Event legs name their event; the prop names none (its unit is its market).
UNITS = {1: 1, 4: 1, 2: 2, 3: 3, 5: None, 6: 3}


async def _statement(rig, chunk, *, held, force_ids=frozenset()):
    """One writer transaction while `held` is locked elsewhere; rolled back."""
    from app.tasks import polymarket_ws as pm

    holder = await rig.engine.connect()
    hold = await holder.begin()
    await holder.execute(
        text("SELECT id FROM futures_outcomes WHERE id = :id FOR UPDATE"), {"id": held}
    )
    try:
        async with rig.engine.connect() as conn:
            tx = await conn.begin()
            await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
            started = time.monotonic()
            rows = (await conn.execute(pm.chunk_price_update_stmt(
                chunk, force_ids=set(force_ids), skip_units=UNITS,
            ))).all()
            elapsed = time.monotonic() - started
            stored = dict((await conn.execute(text(
                "SELECT id, current_probability FROM futures_outcomes ORDER BY id"
            ))).all())
            await tx.rollback()
    finally:
        await hold.rollback()
        await holder.close()
    written = {row.id for row in rows if not row.skipped}
    skipped = {row.id for row in rows if row.skipped}
    return written, skipped, {k: float(v) for k, v in stored.items()}, elapsed


CHANGED = {1: 0.5, 4: 0.5, 2: 0.5, 5: 0.5, 3: 0.7}  # 3 equals its stored 0.7
SPANNING = {**CHANGED, 6: 0.5}


async def test_the_statement_holds_back_the_held_rows_whole_event(rig):
    await _seed_units(rig)
    written, skipped, stored, elapsed = await _statement(rig, CHANGED, held=1)
    # Event 1's legs on BOTH its markets are held back, explicitly reported;
    # event 2 and the prop write; the unchanged leg returns nothing.
    assert skipped == {1, 4} and written == {2, 5}
    assert stored[1] == stored[4] == 0.7 and stored[2] == stored[5] == 0.5
    assert elapsed < 1.0, "SKIP LOCKED never waits on the row lock"


async def test_a_held_prop_holds_back_only_its_question(rig):
    await _seed_units(rig)
    written, skipped, stored, _ = await _statement(rig, CHANGED, held=5)
    # The prop's market is its own unit: event 2's game leg still writes.
    assert skipped == {5} and written == {1, 4, 2}


async def test_a_held_row_holds_back_its_whole_question_even_across_events(rig):
    await _seed_units(rig)
    written, skipped, stored, _ = await _statement(rig, SPANNING, held=1)
    # Leg 6 names event 3 but shares market 1 with the held row: the question
    # is never written half (CERT-3868), whatever event its legs name.
    assert skipped == {1, 4, 6} and written == {2, 5}


async def test_an_unchanged_held_row_takes_no_lock_but_a_forced_one_waits_its_unit(rig):
    await _seed_units(rig)
    written, skipped, _, elapsed = await _statement(rig, CHANGED, held=3)
    # The change filter runs before the lock: an unchanged row is never a
    # lock candidate, so a holder on it skips nothing.
    assert skipped == set() and written == {1, 4, 2, 5} and elapsed < 1.0
    written, skipped, _, _ = await _statement(rig, CHANGED, held=3, force_ids={3})
    # Forced (a held quote's landing write, a first observation) it is wanted.
    assert skipped == {3} and written == {1, 4, 2, 5}
