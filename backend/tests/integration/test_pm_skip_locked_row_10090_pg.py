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
  starts writes event 2, which then publishes its new value.
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
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import (
    Column, DateTime, Integer, MetaData, Numeric, Table, insert, text,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as task
from app.utils.futures_rank import rerank_market_fields_stmt
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
        await tx.rollback()
        released = time.monotonic()
        await wait_for(lambda: published(t, HELD, QUOTES[HELD]), timeout=3.0)
        async with asyncio.timeout(3.0):  # the row itself lands
            while await stored_price(rig, HELD) != QUOTES[HELD]:
                await asyncio.sleep(0.005)
        out.update(
            released=released,
            landed_row=await stored_price(rig, HELD),
            calls_after_release=[c for c in calls if c[0] >= released],
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
    after = [c for c in out["calls_after_release"] if HELD in c[1]]
    landing = next(c for c in after if HELD in c[2])
    if overlay:
        # Overlay-held, it keeps the existing re-probe floor (attempt68):
        # readers already have its quote, so the row waits at most 250 ms past
        # the release, plus one flush period.
        assert landing[0] - out["released"] <= 0.25 + 0.25 + 0.1, out
    else:
        # The first flush after release lands it.
        assert landing is after[0], out
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


# ----------------------------------------------------------------------------
# #10090 C (PR #11809, argon): the writer's REUSED statement shapes, against
# real asyncpg. Folded here from C's opt-in `test_pm_ws_statement_reuse_pg_10090.py`
# so a CI step that already runs (the release-wake step) runs them; C's guard
# for its private lab DSN went with it — this file's database is the step's
# disposable one. Every case owns a private schema holding only the columns
# the two production statements read or write. "baseline" builds the statement
# fresh per call; "reused" takes the cached shape plus that call's own binds.

BEFORE = datetime(2020, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def writer_db():
    schema = f"stmt_reuse_10090_{os.getpid()}_{uuid4().hex[:12]}"
    engine = create_async_engine(
        DB_URL,
        # Sequential writes reuse asyncpg's prepared-statement cache. A second
        # connection lets the lock guards hold a row beside their writer.
        pool_size=2,
        max_overflow=0,
        connect_args={"server_settings": {"search_path": schema}},
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.execute(
                text(
                    f'CREATE TABLE "{schema}".futures_outcomes ('
                    "id INTEGER PRIMARY KEY, market_id INTEGER NOT NULL, "
                    "current_probability NUMERIC(7, 6), rank INTEGER, "
                    "last_updated TIMESTAMPTZ NOT NULL, price_changed_at TIMESTAMPTZ, "
                    "is_winner BOOLEAN, resolution_source VARCHAR(100))"
                )
            )
        yield engine
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    )
        finally:
            await engine.dispose()


#: The private schema's table, as Core (no raw INSERT in a `*_pg.py` gate:
#: `test_pg_gate_seed_completeness`). Only the columns created above.
_PRIVATE_OUTCOMES = Table(
    "futures_outcomes", MetaData(),
    Column("id", Integer, primary_key=True),
    Column("market_id", Integer, nullable=False),
    Column("current_probability", Numeric(7, 6)),
    Column("rank", Integer),
    Column("last_updated", DateTime(timezone=True), nullable=False),
    Column("price_changed_at", DateTime(timezone=True)),
)


async def _seed(engine, rows):
    async with engine.begin() as connection:
        await connection.execute(
            insert(_PRIVATE_OUTCOMES),
            [
                {"id": oid, "market_id": market, "current_probability": price,
                 "rank": rank, "last_updated": BEFORE, "price_changed_at": BEFORE}
                for oid, market, price, rank in rows
            ],
        )


async def _read(engine):
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT id, market_id, current_probability, rank, last_updated, "
                    "price_changed_at FROM futures_outcomes ORDER BY id"
                )
            )
        ).mappings().all()
    return {row["id"]: dict(row) for row in rows}


async def _prices(engine, reused, chunk, *, force_ids=None, nowait=False, skip_units=None):
    if reused:
        statement, parameters = task.chunk_price_update_execution(
            chunk, force_ids=force_ids, nowait=nowait, skip_units=skip_units
        )
    else:
        statement = task.chunk_price_update_stmt(
            chunk, force_ids=force_ids, nowait=nowait, skip_units=skip_units
        )
        parameters = None
    async with AsyncSession(engine) as session, session.begin():
        result = await session.execute(statement, parameters)
        return [dict(row) for row in result.mappings().all()]


