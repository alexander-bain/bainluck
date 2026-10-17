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


def wire_held_quotes(t):
    """The consumer's own wiring (`_run_polymarket_ws_consumer`): install the
    map and note every accepted input with its frozen bound exactly where
    `_mark_input` does. No sample is taken here: like the consumer, the first
    completed DB-clock sample follows the first price-chunk attempt (`prime`)."""
    held = t.r.held_quotes = blend.HeldRowQuotes()
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
    wire_held_quotes(t)
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
