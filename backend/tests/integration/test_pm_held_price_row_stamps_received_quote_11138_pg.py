"""#11138 — a held PM price row no longer holds the blend, on real PostgreSQL.

## the ship

A reader holding a live event page sees a changed Polymarket price in the
headline promptly even while a background transaction holds that price's
`futures_outcomes` row. Root's local real-PG/EventPage lab on cdd20661: PM .82
reached the folded hero after 3.69 s, only after the holder let go.

## the rig

#10090's release-wake rig (`test_pm_stamp_release_wake_10090_pg.build`): the
SHIPPED game flush closures and `write_chunk` on the consumer's own pool, real
chunk UPDATE + rerank + commit, real `LiveBlendRefresher` stamps, frames that a
recording Redis acknowledges only after an independent connection reads the
committed events row back. The holder is a second connection holding
`SELECT ... FOR UPDATE` on outcome 1's price row — not the events row.

## what is asserted

* candidate: the received quote is published (committed on the events row)
  BEFORE the holder lets go, and again for a newer quote during the same hold,
  while the price row itself still holds the old price;
* a new consumer run (empty `held_quotes`) re-reading the still-held row
  cannot put the older price back — its stamp is refused in the UPDATE;
* after release the price row lands at the newest price, the held quote is
  released, and no published value regresses;
* parent (`held_quotes = None`): nothing is published while the row is held —
  the strawman that shows the first assertion bites.

Ages are printed as EVIDENCE: synthetic rows on one machine, not production.
"""

from __future__ import annotations

