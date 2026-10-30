"""#10090 — one locked Kalshi price row holds back only its own game. Real Postgres.

## the ship

Live games' Kalshi prices stop freezing for minutes when another transaction
holds a lock on one row of the same flush phase. Production v5973
(2026-10-30 15:35:39-15:36:00Z): `flush error (178-200 updates retained for
retry)` x7 — one held row rolled back every game packed beside it.

## what this proves, against a real row lock

The #10661 rig: the SHIPPED `flush_prices` (AST, compiled against
`app.tasks.kalshi_ws`'s globals) on the real `get_task_session`, the real
price pipeline and UPDATEs, the real re-rank and the real refresher's due/debt
bookkeeping (blend SQL and Redis recorded). The run's non-live plan
(`live_event_ids` set) packs games A and B, and the unrelated contract, as it
does in production. A second connection holds game A's PRICE row.

* ``test_one_held_row_holds_back_only_its_game_in_the_same_phase``: the phase
  holding both games commits game B (and the contract) while A's row is still
  held — no lock wait, no error, no requeue; A's tick stays buffered (Q491),
  unwritten and unstamped; the skip is counted. After release the next flush
  writes A and stamps it.
* ``test_a_lone_held_game_keeps_its_waiting_refusal``: a phase of ONE game is
  unchanged — it still waits its lock budget and is retained, as before.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.test_kalshi_price_lock_budget_pg_10661 import (  # noqa: F401
    DB_URL,
    _holding,
    _prices,
    _rig,
    pg,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set BLEND_DEADLOCK_DATABASE_URL (CI job `database-integration`)",
    ),
]


def _packed(ns):
    """The run's non-live plan: games packed into shared phases (production)."""
    ns["live_event_ids"] = set()
    seen = []
    owner = ns["prices"]
    inner = getattr(owner, "skip_locked", None)
    if inner is None:  # the parent has no pre-pass; its behaviour is asserted
        return seen

    async def recorded(session, phase, **kwargs):
        skipped = await inner(session, phase, **kwargs)
        seen.append((frozenset(phase), frozenset(skipped)))
        return skipped

    owner.skip_locked = recorded
    return seen


async def test_one_held_row_holds_back_only_its_game_in_the_same_phase(pg):
    engine, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    batch = {
        legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None),
        legs["x1"]: (0.4, None, None),
    }
    ns, trace, stats = _rig(engine, ids, batch)
    seen = _packed(ns)

    async with _holding(side, legs["a1"]) as held:
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
        assert held.is_active  # all of this happened while A1 was held
        stored = await _prices(side, ids)
        assert stored["b1"][0] == 0.6 and stored["x1"][0] == 0.4
        assert stats["errors"] == 0 and stats["requeued"] == 0  # no lock wait
        assert stored["a1"] == (0.3, 2)  # unwritten, rank untouched
        assert batch == {legs["a1"]: (0.7, None, None)}  # Q491: still buffered
        # Games A and B shared one phase; only A was held back.
        assert any(
            {legs["a1"], legs["b1"]} <= phase and skipped == {legs["a1"]}
            for phase, skipped in seen
        ), seen
        assert stats["price_rows_skipped_locked"] == 1
        refreshed = [t[1] for t in trace if t[0] == "refresh"]
        assert any(events["b"] in r for r in refreshed), trace
        assert not any(events["a"] in r for r in refreshed), trace
        assert not ns["prices"].lock_retry_until  # no cooldown on the held row

    # Released: the next flush writes A and stamps it.
    assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
    stored = await _prices(side, ids)
    assert stored["a1"] == (0.7, 1) and stored["a2"] == (0.5, 2)
    assert not batch
    assert any(t[0] == "refresh" and events["a"] in t[1] for t in trace), trace
    assert stats["errors"] == 0


async def test_a_lone_held_game_keeps_its_waiting_refusal(pg):
    engine, side, ids = pg
    legs = ids["legs"]
    batch = {legs["a1"]: (0.7, None, None)}
    ns, trace, stats = _rig(engine, ids, batch)
    seen = _packed(ns)

    async with _holding(side, legs["a1"]):
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
        assert seen == []  # one game: no SKIP LOCKED pass
        assert stats["errors"] == 1 and stats["requeued"] == 1
        assert batch == {legs["a1"]: (0.7, None, None)}
        assert not stats.get("price_rows_skipped_locked")


async def _skipped(engine, side, rows, *, held):
    """`kalshi_skip_locked_stmt(rows)` while `held` rows are locked elsewhere."""
    from sqlalchemy import text

    from app.utils.kalshi_price_statement import kalshi_skip_locked_stmt

    holder = await side.connect()
    hold = await holder.begin()
    for oid in held:
        await holder.execute(
            text("SELECT id FROM futures_outcomes WHERE id = :id FOR UPDATE"), {"id": oid}
        )
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
                result = await conn.execute(kalshi_skip_locked_stmt(rows))
                return {row.id for row in result.all()}
    finally:
        await hold.rollback()
        await holder.close()


async def test_the_pre_pass_skips_only_rows_the_updates_would_write(pg):
    from sqlalchemy import text

    engine, side, ids = pg
    legs = ids["legs"]
    async with side.begin() as conn:  # a2 was just observed at its stored price
        await conn.execute(
            text("UPDATE futures_outcomes SET last_updated = now() WHERE id = :id"),
            {"id": legs["a2"]},
        )
        await conn.execute(  # x1's stamp is past the 30 s liveness refresh
            text(
                "UPDATE futures_outcomes SET last_updated = now() - interval '1 hour' "
                "WHERE id = :id"
            ),
            {"id": legs["x1"]},
        )
    every = list(legs.values())
    rows = [
        (legs["a1"], 0.7, None, None, False),        # changed
        (legs["a2"], 0.5, None, None, False),        # unchanged, fresh: no write
        (legs["b1"], 0.6, 0.55, 0.65, False),        # changed, full book
        (legs["b_settled"], 0.2, None, None, True),  # settled: refused even forced
        (legs["x1"], 0.5, None, None, False),        # unchanged but due liveness
    ]
    skipped = await _skipped(engine, side, rows, held=every)
    # The same predicate as the per-row UPDATE: an unchanged, freshly stamped
    # row and a settled one are never lock candidates, so never "skipped".
    assert skipped == {legs["a1"], legs["b1"], legs["x1"]}
    # Forced (a held quote's landing write / a first observation) it is wanted.
    rows[1] = (legs["a2"], 0.5, None, None, True)
    assert legs["a2"] in await _skipped(engine, side, rows, held=every)
    # Nothing held: nothing skipped.
    assert await _skipped(engine, side, rows, held=[]) == set()


async def test_the_final_drain_waits_for_a_held_row_and_never_skips(pg):
    """The drain has no next flush: a held game is waited for, never skipped."""
    from tests.integration.test_kalshi_price_lock_budget_pg_10661 import _wait_for_a_lock_wait

    engine, side, ids = pg
    legs = ids["legs"]
    batch = {legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None)}
    ns, _trace, stats = _rig(engine, ids, batch)
    seen = _packed(ns)

    async with _holding(side, legs["a1"]) as held:
        task = asyncio.create_task(ns["drain_prices"]())
        await _wait_for_a_lock_wait(side)  # it waits on the row
        await asyncio.sleep(0.3)
        assert not task.done()
        await held.rollback()
        await asyncio.wait_for(task, 5)
    assert seen == [] and not stats.get("price_rows_skipped_locked")
    assert stats["final_flush_dropped"] == 0 and not batch
    stored = await _prices(side, ids)
    assert stored["a1"][0] == 0.7 and stored["b1"][0] == 0.6
