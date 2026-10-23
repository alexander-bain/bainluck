"""#10090 — a held quote the refresh floor deferred is still stamped, on real PostgreSQL.

## the ship

The latest owed held probability reaches the headline and chart under real
database contention without becoming fresh debt. While a foreign transaction
holds the Kalshi price row, a changed quote whose first stamp the refresher's
floor deferred is stamped at the NEXT flush with no new input — it does not
wait for the row lock to clear.

## the rig

`test_kalshi_held_price_row_10090_pg`'s: the SHIPPED `flush_prices` closure on
the consumer's pooled engine with a REAL `LiveBlendRefresher("kalshi")`, inputs
accepted as `handle_ticker` accepts them, and a second connection holding
`SELECT ... FOR UPDATE` on the home leg's price row. The refresher's monotonic
clock is driven by hand so the floor is deterministic.

## what is asserted

On the next flush after the floor deferred .70, with no new input:

* the headline is .70 while the price row still stores .60;
* no extra price-write attempt and `lock_retry_until` unchanged (the owed
  stamp does not re-spend the held write);
* the refresher's pending set is empty and a frame carries .70.

Not asserted here: whether the owed stamp is queued as fresh or as ordinary
debt. Queuing it as fresh still lands .70 on this rig; that budget split is
guarded by the unit file `test_kalshi_owed_held_budget_49.py`.

On #11208's source (27e15c9c51) the unchanged quote stays fenced out until the
lock clears, so the headline stays .65 and this case fails.

Synthetic rows on one machine: ordering and durability, not production timing.
"""

from __future__ import annotations

import pytest

from tests.integration.test_kalshi_held_price_row_10090_pg import (  # noqa: F401
    AWAY,
    DB_URL,
    EVENT,
    HOME,
    PERIOD,
    hold_row,
    rig,
    started,
    stored,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


async def test_a_floor_deferred_held_quote_is_stamped_next_flush_while_the_row_stays_locked(
    rig, monkeypatch
):
    from app.tasks import live_blend_refresh

    clock = [1000.0]
    monkeypatch.setattr(live_blend_refresh, "_mono", lambda: clock[0])
    c, _ = await started(rig)
    conn, tx = await hold_row(rig, HOME)
    try:
        # Held from the first attempt: .65 is stamped through the overlay.
        c.accept(HOME, 0.65)
        c.accept(AWAY, 0.35)
        assert await c.flush() is True
        clock[0] += PERIOD
        assert await c.flush() is True
        attempts = len(c.attempts)
        deadline = dict(c.prices.lock_retry_until)
        assert (await stored(rig)) == (pytest.approx(0.60), pytest.approx(0.65))

        # Arm the floor so the next changed quote's stamp is deferred: the
        # event was "just refreshed" and is not due for another PERIOD.
        c.refresher.min_refresh_interval_s = PERIOD
        c.refresher._last_refresh_at[EVENT] = clock[0] + 0.1
        clock[0] += PERIOD
        c.accept(HOME, 0.70)
        c.accept(AWAY, 0.30)
        assert await c.flush() is True
        assert c.refresher.pending_event_ids() == {EVENT}, "the floor deferred it"
        assert (await stored(rig))[1] == pytest.approx(0.65)

        # Next flush, NO new input, row still locked: the owed quote lands.
        clock[0] += PERIOD
        assert await c.flush() is True
        price, headline = await stored(rig)
        assert price == pytest.approx(0.60), "the price row is still held"
        assert headline == pytest.approx(0.70), (price, headline)
        assert not c.refresher.pending_event_ids()
        assert len(c.attempts) == attempts, "no extra price-write attempt"
        assert c.prices.lock_retry_until == deadline, "the retry deadline is untouched"
        assert any(
            f.get("event_id") == EVENT and f.get("source_value") == pytest.approx(0.70)
            for f in c.frames
        ), "a frame carries the owed quote"
    finally:
        await tx.rollback()
        await conn.close()
        c.close()
