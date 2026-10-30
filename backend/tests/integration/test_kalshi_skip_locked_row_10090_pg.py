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

#10090 class f (`KALSHI_WS_MERGE_LIVE_PHASES`): consecutive live games share
ONE transaction once a phase session has shown the pre-pass, with the same
price and re-rank statements (#10693); a held price row still holds back only
its game; a lock the pre-pass cannot skip splits the merged phase back into
today's per-game phases in the same flush; a cooling game, or a live-aux
board beside a headline, is never merged.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest
from sqlalchemy import text

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


# ── lane1 review R1 (#11797): a foreign-key share lock is not a held row ──────
#
# A snapshot INSERT (`futures_odds_snapshots.outcome_id` → `futures_outcomes.id`)
# takes FOR KEY SHARE on its outcome row until it commits: that is the lock
# PostgreSQL's FK check (RI_FKey_check) takes, held here explicitly. The price
# UPDATE itself takes FOR NO KEY UPDATE, which does not conflict with it, so the
# base per-row Kalshi UPDATE writes straight through such an insert. The SKIP
# LOCKED passes must lock no harder than that UPDATE (as the live EI write does,
# bceb3637): with FOR UPDATE they skip the row — holding back its whole game —
# and, while they hold it, make every concurrent snapshot INSERT wait.


@contextlib.asynccontextmanager
async def _key_sharing(side, outcome_id):
    """An open transaction holding the FK check's lock on one outcome row."""
    conn = await side.connect()
    tx = await conn.begin()
    await conn.execute(
        text("SELECT 1 FROM futures_outcomes WHERE id = :id FOR KEY SHARE"),
        {"id": outcome_id},
    )
    try:
        yield tx
    finally:
        if tx.is_active:
            await tx.rollback()
        await conn.close()


async def _run(side, stmt):
    async with side.connect() as conn:
        tx = await conn.begin()
        await conn.execute(text("SET LOCAL lock_timeout = '300ms'"))
        rows = (await conn.execute(stmt)).all()
        await tx.rollback()
    return rows


async def test_a_key_share_holder_is_not_a_held_row_for_either_venue(pg):
    from app.tasks.polymarket_ws import chunk_price_update_stmt
    from app.utils.kalshi_price_statement import kalshi_skip_locked_stmt

    _, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    a1, a2, b1 = legs["a1"], legs["a2"], legs["b1"]
    chunk = {a1: 0.61, a2: 0.39, b1: 0.62}
    units = {a1: events["a"], a2: events["a"], b1: events["b"]}
    kalshi = [(oid, value, None, None, False) for oid, value in chunk.items()]
    async with _key_sharing(side, a1):
        pm = await _run(side, chunk_price_update_stmt(chunk, skip_units=units))
        assert sorted((r.id, r.skipped) for r in pm) == sorted(
            (oid, False) for oid in chunk
        )
        assert await _run(side, kalshi_skip_locked_stmt(kalshi)) == []
    # Control: a real writer's row lock is still skipped, with its unit.
    async with _holding(side, a1):
        pm = await _run(side, chunk_price_update_stmt(chunk, skip_units=units))
        assert {r.id for r in pm if r.skipped} == {a1, a2}
        assert {r.id for r in pm if not r.skipped} == {b1}
        assert {r.id for r in await _run(side, kalshi_skip_locked_stmt(kalshi))} == {a1}


async def test_the_kalshi_pre_pass_never_makes_a_snapshot_insert_wait(pg):
    from app.utils.kalshi_price_statement import kalshi_skip_locked_stmt

    _, side, ids = pg
    a1 = ids["legs"]["a1"]
    async with side.connect() as writer:
        tx = await writer.begin()
        assert (await writer.execute(kalshi_skip_locked_stmt(
            [(a1, 0.61, None, None, False), (ids["legs"]["b1"], 0.62, None, None, False)]
        ))).all() == []
        # The phase transaction is still open, holding the pre-pass's locks.
        async with side.connect() as other:
            other_tx = await other.begin()
            await other.execute(text("SET LOCAL lock_timeout = '300ms'"))
            await other.execute(
                text("SELECT 1 FROM futures_outcomes WHERE id = :id FOR KEY SHARE"),
                {"id": a1},
            )
            await other_tx.rollback()
        await tx.rollback()


# ── #10090 class f: consecutive live games in ONE transaction ─────────────────
#
# `KALSHI_WS_MERGE_LIVE_PHASES` (here `prices.merge_live_phases`). Production
# 2026-10-30 19:33-19:42Z: the longest Kalshi flush ran 30-46 transactions,
# mostly one live game each, and each paid its checkout and BEGIN+SET before its
# first write. Merged, games A and B (both live) share one transaction once a
# phase session has shown the SKIP LOCKED pre-pass. A held price row still holds
# back only its game; a lock the pre-pass cannot skip (game A's re-rank sibling)
# splits the merged phase back into today's per-game phases in the same flush.


def _live(ns, ids, *, merge):
    """Games A and B live, at production's 0.25 s period, merging or not."""
    ns["live_event_ids"] = set(ids["events"].values())
    ns["flush_period"] = 0.25
    ns["prices"].merge_live_phases = merge
    return ns


@contextlib.contextmanager
def _transactions(engine):
    """COMMITs and statements on the flush's engine while the block runs."""
    from sqlalchemy import event

    seen = {"commits": 0, "sql": []}

    def commit(_conn):
        seen["commits"] += 1

    def statement(_conn, _cursor, sql, *_args):
        seen["sql"].append(" ".join(sql.split()))

    sync = engine.sync_engine
    event.listen(sync, "commit", commit)
    event.listen(sync, "before_cursor_execute", statement)
    try:
        yield seen
    finally:
        event.remove(sync, "commit", commit)
        event.remove(sync, "before_cursor_execute", statement)


def _updates(sql):
    """The price and re-rank UPDATE templates; a re-rank's market list is one
    bind per market, so its length is not part of the template."""
    import re

    return {
        re.sub(r"IN \((\$\d+::INTEGER(, )?)+\)", "IN (<markets>)", s)
        for s in sql if s.startswith("UPDATE futures_outcomes")
    }


def _skip_locks(sql):
    return [s for s in sql if "SKIP LOCKED" in s]


async def test_merged_live_games_share_one_transaction_and_the_pipeline_sql(pg):
    engine, side, ids = pg
    legs = ids["legs"]

    # Off (today): one transaction per live game, no pre-pass on a lone game,
    # on every flush (the second is where an engaged run would merge).
    batch = {legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None)}
    off, _trace, off_stats = _rig(engine, ids, batch)
    _live(off, ids, merge=False)
    with _transactions(engine) as before:
        assert await asyncio.wait_for(off["flush_prices"](), 5) is True
    batch.update({legs["a1"]: (0.75, None, None), legs["b1"]: (0.62, None, None)})
    with _transactions(engine) as again:
        assert await asyncio.wait_for(off["flush_prices"](), 5) is True
    for seen in (before, again):
        assert seen["commits"] == 2 and not _skip_locks(seen["sql"])
    assert not off_stats.get("live_phases_merged") and not batch
    assert not off["prices"].skip_locked_engaged

    # On: the first phase session shows the pre-pass; until then, today's plan.
    batch.update({legs["a1"]: (0.8, None, None), legs["b1"]: (0.65, None, None)})
    on, trace, stats = _rig(engine, ids, batch)
    _live(on, ids, merge=True)
    with _transactions(engine) as warm:
        assert await asyncio.wait_for(on["flush_prices"](), 5) is True
    assert warm["commits"] == 2 and on["prices"].skip_locked_engaged
    assert not stats.get("live_phases_merged")

    batch.update({legs["a1"]: (0.9, None, None), legs["b1"]: (0.55, None, None)})
    with _transactions(engine) as merged:
        assert await asyncio.wait_for(on["flush_prices"](), 5) is True
    assert merged["commits"] == 1  # both games, one transaction
    assert stats["live_phases_merged"] == 1 and stats["errors"] == 0
    assert len(_skip_locks(merged["sql"])) == 1  # the merged phase's pre-pass
    # #10693: the same price and re-rank statements, only fewer transactions.
    assert _updates(merged["sql"]) == _updates(before["sql"]) == _updates(warm["sql"])
    stored = await _prices(side, ids)
    assert stored["a1"][0] == 0.9 and stored["b1"][0] == 0.55 and not batch
    refreshed = {e for t in trace if t[0] == "refresh" for e in t[1]}
    assert set(ids["events"].values()) <= refreshed, trace


