"""#10090 — a held PM quote that returns to its STORED price still reaches readers.

## the ship

A reader holding a live event page sees every Polymarket reversal promptly
while a background transaction holds that leg's `futures_outcomes` row. Root's
local real-PG/EventPage lab on 0edcd41a (attempt67): nine held PM home rows,
36 alternating .65/.655 pulses — 1 of 36 reached the headline and chart, and
the page sat on .655 for 24.669 s.

## the mechanism

While the row is held, a quote that differs from the stored price is published
through `HeldRowQuotes` (#11138): the events row carries .655, the price row
still stores .65. The return to .65 then equals the STORED price, so the chunk
UPDATE's unchanged-price filter returned no row, took no lock and raised
nothing. `write_chunk` read that as a landed write: it cleared the buffer,
released the held quote and staged no observation. The page kept .655.

The repair: a leg the overlay holds is forced through the price write, so a
still-held row refuses and the newer quote is held and published by the same
overlay; and a forced write that lands after the holder let go returns its row,
so the flush owes and stamps that event from the stored price. Both arms below
fail on the parent (0edcd41a) and pass on the repair.

## the rig

#11138's (`test_pm_held_price_row_stamps_received_quote_11138_pg`): the SHIPPED
game flush and `write_chunk` on the consumer's own pool, real stamps, frames a
recording Redis acknowledges only after the committed events row reads back.
The production 250 ms cadence, so the defect is not tied to the opt-in 25 ms
game cadence (#11218).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.integration.test_pm_held_price_row_stamps_received_quote_11138_pg import (  # noqa: F401
    DB_URL,
    EVENT,
    OUTCOME,
    build,
    consumer,
    hold_price_row,
    prime,
    rig,
    start_cadence,
    stop_cadence,
    stored,
    wait_for,
    wire_held_quotes,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


def published_since(t, value, sent):
    return [
        at for at, eid, v, _ in t.pubs
        if at >= sent and eid == EVENT and v == value
    ]


async def test_a_return_to_the_stored_price_is_published_while_the_row_stays_held(
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
        # .60 is the stored price: each return to it is the case that was lost.
        for value in (0.82, 0.60, 0.84, 0.60):
            sent = time.monotonic()
            t.accept(OUTCOME, value)
            await wait_for(lambda: published_since(t, value, sent), timeout=2.0)
            assert tx.is_active  # still held
            assert await stored(rig) == (0.60, value)

        await tx.rollback()
        await wait_for(lambda: not t.p.ns["price_buffer"], timeout=3.0)
        assert OUTCOME not in t.r.held_quotes
        assert await stored(rig) == (0.60, 0.60)
        values = [v for _, eid, v, _ in t.pubs if eid == EVENT]
        assert values[-4:] == [0.82, 0.60, 0.84, 0.60], values
    finally:
        if tx is not None and tx.is_active:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        await stop_cadence(t, stop, cadence)


async def test_a_return_to_the_stored_price_after_the_holder_lets_go_is_published(
    rig, consumer, monkeypatch,
):
    """The holder lets go between the held quote's publication and the next
    flush, and the return to the stored price arrives in that gap: the forced
    write now LANDS, unchanged, and must still move the page off the held
    value it published."""
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
        await wait_for(lambda: published_since(t, 0.82, sent), timeout=2.0)
        assert OUTCOME in t.r.held_quotes
        assert await stored(rig) == (0.60, 0.82)

        # No flush runs between the release and the return.
        await stop_cadence(t, stop, cadence)
        await tx.rollback()
        sent = time.monotonic()
        t.accept(OUTCOME, 0.60)
        stop = asyncio.Event()
        cadence = start_cadence(t, stop)

        await wait_for(lambda: published_since(t, 0.60, sent), timeout=2.0)
        await wait_for(lambda: not t.p.ns["price_buffer"], timeout=3.0)
        assert OUTCOME not in t.r.held_quotes
        assert await stored(rig) == (0.60, 0.60)
    finally:
        if tx is not None and tx.is_active:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        await stop_cadence(t, stop, cadence)
