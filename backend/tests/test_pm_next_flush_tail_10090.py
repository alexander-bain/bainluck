"""#10090 — a held stamp must not hold the NEXT flush for a prop withdrawal.

Event 1's stamp is running (held inside its transaction). The flush that
started it must still return, so event 2's price — which arrives for the
successor flush — commits and publishes beside it. The parent's tail joined
the running stamp whenever ANY withdrawal was buffered, and a busy game's
non-speaking prop leg draws a fresh wide book during almost every withdrawal
transaction, so the first flush never returned while event 1's stamp was held.

A withdrawal now skips the running stamp only when every leg in its own
snapshot is one no blend reads (a venue-refuted prop) and the stamp's
membership is known; a speaking leg or unknown membership still follows it. Executes the shipped `_flush_prices`
closure and the real refresher; the database boundary is faked. Proves
ordering, not production latency.

Since the post-v5710 residual, a speaking leg follows only ITS OWN event's
running stamp, and without holding the flush: its book stays buffered and the
first flush after that stamp returns withdraws it (and re-stamps the event).
Unknown membership still joins.

Since the props' own loop (`flush_props`), a prop's withdrawal is never the
game flush's: it follows its own price there and never reads the stamp. The
game flush neither withdraws a prop nor waits for one.
"""

import asyncio

import pytest

from app.tasks import live_blend_refresh as blend
from tests.test_pm_prop_withdrawal_stamp_10090 import PROP, WIN, game, stamp_rig_block
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio

NEXT_PROP = 901  # non-speaking leg of event 2


def add_next_prop(p):
    p.ns["event_id_by_outcome"][NEXT_PROP] = 2
    p.ns["non_blend_outcome_ids"].add(NEXT_PROP)
    p.ns["market_by_outcome"][NEXT_PROP] = NEXT_PROP


def next_price(p):
    p.ns["price_buffer"][900] = 0.2
    p.ns["input_marks"][900] = blend.InputMark(
        seq=3, event_id=2, outcome_id=900, probability=0.2, kind="price",
        recv_wall=1003, recv_mono=103, venue_ts_ms=None, event_ordinal=1,
    )


def watch_withdrawals(p, x):
    """Record each withdrawal's legs and whether event 1 had committed."""
    seen = []
    withdraw = p.ns["withdraw_book_refuted_prices"]

    async def watched(session, selected):
        seen.append((sorted(selected), 1 in x.committed))
        return await withdraw(session, selected)

    p.ns["withdraw_book_refuted_prices"] = watched
    return seen


async def held_first_flush(p, x):
    """Flush 1 commits event 1's pair and leaves its stamp held."""
    held = stamp_rig_block(x)
    first = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    await asyncio.wait_for(held.entered.wait(), 1)
    return held, first