import asyncio
import functools
import itertools
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.tasks import live_blend_refresh as blend
from app.tasks.base import get_task_session
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (  # noqa: F401
    PERIOD,
    build,
    consumer,
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

OUTCOME = EVENT = 1


async def hold_price_row(rig, outcome_id):
    conn = await rig.engine.connect()
    tx = await conn.begin()
    await conn.execute(
        text("SELECT id FROM futures_outcomes WHERE id = :id FOR UPDATE"),
        {"id": outcome_id},
    )
    return conn, tx


async def stored(rig):
    async with rig.engine.connect() as conn:
        price = await conn.scalar(
            text("SELECT current_probability FROM futures_outcomes WHERE id = :id"),
            {"id": OUTCOME},
        )
        sources = await conn.scalar(
            text("SELECT win_probability_sources FROM events WHERE id = :id"),
            {"id": EVENT},
        )
    return float(price), sources["polymarket"]["value"]


async def wire_held_quotes(t, consumer):
    """The consumer's own wiring (`_run_polymarket_ws_consumer`): install the
    map, take the first completed DB-clock sample before any input can arrive,
    and note every accepted input with its frozen bound exactly where
    `_mark_input` does."""
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


def published(t, value):
    return [at for at, eid, v, _ in t.pubs if eid == EVENT and v == value]


async def prime(t, rig):
    """One ordinary quote, written and published, before any hold."""
    t.accept(OUTCOME, 0.60)
    await wait_for(lambda: published(t, 0.6))
    assert await stored(rig) == (0.6, 0.6)


async def test_a_held_price_row_publishes_the_received_quote_before_release(
    rig, consumer, monkeypatch,
):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    await wire_held_quotes(t, consumer)
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    holder = tx = None
    try:
        await prime(t, rig)
        holder, tx = await hold_price_row(rig, OUTCOME)

        sent = time.monotonic()
        t.accept(OUTCOME, 0.82)
        await wait_for(lambda: published(t, 0.82), timeout=3.0)
        first_age = published(t, 0.82)[0] - sent
        assert tx.is_active  # still held
        assert await stored(rig) == (0.6, 0.82)  # row old, blend new

        # A newer quote during the same hold: refused probe / cooldown path.
        sent = time.monotonic()
        t.accept(OUTCOME, 0.84)
        await wait_for(lambda: published(t, 0.84), timeout=3.0)
        second_age = published(t, 0.84)[0] - sent
        assert await stored(rig) == (0.6, 0.84)

        # A new consumer run re-reads the still-held old row: refused.
        restarted = blend.LiveBlendRefresher(
            "polymarket", min_refresh_interval_s=0,
            session_factory=functools.partial(get_task_session, engine=consumer),
        )
        restarted.held_quotes = blend.HeldRowQuotes()
        restarted._client = t.r._client
        await restarted.refresh([EVENT])
        assert await stored(rig) == (0.6, 0.84)

        await tx.rollback()
        released = time.monotonic()
        await wait_for(lambda: OUTCOME not in t.r.held_quotes, timeout=3.0)
        landed_age = time.monotonic() - released
        assert await stored(rig) == (0.84, 0.84)
        await asyncio.sleep(0.6)  # later flushes/stamps from the landed row
    finally:
        if tx is not None and tx.is_active:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        await stop_cadence(t, stop, cadence)

    values = [v for _, eid, v, _ in t.pubs if eid == EVENT]
    assert values[values.index(0.84):] == [0.84] * len(values[values.index(0.84):])
    print(
        "EVIDENCE",
        dict(
            held_first_quote_published_s=round(first_age, 4),
            held_newer_quote_published_s=round(second_age, 4),
            row_landed_after_release_s=round(landed_age, 4),
            event_values=values,
        ),
    )


async def test_parent_publishes_nothing_while_the_price_row_is_held(
    rig, consumer, monkeypatch,
):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    t.r.held_quotes = None  # parent: the stamp reads only the stored row
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    holder = tx = None
    try:
        await prime(t, rig)
        holder, tx = await hold_price_row(rig, OUTCOME)
        t.accept(OUTCOME, 0.82)
        await asyncio.sleep(1.5)
        assert not published(t, 0.82)
        assert await stored(rig) == (0.6, 0.6)
        await tx.rollback()
        released = time.monotonic()
        await wait_for(lambda: published(t, 0.82), timeout=3.0)
        print("EVIDENCE", dict(parent_published_after_release_s=round(
            published(t, 0.82)[0] - released, 4)))
    finally:
        if tx is not None and tx.is_active:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        await stop_cadence(t, stop, cadence)


# ── B2 on the real refresher transaction: one event, one cohort ────────────
#
# lane1's review (2026-10-17) found the first DB-bound candidate overlaid PER
# LEG, so a stamp could carry one row a partial write had already re-dated
# beside sibling legs taken from the held quotes. Here the REAL refresher reads,
# overlays, orients and commits a three-way soccer event on PostgreSQL.

THREE_WAY_EVENT, HOME, DRAW, AWAY = 501, 5011, 5012, 5013


async def seed_three_way(rig, stamps):
    """One soccer event, one Polymarket match market, three legs stored at
    .45/.30/.27, each `last_updated` set from the DB's own clock."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    async with rig.maker() as session:
        sport = Sport(key="soccer_epl", name="EPL")
        session.add(sport)
        await session.flush()
        session.add(Event(
            id=THREE_WAY_EVENT, sport_id=sport.id, home_team_name="Arsenal",
            away_team_name="Chelsea", status="live", win_probability_sources={},
            commence_time=await session.scalar(text("SELECT now() - interval '30 minutes'")),
        ))
        session.add(FuturesMarket(
            id=THREE_WAY_EVENT, source="polymarket", external_id="game-501",
            sport_id=sport.id, event_id=THREE_WAY_EVENT, name="Arsenal vs Chelsea",
            status="open", category="game", market_type="duel",
        ))
        await session.flush()
        for oid, name, price in ((HOME, "Arsenal", 0.45), (DRAW, "Draw", 0.30),
                                 (AWAY, "Chelsea", 0.27)):
            session.add(FuturesOutcome(
                id=oid, market_id=THREE_WAY_EVENT, external_id=f"leg-{oid}",
                name=name, current_probability=price, rank=1,
            ))
        await session.commit()
    async with rig.engine.begin() as conn:
        for oid, offset_s in stamps.items():
            await conn.execute(
                text(
                    "UPDATE futures_outcomes SET last_updated = "
                    "clock_timestamp() + make_interval(secs => :s) WHERE id = :id"
                ),
                {"id": oid, "s": offset_s},
            )


async def stamp_three_way(rig, *, bound_offset_s):
    """Hold .47/.28/.25 at a DB bound `bound_offset_s` from now, then run the
    real refresher once and return the committed Polymarket entry."""
    from tests.integration.test_pm_stamp_release_wake_10090_pg import _Pool

    async with rig.engine.connect() as conn:
        bound = (await conn.scalar(text(
            "SELECT clock_timestamp() + make_interval(secs => :s)"
        ), {"s": bound_offset_s})).timestamp()
    held = blend.HeldRowQuotes()
    held._database_bound = bound
    marks = [
        SimpleNamespace(outcome_id=oid, seq=seq, probability=price)
        for seq, (oid, price) in enumerate(((HOME, 0.47), (DRAW, 0.28), (AWAY, 0.25)), 1)
    ]
    for mark in marks:
        held.note_input(mark)
    held.hold({m.outcome_id: (m.probability, held.bound_for(m)) for m in marks})
    refresher = blend.LiveBlendRefresher(
        "polymarket", min_refresh_interval_s=0,
        session_factory=functools.partial(get_task_session, engine=rig.engine),
    )
    refresher.held_quotes = held

    async def sink(_payload):
        return None

    client = SimpleNamespace(connection_pool=_Pool(sink))
    refresher._client = lambda: client
    await refresher.refresh([THREE_WAY_EVENT])
    await refresher.drain_history()
    async with rig.engine.connect() as conn:
        sources = await conn.scalar(
            text("SELECT win_probability_sources FROM events WHERE id = :id"),
            {"id": THREE_WAY_EVENT},
        )
    return (sources or {}).get("polymarket")


async def test_a_clean_held_three_way_event_commits_the_held_cohort(rig):
    # Every row predates the bound: the whole held cohort is the reading.
    await seed_three_way(rig, {HOME: -10, DRAW: -10, AWAY: -10})
    entry = await stamp_three_way(rig, bound_offset_s=-5)
    assert entry is not None and entry["value"] == 0.47


async def test_a_partially_written_three_way_event_commits_the_stored_cohort(rig):
    # B2: an earlier partial write re-dated only DRAW past the inputs' bound.
    # The per-leg candidate committed held HOME .47 beside stored DRAW .30 —
    # two snapshots in one reading. Whole-event abstention commits the stored
    # cohort; the held quotes stay owed to the ordinary writer.
    await seed_three_way(rig, {HOME: -10, DRAW: 0, AWAY: -10})
    entry = await stamp_three_way(rig, bound_offset_s=-5)
    assert entry is not None and entry["value"] == 0.45


# ── G1 + first quote after a restart: the REAL consumer flush ──────────────


async def test_G1_a_newer_tick_during_the_real_flush_never_tears_the_held_cohort(
    rig, consumer, monkeypatch,
):
    """lane1's G1 (Root's real-flush arm, adopted): the ACTUAL `_flush_prices`
    snapshots .70/.18/.12, a newer HOME .72 arrives while `write_chunk` is
    suspended, and the real write meets a foreign row lock. The first stamp
    commits the whole snapshot (.70), the successor commits .72 before the
    holder lets go, and after release every projection lands .72/.18/.12.
    Re-reading bounds from the live records after the write fails this at
    'current batch lost a speaking leg'."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    await seed_three_way(rig, {HOME: -10, DRAW: -10, AWAY: -10})
    held = await wire_held_quotes(t, consumer)
    for name in ("event_id_by_outcome", "market_by_outcome"):
        t.p.ns[name].update({oid: THREE_WAY_EVENT for oid in (HOME, DRAW, AWAY)})
    sequence = itertools.count(1)

    def accept(oid, price):
        mark = blend.InputMark(
            seq=next(sequence), event_id=THREE_WAY_EVENT, outcome_id=oid,
            probability=price, kind="price", recv_wall=time.time(),
            recv_mono=time.monotonic(), venue_ts_ms=None, event_ordinal=1,
        )
        t.p.ns["price_buffer"][oid] = price
        t.p.ns["input_marks"][oid] = mark
        held.note_input(mark)

    async def source_value():
        async with rig.engine.connect() as conn:
            sources = await conn.scalar(text(
                "SELECT win_probability_sources FROM events WHERE id=:id"
            ), {"id": THREE_WAY_EVENT})
        return sources["polymarket"]["value"]

    entered, resume = asyncio.Event(), asyncio.Event()
    real_write = t.p.ns["write_chunk"]
    attempts = []

    async def paused_first_write(chunk, **kwargs):
        attempts.append(dict(chunk))
        if len(attempts) == 1:
            entered.set()
            await resume.wait()
        return await real_write(chunk, **kwargs)

    t.p.ns["write_chunk"] = paused_first_write
    holder, tx = await hold_price_row(rig, HOME)
    running = cadence = None
    stop = asyncio.Event()
    try:
        for oid, price in ((HOME, .70), (DRAW, .18), (AWAY, .12)):
            accept(oid, price)
        running = asyncio.create_task(t.tracked_flush(time.monotonic()))
        await asyncio.wait_for(entered.wait(), 2)
        accept(HOME, .72)  # the real consumer already snapshotted .70/.18/.12
        resume.set()
        await asyncio.wait_for(running, 5)
        await t.boundary.join_stamps()
        assert attempts[0] == {HOME: .70, DRAW: .18, AWAY: .12}
        assert tx.is_active
        assert {HOME, DRAW, AWAY}.issubset(held._quotes), "current batch lost a speaking leg"
        assert {oid: held._quotes[oid][0] for oid in (HOME, DRAW, AWAY)} == {
            HOME: .70, DRAW: .18, AWAY: .12,
        }
        assert await source_value() == .70
        assert t.p.ns["price_buffer"][HOME] == .72

        # The successor flush starts one production cadence after the first,
        # as the real cadence would: the refresher's per-event floor is that
        # cadence (`min_refresh_interval_s=PERIOD`), so a back-to-back call
        # inside it leaves .72 owed to the next flush. Called back to back,
        # this arm passed only because the first write spent the whole 500 ms
        # lock budget; a 50 ms price-statement budget (#10090) exposed it, and
        # the parent fails it identically with a 10 ms gap.
        await asyncio.sleep(max(0.0, t.flush_starts[0] + PERIOD - time.monotonic()))
        await t.tracked_flush(time.monotonic())
        await t.boundary.join_stamps()
        assert await source_value() == .72
        assert held._quotes[HOME][0] == .72
        assert tx.is_active

        await tx.rollback()
        cadence = start_cadence(t, stop)
        await wait_for(lambda: all(oid not in held for oid in (HOME, DRAW, AWAY)), timeout=5)
        await stop_cadence(t, stop, cadence)
        cadence = None
        async with rig.engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id,current_probability FROM futures_outcomes WHERE id=ANY(:ids)"
            ), {"ids": [HOME, DRAW, AWAY]})).all()
        assert {oid: float(value) for oid, value in rows} == {HOME: .72, DRAW: .18, AWAY: .12}
        assert await source_value() == .72
        values = [v for _, eid, v, _ in t.pubs if eid == THREE_WAY_EVENT]
        assert values[:2] == [.70, .72]
        assert all(v == .72 for v in values[1:])
        print("G1_EVIDENCE", {"attempts": attempts, "committed_values": values})
    finally:
        resume.set()
        if tx.is_active:
            await tx.rollback()
        await holder.close()
        if running is not None and not running.done():
            await asyncio.wait_for(running, 5)
        if cadence is not None:
            await stop_cadence(t, stop, cadence)
        await t.boundary.join_stamps()
        await t.r.drain_history()