async def test_a_held_price_row_in_a_merged_phase_holds_back_only_its_game(pg):
    engine, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    batch = {legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None)}
    ns, trace, stats = _rig(engine, ids, batch)
    _live(ns, ids, merge=True)
    ns["prices"].skip_locked_engaged = True  # an earlier phase session showed it
    seen = _packed(ns)
    ns["live_event_ids"] = set(events.values())  # `_packed` empties it

    async with _holding(side, legs["a1"]) as held:
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
        assert held.is_active
        stored = await _prices(side, ids)
        assert stored["b1"][0] == 0.6 and stored["a1"] == (0.3, 2)
        assert stats["live_phases_merged"] == 1
        assert stats["errors"] == 0 and stats["requeued"] == 0  # no lock wait
        assert seen == [(frozenset({legs["a1"], legs["b1"]}), frozenset({legs["a1"]}))]
        assert stats["price_rows_skipped_locked"] == 1
        assert batch == {legs["a1"]: (0.7, None, None)}  # Q491: still buffered
        refreshed = {e for t in trace if t[0] == "refresh" for e in t[1]}
        assert events["b"] in refreshed and events["a"] not in refreshed, trace

    assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
    assert (await _prices(side, ids))["a1"] == (0.7, 1) and not batch


async def test_a_rerank_lock_timeout_splits_the_merged_phase_back_into_games(pg):
    """Game A's re-rank sibling A2 is held: the pre-pass cannot skip it (A2 is
    not one of the phase's writes), so the merged transaction times out. Its
    games then take today's per-game phases in the same flush: A times out on
    its own exactly as before, B commits."""
    engine, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    batch = {legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None)}
    ns, trace, stats = _rig(engine, ids, batch)
    _live(ns, ids, merge=True)
    ns["prices"].skip_locked_engaged = True

    async with _holding(side, legs["a2"]) as held:
        with _transactions(engine) as seen:
            assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
        assert held.is_active
        stored = await _prices(side, ids)
        assert stored["b1"][0] == 0.6  # B committed in this same flush
        assert stored["a1"] == (0.3, 2) and stored["a2"] == (0.5, 1)
        assert stats["live_merge_split"] == 1 and stats["live_phases_merged"] == 1
        # Today's per-game result for A: one lock-timeout error, its one row kept.
        assert stats["errors"] == 1 and stats["requeued"] == 1
        assert batch == {legs["a1"]: (0.7, None, None)}
        assert seen["commits"] == 1  # only B's own phase committed
        assert legs["a1"] in ns["prices"].lock_retry_until  # A's ordinary cooldown
        assert legs["b1"] not in ns["prices"].lock_retry_until
        refreshed = {e for t in trace if t[0] == "refresh" for e in t[1]}
        assert events["b"] in refreshed and events["a"] not in refreshed, trace