async def _ranks(engine, reused, market_ids):
    if reused:
        statement, parameters = task.pm_rerank_market_fields_execution(market_ids)
    else:
        statement, parameters = rerank_market_fields_stmt(market_ids), None
    async with AsyncSession(engine) as session, session.begin():
        return (await session.execute(statement, parameters)).rowcount


@pytest.mark.parametrize("mode", ["baseline", "reused", "reused-skip"])
async def test_pg_successive_inputs_keep_precision_force_and_returned_order(writer_db, mode):
    reused = mode != "baseline"

    async def prices(chunk, **kwargs):
        if mode == "reused-skip":  # every row its own unit, nothing held
            kwargs["skip_units"] = {oid: None for oid in chunk}
        return await _prices(writer_db, reused, chunk, **kwargs)

    await _seed(
        writer_db,
        [(11, 101, Decimal("0.051235"), 2), (12, 202, Decimal("0.750000"), 1)],
    )
    first = await prices(
        {12: Decimal("0.8123456789"), 11: Decimal("0.0512345678")}, force_ids=set(),
    )
    assert [(row["id"], row["ord"], row["current_probability"]) for row in first] == [
        (12, 1, Decimal("0.812346"))
    ]
    assert first[0]["quote_moved"] is True
    assert first[0]["market_id"] == 202
    assert first[0]["is_winner"] is None and first[0]["resolution_source"] is None
    assert first[0]["database_clock"] >= first[0]["last_updated"] > BEFORE
    assert first[0].get("skipped", False) is False
    assert (await _read(writer_db))[11]["last_updated"] == BEFORE

    latest = {11: Decimal("0.0623456789"), 12: 0.1234567}
    second = await prices(latest, force_ids=set())
    assert sorted(
        [(row["ord"], row["id"], row["current_probability"]) for row in second]
    ) == [(1, 11, Decimal("0.062346")), (2, 12, Decimal("0.123457"))]
    assert all(row["quote_moved"] is True for row in second)
    landed = await _read(writer_db)

    assert await prices(latest, force_ids=set()) == []
    assert await _read(writer_db) == landed
    forced = await prices(latest, force_ids={11})
    assert [(row["id"], row["quote_moved"]) for row in forced] == [(11, False)]
    liveness = await _read(writer_db)
    assert liveness[11]["last_updated"] > landed[11]["last_updated"]
    assert liveness[11]["price_changed_at"] == landed[11]["price_changed_at"]
    assert liveness[12] == landed[12]

    default_forced = await prices({12: 0.1234567})
    assert [(row["id"], row["quote_moved"]) for row in default_forced] == [(12, False)]
    assert await prices({}, force_ids=set()) == []


@pytest.mark.parametrize("reused", [False, True], ids=["baseline", "reused"])
async def test_pg_nowait_refusal_rolls_back_both_binary_legs_then_accepts_fresh_pair(
    writer_db, reused
):
    await _seed(
        writer_db,
        [(1, 101, Decimal("0.450000"), 2), (2, 101, Decimal("0.550000"), 1)],
    )
    before = await _read(writer_db)
    async with AsyncSession(writer_db) as holder, holder.begin():
        await holder.execute(text("SELECT id FROM futures_outcomes WHERE id = 1 FOR UPDATE"))
        # The free leg is first: a partial write before the locked companion
        # would violate CERT-3868 even if the later refusal were reported.
        with pytest.raises(DBAPIError) as refused:
            await asyncio.wait_for(
                _prices(writer_db, reused, {2: 0.25, 1: 0.75}, force_ids={1, 2}, nowait=True),
                timeout=2,
            )
        assert getattr(refused.value.orig, "sqlstate", None) == "55P03"
        assert await _read(writer_db) == before

    landed = await _prices(
        writer_db, reused, {2: Decimal("0.125"), 1: Decimal("0.875")},
        force_ids={1, 2}, nowait=True,
    )
    assert sorted((row["ord"], row["id"]) for row in landed) == [(1, 2), (2, 1)]
    state = await _read(writer_db)
    assert [state[oid]["current_probability"] for oid in (1, 2)] == [
        Decimal("0.875000"), Decimal("0.125000"),
    ]
    assert all(state[oid]["last_updated"] > BEFORE for oid in (1, 2))