async def test_the_first_quote_after_a_consumer_start_is_published_while_its_row_is_held(
    rig, consumer, monkeypatch,
):
    """Root's initial-sample review: a fresh consumer's FIRST accepted quote must
    carry a bound, so it reaches the page while a foreign transaction holds its
    row. Without the startup sample its bound is None, frozen, and no later
    sample may re-date it: nothing publishes until the holder lets go."""
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    await wire_held_quotes(t, consumer)  # the consumer's startup sample
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    holder = tx = None
    try:
        holder, tx = await hold_price_row(rig, OUTCOME)
        sent = time.monotonic()
        t.accept(OUTCOME, 0.82)  # no earlier write: the startup sample is the bound
        await wait_for(lambda: published(t, 0.82), timeout=3.0)
        age = published(t, 0.82)[0] - sent
        assert tx.is_active
        price, value = await stored(rig)
        assert value == 0.82 and price != 0.82
        await tx.rollback()
        await wait_for(lambda: OUTCOME not in t.r.held_quotes, timeout=3.0)
    finally:
        if tx is not None and tx.is_active:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        await stop_cadence(t, stop, cadence)
    print("EVIDENCE", dict(first_quote_after_start_published_s=round(age, 4)))


# ── #10090: Root's attempt19 transient-hold case on the shipped writer ─────
#
# Root's local real-PG gate (attempt19-fast-retry-779) failed ONE case of the
# 50 ms price-statement budget: ambiguous bound, a 150 ms foreign hold, .82
# published 1000.563 ms after the input (strict < 1 s). Its traced rerun
# (attempt20) located the phase: the deferred chunk still held .82, so the
# event owed a stamp the overlay refuses for an ambiguous row; that stamp
# republished the stored .70 (171→580 ms) while the event fence kept two
# retries of .82 out. The same case, same holder, same cadence and the same
# strict bound, now on the SHIPPED writer: an ambiguous quote is not held, so
# no stored-row stamp runs and .70 is never republished.


