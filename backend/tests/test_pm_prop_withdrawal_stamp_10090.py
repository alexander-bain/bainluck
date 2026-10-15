"""#10090 — a busy game's prop withdrawals must not hold its WIN stamp.

The flush held an event's stamp (and excluded it from every refresh) while ANY
of its legs had a wide book waiting for withdrawal. A venue-refuted prop leg
cannot move the blend reading, and on a busy game a fresh wide book on one of
~140 prop legs arrives during almost every withdrawal transaction, so the
committed WIN price stayed owed flush after flush. Production witness (motive,
not proof): v5647, event 14781712, a 0.135→0.14 revision stored 19:23:24.584Z
and stamped 19:23:33.734Z, origin=throttle, no lock/commit/batch failure, with
5,589 refused venue messages on that game in the minute.

Executes the shipped `_flush_prices` closure and the real refresher; the
database boundary is faked. Proves ordering and ownership, not production
latency.

Since the props' own loop (`flush_props`), a prop's price and withdrawal never
run in the game flush at all; `flush` below runs both loops, one after the
other, as the consumer's two cadences would.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.tasks import live_blend_refresh as blend
from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig
from tests.test_single_event_commit_10090 import rig as stamp_rig, settle_until

pytestmark = pytest.mark.asyncio

PROP = 3  # non-speaking (venue-refuted) leg of event 1; 4 is its complement
WIN = 1  # speaking leg of event 1; 2 is its complement


def game(monkeypatch, *, churn_leg, batch=None, hold_later_chunk=False):
    """Event 1: WIN pair 1/2 and prop pair 3/4. Every withdrawal transaction
    of ``churn_leg`` sees another wide book on it arrive meanwhile. Open leg
    900 (event 2) writes in a later chunk, held when ``hold_later_chunk``."""
    x = stamp_rig(monkeypatch, count=2)
    x.r.min_refresh_interval_s = 0.25  # deployed PM floor = PM_WS_PRICE_FLUSH_SECONDS
    p = pm_rig(
        batch={1: 0.6, 2: 0.4} if batch is None else batch,
        mapping={1: 1, 2: 1, 3: 1, 4: 1, 900: 2},
        books={churn_leg: (0.01, 0.99)},
    )
    if not hold_later_chunk:
        p.release.set()
    p.ns["non_blend_outcome_ids"].update({3, 4})
    p.ns["market_by_outcome"].update({3: 3, 4: 4})
    p.ns["open_complement_of"].update({3: 4, 4: 3})
    p.ns["input_marks"] = {
        oid: blend.InputMark(
            seq=n, event_id=1, outcome_id=oid, probability=value, kind="price",
            recv_wall=1000 + n, recv_mono=100 + n, venue_ts_ms=None,
            event_ordinal=n,
        )
        for n, (oid, value) in enumerate(p.ns["price_buffer"].items(), 1)
    }
    x.r.receipts = p.ns["tail_receipts"] = blend.TailReceipts("polymarket")
    p.ns["blend_refresher"] = x.r
    p.ns["logger"] = blend.logger
    withdraw = p.ns["withdraw_book_refuted_prices"]
    arrivals = [0]

    async def churning(session, selected):
        rows = await withdraw(session, selected)
        arrivals[0] += 1
        p.books[churn_leg] = (0.01 + 0.0001 * arrivals[0], 0.99)
        return rows

    p.ns["withdraw_book_refuted_prices"] = churning
    attempts = []
    attempt = x.r._refresh_batch

    async def counted(ids, *args, **kwargs):
        attempts.extend(ids)
        return await attempt(ids, *args, **kwargs)

    x.r._refresh_batch = counted
    return p, x, attempts


async def flush(p, n):
    assert await p.ns["flush_prices"](flush_started=1000 + 0.25 * n)
    assert await p.ns["flush_props"](flush_started=1000 + 0.25 * n)
    await p.ns["catalog_boundary"].join_stamps()


async def test_prop_withdrawal_churn_does_not_hold_the_committed_win_stamp(monkeypatch):
    p, x, attempts = game(monkeypatch, churn_leg=PROP)
    await flush(p, 0)
    # Parent: the price committed but event 1 was excluded from every refresh
    # while prop 3 kept drawing books (8 flushes, never stamped).
    assert ("write", [1, 2]) in p.trace and ("withdraw", [PROP]) in p.trace
    assert x.committed == x.published == [1]
    assert attempts == [1]  # once: the prop's withdrawal owes no second stamp
    assert not x.r.pending_event_ids()
    for n in range(1, 4):  # the prop keeps churning; nothing is owed or re-stamped
        await flush(p, n)
    assert attempts == [1] and not x.r.pending_event_ids()
    assert x.r.stats["errors"] == 0


async def test_speaking_leg_withdrawal_still_holds_the_stamp(monkeypatch):
    # Control, unchanged: a pending withdrawal on a leg the blend reads keeps
    # the event owed instead of stamping a board that withdrawal will change.
    p, x, attempts = game(monkeypatch, churn_leg=WIN)
    for n in range(3):
        await flush(p, n)
    assert ("withdraw", [WIN]) in p.trace
    assert 1 not in x.committed and attempts == []
    assert 1 in x.r.pending_event_ids()


async def test_quiet_game_prop_withdrawal_releases_owed_debt(monkeypatch):
    # The quiet-flush path reads the same exclusion: owed WIN debt is stamped
    # while a prop keeps drawing wide books, with no new price in the batch.
    p, x, attempts = game(monkeypatch, churn_leg=PROP, batch={})
    x.r.adopt_pending([1])
    await flush(p, 0)
    assert ("withdraw", [PROP]) in p.trace
    assert x.committed == x.published == [1] and attempts == [1]
    assert not x.r.pending_event_ids()


@pytest.mark.parametrize("prop_quotes", [False, True])
async def test_win_stamp_publishes_before_an_unrelated_later_chunk(monkeypatch, prop_quotes):
    # Within the flush: the committed pair publishes right after its own chunk,
    # not at the flush's tail behind event 2's held write (where the parent's
    # final arm would at best have reached it). The prop's price and its
    # withdrawal are the props' loop's: neither runs in this flush, and the
    # withdrawal follows the prop's own price there.
    batch = {1: 0.6, 2: 0.4, 900: 0.1}
    if prop_quotes:
        batch.update({3: 0.3, 4: 0.7})
    p, x, attempts = game(
        monkeypatch, churn_leg=PROP, batch=batch, hold_later_chunk=True,
    )
    task = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await asyncio.wait_for(p.entered.wait(), 1)
        await settle_until(lambda: 1 in x.published)
        assert ("withdraw", [PROP]) not in p.trace
        assert not task.done() and 900 in p.ns["price_buffer"]
    finally:
        p.release.set()
        await asyncio.wait_for(task, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert ("withdraw", [PROP]) not in p.trace
    assert not [ids for kind, ids in p.trace if kind == "write" and PROP in ids]
    assert await p.ns["flush_props"](flush_started=1000.25)
    if prop_quotes:
        assert p.trace.index(("write", [3, 4])) < p.trace.index(("withdraw", [PROP]))
    else:
        assert ("withdraw", [PROP]) in p.trace
    await p.ns["catalog_boundary"].join_stamps()
    assert attempts.count(1) == 1 and not x.r.pending_event_ids()


async def test_a_running_win_stamp_does_not_hold_the_next_chunk_for_a_prop_withdrawal(
    monkeypatch,
):
    # The chunk-start join keeps a running stamp's read ahead of that event's
    # next write. A pending prop withdrawal is not such a write for the WIN
    # reading, so event 2's later chunk writes while event 1's stamp is held.
    p, x, attempts = game(monkeypatch, churn_leg=PROP, batch={1: 0.6, 2: 0.4, 900: 0.1})
    held = stamp_rig_block(x)
    task = asyncio.create_task(p.ns["flush_prices"](flush_started=1000))
    try:
        await asyncio.wait_for(held.entered.wait(), 1)  # event 1's stamp is running
        await settle_until(lambda: 2 in x.published)  # event 2 wrote AND stamped
        assert ("write", [900]) in p.trace and 1 not in x.committed
    finally:
        held.release.set()
        await asyncio.wait_for(task, 2)
        await p.ns["catalog_boundary"].join_stamps()
    assert x.published == [2, 1] and not x.r.pending_event_ids()


def stamp_rig_block(x):
    """Hold event 1's stamp inside its transaction until released."""
    entered, release = asyncio.Event(), asyncio.Event()
    attempt = x.r._refresh_batch

    async def held(ids, *args, **kwargs):
        if 1 in ids:
            entered.set()
            await release.wait()
        return await attempt(ids, *args, **kwargs)

    x.r._refresh_batch = held
    return SimpleNamespace(entered=entered, release=release)