@pytest.mark.parametrize("reused", [False, True], ids=["baseline", "reused"])
async def test_pg_successive_skip_flushes_each_hold_back_only_their_own_locked_unit(
    writer_db, reused
):
    """lane1b port: the cached SKIP LOCKED shape pins no skip set and no unit
    list. Each flush holds back exactly the unit of the row locked DURING it,
    read from that flush's own unit map in that flush's own chunk order."""
    await _seed(
        writer_db,
        [
            (1, 101, Decimal("0.400000"), 1),  # event 10's binary: legs 1 and 2
            (2, 101, Decimal("0.600000"), 2),
            (3, 202, Decimal("0.300000"), 1),  # questions with no event
            (4, 303, Decimal("0.700000"), 1),
            (5, 105, Decimal("0.200000"), 1),  # event 10's other question
        ],
    )
    units = {1: 10, 2: 10, 3: None, 4: None, 5: 10}

    async def flush(chunk, held=None):
        async with AsyncSession(writer_db) as holder, holder.begin():
            if held is not None:
                await holder.execute(
                    text("SELECT id FROM futures_outcomes WHERE id = :id FOR UPDATE"),
                    {"id": held},
                )
            rows = await asyncio.wait_for(
                _prices(writer_db, reused, chunk, force_ids=set(),
                        skip_units={oid: units[oid] for oid in chunk}),
                timeout=2,  # SKIP LOCKED: nothing waits on the holder
            )
        return (
            {row["id"] for row in rows if row["skipped"]},
            {row["id"] for row in rows if not row["skipped"]},
        )

    # Row 3 held: only its own question waits; event 10 and row 4 commit.
    assert await flush(
        {1: 0.45, 2: 0.55, 3: 0.35, 4: 0.75, 5: 0.25}, held=3,
    ) == ({3}, {1, 2, 4, 5})
    # Row 1 held, chunk in a new order: all of event 10 waits (its second
    # question too); row 3 — skipped last time — commits.
    assert await flush(
        {3: 0.35, 4: 0.8, 1: 0.5, 2: 0.5, 5: 0.3}, held=1,
    ) == ({1, 2, 5}, {3, 4})
    # Nothing held: nothing skipped, whatever the previous flushes held.
    assert await flush({1: 0.5, 2: 0.5, 5: 0.3}) == (set(), {1, 2, 5})
    state = await _read(writer_db)
    assert [state[oid]["current_probability"] for oid in (1, 2, 3, 4, 5)] == [
        Decimal("0.500000"), Decimal("0.500000"), Decimal("0.350000"),
        Decimal("0.800000"), Decimal("0.300000"),
    ]


@pytest.mark.parametrize("reused", [False, True], ids=["baseline", "reused"])
async def test_pg_rerank_expands_fresh_markets_and_preserves_ties_nulls_and_liveness(
    writer_db, reused
):
    await _seed(
        writer_db,
        [
            (1, 101, Decimal("0.3"), 7),
            (2, 101, Decimal("0.3"), 8),
            (3, 101, None, 9),
            (4, 202, Decimal("0.8"), 6),
            (5, 202, Decimal("0.4"), 7),
            (6, 202, None, 8),
            (7, 303, Decimal("0.9"), 3),
            (8, 303, Decimal("0.1"), 4),
            (9, 303, Decimal("0.1"), 7),
        ],
    )
    assert await _ranks(writer_db, reused, [101]) == 3
    state = await _read(writer_db)
    assert [state[oid]["rank"] for oid in range(1, 10)] == [1, 1, 3, 6, 7, 8, 3, 4, 7]

    assert await _ranks(writer_db, reused, [303, 202]) == 6
    state = await _read(writer_db)
    assert [state[oid]["rank"] for oid in range(1, 10)] == [1, 1, 3, 1, 2, 3, 1, 2, 2]
    assert all(row["last_updated"] == BEFORE for row in state.values())

    async with writer_db.begin() as connection:
        await connection.execute(
            text("UPDATE futures_outcomes SET current_probability = 0.2 WHERE id = 4")
        )
        await connection.execute(
            text("UPDATE futures_outcomes SET current_probability = 0.8 WHERE id = 5")
        )
    assert await _ranks(writer_db, reused, [202]) == 2
    changed = await _read(writer_db)
    assert [changed[oid]["rank"] for oid in range(1, 10)] == [1, 1, 3, 2, 1, 3, 1, 2, 2]
    assert await _ranks(writer_db, reused, []) == 0
    assert await _read(writer_db) == changed
    assert await _ranks(writer_db, reused, [101, 202, 303]) == 0
    assert all(row["last_updated"] == BEFORE for row in changed.values())