@pytest.mark.parametrize("retry_s", [0.25, 2.0])
@pytest.mark.parametrize("bound", ["eligible", "missing", "ambiguous"])
async def test_a_transient_hold_publishes_within_one_second_without_republishing_the_stored_row(
    rig, consumer, monkeypatch, retry_s, bound,
):
    from sqlalchemy import event as sa_event

    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    t.p.ns["PRICE_FLUSH_SECONDS"] = retry_s
    if bound == "missing":
        held = t.r.held_quotes = blend.HeldRowQuotes()  # no completed sample
        accept = t.accept

        def note(oid, value):
            mark = accept(oid, value)
            held.note_input(mark)
            return mark

        t.accept = note
    else:
        await wire_held_quotes(t, consumer)
    if bound == "ambiguous":
        # A committed write after the sample: the stored row is at/after
        # every bound this run freezes until the next completed sample.
        async with rig.engine.begin() as conn:
            await conn.execute(text(
                "UPDATE futures_outcomes SET last_updated = clock_timestamp() WHERE id = :id"
            ), {"id": OUTCOME})
    holder, tx = await hold_price_row(rig, OUTCOME)
    stop = asyncio.Event()
    cadence = release = None
    released = []
    statement_entered = asyncio.Event()

    def observe_statement(conn, cursor, statement, parameters, context, executemany):
        if "WITH locked AS MATERIALIZED" in statement:
            statement_entered.set()

    sa_event.listen(consumer.sync_engine, "before_cursor_execute", observe_statement)

    async def release_short_lock():
        await asyncio.wait_for(statement_entered.wait(), 2)
        await asyncio.sleep(0.15)
        await tx.rollback()
        released.append(time.monotonic())

    try:
        sent = time.monotonic()
        t.accept(OUTCOME, 0.82)
        release = asyncio.create_task(release_short_lock())
        cadence = start_cadence(t, stop)
        await wait_for(lambda: published(t, 0.82), timeout=5)
        first = published(t, 0.82)[0]
        await asyncio.wait_for(release, 5)
        t.accept(OUTCOME, 0.84)
        await wait_for(lambda: published(t, 0.84), timeout=5)
        await wait_for(lambda: not t.p.ns["price_buffer"], timeout=5)
        await stop_cadence(t, stop, cadence)
        cadence = None
        assert await stored(rig) == (0.84, 0.84)
        values = [v for _, eid, v, _ in t.pubs if eid == EVENT]
        print("TRANSIENT_HOLD_EVIDENCE", dict(
            bound=bound, retry_s=retry_s,
            first_ms=round(1000 * (first - sent), 3),
            release_ms=round(1000 * (released[0] - sent), 3),
            after_release_ms=round(1000 * (first - released[0]), 3),
            values=values,
        ))
        assert values[-1] == 0.84
        assert all(v == 0.84 for v in values[values.index(0.84):])
        # The phase attempt20 traced: no stamp of the stored row ran first.
        assert values[0] == 0.82, values
        # Root's attempt19 assertion, unchanged.
        assert first - sent < 1, values
    finally:
        sa_event.remove(consumer.sync_engine, "before_cursor_execute", observe_statement)
        if tx.is_active:
            await tx.rollback()
        await holder.close()
        if release is not None and not release.done():
            release.cancel()
            await asyncio.gather(release, return_exceptions=True)
        if cadence is not None:
            await stop_cadence(t, stop, cadence)