@pytest.mark.parametrize("scenario", ["no_props", "prop_churn", "late_unrelated_prop"])
async def test_next_event_publishes_while_previous_event_stamp_is_held(monkeypatch, scenario):
    p, x, attempts = game(monkeypatch, churn_leg=PROP)
    if scenario == "no_props":
        p.books.clear()  # control: the parent passed this arm
    if scenario == "late_unrelated_prop":
        # Event 2's prop draws a book DURING event 1's early withdrawal, so it
        # was never in the early pass: the tail really withdraws it, and then
        # owes no stamp for it.
        add_next_prop(p)
        withdraw = p.ns["withdraw_book_refuted_prices"]

        async def late_prop(session, selected):
            rows = await withdraw(session, selected)
            if PROP in selected:
                p.books[NEXT_PROP] = (0.01, 0.99)
            return rows

        p.ns["withdraw_book_refuted_prices"] = late_prop
    held = stamp_rig_block(x)

    async def sequential_flushes():
        assert await p.ns["flush_prices"](flush_started=1000)
        assert await p.ns["flush_props"]()
        next_price(p)  # input for the successor flush, not a later chunk
        assert await p.ns["flush_prices"](flush_started=1000.25)
        assert await p.ns["flush_props"]()

    task = asyncio.create_task(sequential_flushes())
    try:
        await asyncio.wait_for(held.entered.wait(), 1)
        await settle_until(lambda: 2 in x.published)
        assert 1 not in x.committed
        if scenario == "late_unrelated_prop":
            # Withdrawn by the props' loop while event 1's read is held.
            await settle_until(lambda: any(
                kind == "withdraw" and NEXT_PROP in ids for kind, ids in p.trace
            ))
            assert 1 not in x.committed
    finally:
        held.release.set()
        await asyncio.wait_for(task, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert x.published == [2, 1]
    assert attempts.count(1) == 1  # no prop withdrawal bought a second stamp
    assert not x.r.pending_event_ids() and x.r.stats["errors"] == 0


@pytest.mark.parametrize("leg", [PROP, WIN])
async def test_a_tail_withdrawal_waits_only_when_the_running_read_can_see_it(
    monkeypatch, leg,
):
    # Flush 2 carries no price, only a fresh wide book on one leg of event 1,
    # whose stamp is held. A prop withdraws beside the running read; a WIN leg
    # (control) must wait until that read committed. Neither holds the flush:
    # the WIN book stays buffered for the first flush after the read.
    p, x, attempts = game(monkeypatch, churn_leg=PROP)
    p.books.clear()
    held, first = await held_first_flush(p, x)
    second = None
    try:
        assert await asyncio.wait_for(first, 1)
        seen = watch_withdrawals(p, x)
        p.books[leg] = (0.01, 0.99)
        second = asyncio.create_task(p.ns["flush_prices"](flush_started=1000.25))
        assert await asyncio.wait_for(second, 1)
        if leg == PROP:
            assert seen == [] and leg in p.books  # not the game flush's
            assert await asyncio.wait_for(p.ns["flush_props"](), 1)
            assert seen == [([PROP], False)]
        else:
            assert seen == [] and leg in p.books
            assert p.ns["stats"]["stamp_fenced"] == 1
    finally:
        held.release.set()
        if second is not None:
            await asyncio.wait_for(second, 2)
        await p.ns["catalog_boundary"].join_stamps()
    if leg == WIN:
        assert seen == []
        assert await p.ns["flush_prices"](flush_started=1000.5)
        await p.ns["catalog_boundary"].join_stamps()
        assert seen == [([WIN], True)]  # withdrawn only after the read committed
        assert attempts.count(1) == 2  # and the withdrawal is re-stamped
    else:
        assert attempts.count(1) == 1
    assert not x.r.pending_event_ids()


async def test_unknown_stamp_membership_keeps_the_withdrawal_serial(monkeypatch):
    # The running owner cannot name what it reads (no pending reader): a
    # speaking leg's withdrawal in the game flush waits, as before. (The real
    # refresher always names it; only a reader-less double reaches this.) A
    # prop's withdrawal is the props' loop's and reads no stamp, exactly as
    # that loop's prop price write never did.
    p, x, attempts = game(monkeypatch, churn_leg=PROP)
    p.books.clear()
    held, first = await held_first_flush(p, x)
    second = None
    try:
        assert await asyncio.wait_for(first, 1)
        p.ns["catalog_boundary"].stamps.events = None
        seen = watch_withdrawals(p, x)
        p.books[WIN] = (0.01, 0.99)
        second = asyncio.create_task(p.ns["flush_prices"](flush_started=1000.25))
        for _ in range(50):
            await asyncio.sleep(0)
        assert not second.done() and seen == []
        p.books[PROP] = (0.01, 0.99)
        assert await asyncio.wait_for(p.ns["flush_props"](), 1)
        assert seen == [([PROP], False)]
    finally:
        held.release.set()
        if second is not None:
            await asyncio.wait_for(second, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert seen == [([PROP], False), ([WIN], True)]


async def test_next_events_own_prop_withdrawal_does_not_join_the_held_stamp(monkeypatch):
    # Event 2's price and its prop's wide book arrive for flush 2. Event 2
    # publishes while event 1's read is held; the prop's withdrawal is the
    # props' loop's, and it too goes ahead beside that held read.
    p, x, attempts = game(monkeypatch, churn_leg=PROP)
    p.books.clear()
    add_next_prop(p)
    held, first = await held_first_flush(p, x)
    second = None
    try:
        assert await asyncio.wait_for(first, 1)
        seen = watch_withdrawals(p, x)
        next_price(p)
        p.books[NEXT_PROP] = (0.01, 0.99)
        second = asyncio.create_task(p.ns["flush_prices"](flush_started=1000.25))
        await settle_until(lambda: 2 in x.published)
        assert await asyncio.wait_for(second, 1)
        assert seen == []
        # The rig re-arms event 1's prop after every withdrawal; that one
        # also withdraws beside its own event's running read.
        for _ in range(2):
            assert await asyncio.wait_for(p.ns["flush_props"](), 1)
        assert seen == [([NEXT_PROP], False), ([PROP], False)]
        assert 1 not in x.committed
    finally:
        held.release.set()
        if second is not None:
            await asyncio.wait_for(second, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert x.published == [2, 1] and not x.r.pending_event_ids()