async def test_a_cooling_game_or_another_class_is_never_merged(pg):
    """A game in its lock-retry cooldown keeps its own turn (today's skip);
    the fresh game is not merged with it and still commits. Nor is a live-aux
    phase merged into a headline phase: every headline still goes first."""
    engine, side, ids = pg
    legs = ids["legs"]
    batch = {legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None)}
    ns, _trace, stats = _rig(engine, ids, batch)
    _live(ns, ids, merge=True)
    ns["prices"].skip_locked_engaged = True
    from app.tasks.live_blend_refresh import _mono

    ns["prices"].lock_retry_until[legs["b1"]] = _mono() + 60
    with _transactions(engine) as seen:
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
    assert not stats.get("live_phases_merged") and seen["commits"] == 1
    assert not _skip_locks(seen["sql"])  # A alone: today's lone-game phase
    stored = await _prices(side, ids)
    assert stored["a1"][0] == 0.7 and stored["b1"][0] == 0.5
    assert batch == {legs["b1"]: (0.6, None, None)}

    # Another class: B's leg is its game's live-aux board, A's a headline.
    ns["prices"].lock_retry_until.clear()
    ns["prices"].headline_aux_outcome_ids = {legs["b1"]}
    batch[legs["a1"]] = (0.72, None, None)
    with _transactions(engine) as seen:
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
    assert not stats.get("live_phases_merged") and seen["commits"] == 2
    stored = await _prices(side, ids)
    assert stored["a1"][0] == 0.72 and stored["b1"][0] == 0.6 and not batch


async def test_a_game_whose_stamp_still_runs_is_never_merged(pg):
    """B's previous stamp is still running (the same-event fence): today B
    stays buffered at the head of the next flush; merged, it must not ride
    A's transaction instead."""
    engine, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    batch = {legs["a1"]: (0.7, None, None), legs["b1"]: (0.6, None, None)}
    ns, _trace, stats = _rig(engine, ids, batch)
    _live(ns, ids, merge=True)
    prices = ns["prices"]
    prices.skip_locked_engaged = True
    release = asyncio.Event()
    prices.stamping = asyncio.create_task(release.wait())
    prices.stamping_events = {events["b"]}

    flush = asyncio.create_task(ns["flush_prices"]())
    try:
        async with asyncio.timeout(5):
            while (await _prices(side, ids))["a1"][0] != 0.7:
                await asyncio.sleep(0.01)
        assert (await _prices(side, ids))["b1"][0] == 0.5  # fenced, not merged
    finally:
        release.set()
        assert await asyncio.wait_for(flush, 5) is True
    assert not stats.get("live_phases_merged") and stats["stamp_fenced"] >= 1
    assert batch == {legs["b1"]: (0.6, None, None)} and stats["errors"] == 0
