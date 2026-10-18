"""#10090 — a held quote whose first stamp the refresh floor deferred is
re-admitted as ordinary stamp debt, so the latest owed probability reaches the
headline while its price row stays locked. Only a moved quote is fresh; the
floor and the old-work budgets are kept (Root attempt49 candidate2, attempt51)."""

import pytest
from app.tasks.live_blend_refresh import FRESH_FLUSH_PENDING_ATTEMPTS
from tests.test_ws_flush_cadence_10090 import _Recording
from tests.test_kalshi_held_quotes_10090 import (
    Clock,
    held_rig,
    EVENT,
    PERIOD,
    writes_of,
)


async def setup_held(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch)
    await x.flush(flush_started=clock.t)
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    await x.prices.join_stamp(x.ns["blend_refresher"])
    r = _Recording(min_refresh_interval_s=PERIOD)
    r.held_quotes = x.held
    x.ns["blend_refresher"] = r
    return clock, x, r


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate", [None, "mismatched_mark", "settled"])
async def test_floor_deferred_held_quote_progresses_without_new_input(
    monkeypatch, invalidate
):
    clock, x, r = await setup_held(monkeypatch)
    deadline = dict(x.prices.lock_retry_until)
    r._last_refresh_at[EVENT] = clock.t + 0.1
    clock.t += PERIOD
    x.tick(1, 0.65)
    await x.flush(flush_started=clock.t)
    await x.prices.join_stamp(r)
    assert r.pending_event_ids() == {EVENT}
    assert r.batches == [], "actual refresher floor must defer this quote"
    if invalidate == "mismatched_mark":
        x.batch[1] = (0.66, None, None)
    elif invalidate == "settled":
        x.prices.settled_market_ids.add(10)
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    await x.prices.join_stamp(r)
    assert writes_of(x, 1) == 2 and x.prices.lock_retry_until == deadline
    assert not x.committed
    if invalidate:
        assert r.batches == []
        assert r.pending_event_ids() == {EVENT}
    else:
        assert r.batches == [([EVENT], clock.t)]
        assert not r.pending_event_ids()
        clock.t += PERIOD
        await x.flush(flush_started=clock.t)
        await x.prices.join_stamp(r)
        assert len(r.batches) == 1, "paid unchanged quotes do not restamp"


@pytest.mark.asyncio
async def test_unchanged_held_lock_retry_keeps_spent_pending_budget(monkeypatch):
    clock, x, r = await setup_held(monkeypatch)
    clock.t += PERIOD
    # Real fresh work in this flush; its old-work allowance has been spent.
    await r.refresh([999], flush_started=clock.t)
    r._lock_retry.add(EVENT)
    r._pending_attempts = FRESH_FLUSH_PENDING_ATTEMPTS
    assert r._pending_fresh_flush
    await x.flush(flush_started=clock.t)
    await x.prices.join_stamp(r)
    assert r.batches == [([999], clock.t)], "old held debt must not become fresh"
    assert EVENT in r.pending_event_ids()
    clock.t += PERIOD
    await x.flush(flush_started=clock.t)
    await x.prices.join_stamp(r)
    assert r.batches[-1] == ([EVENT], clock.t), "quiet next flush pays valid debt"
    assert not r.pending_event_ids()
    assert writes_of(x, 1) == 2 and not x.committed
