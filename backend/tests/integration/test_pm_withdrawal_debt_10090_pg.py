"""#10090 — a withdrawn PM contribution leaves the page through contention,
cancellation and restart, on real PostgreSQL.

## the ship

A reader holding a live event page sees a withdrawn Polymarket price leave
the headline and the reloaded chart, even when the event row is held, the
removal is cut off, or the worker restarts between the two commits.

## the mechanism

The price withdrawal commits on its own, so it never waits on the event row
(attempt85); the source removal follows in a second transaction. Each
withdrawn leg of a live event is also a row in `owed_chart_points` under
`PM_WITHDRAWAL_DEBT_SOURCE`, inserted in the withdrawal's transaction and
deleted in the removal's (`PMWithdrawalDebt`). A leg another writer withdrew
first is admitted only with a fresh wide book and a `price_changed_at` after
the observation the source carries (`PMWithdrawalDebt.strays`).

## the rig

#10090's release-wake rig (`test_pm_stamp_release_wake_10090_pg.build`): the
SHIPPED flush closures, `write_chunk` and `withdraw_book_refuted_prices` on the
consumer's own pool, real `LiveBlendRefresher` stamps, and frames a recording
Redis acknowledges only after an independent connection reads the committed
events row back — an invalidation only once the source is gone.

## what is asserted

* a withdrawal removes the source once, writes one retirement vertex and
  settles its row;
* R-A: a removal the held event row refuses keeps the committed leg; the retry
  that finds the price already NULL still returns it, so the event re-stamps
  from its other leg;
* R-B: a removal lost with its process is recovered from its row by a new
  run with no book and no catalog entry for the leg; a withdrawal whose
  commit landed but whose acknowledgement was cancelled is recovered by the
  same run's next flush, again with no book; a price the REST poll
  withdrew first is removed once on the next wide book, and a replay (same
  run or a new one) writes nothing more;
* an ordinary stored NULL without a book, and a NULL whose book arrives but
  whose change predates the stamped basis, are never removed;
* the real newer-overlay interleaving: a held quote's newer basis, then a wide
  book, then release — the flush writes the held price first and removes it
  after, so the older-observation refusal is never what decides.

Synthetic rows on one machine: order and coherence, not production timing.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.models.models import FuturesOutcome
from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
)
from tests.integration.test_pm_held_price_row_stamps_received_quote_11138_pg import (
    hold_price_row,
    wire_held_quotes,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (  # noqa: F401
    _Pool,
    build,
    consumer,
    hold_event_row,
    wait_for,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

EVENT = OUTCOME = 1
AWAY = 101
#: Wide, and its ask is below every held price these cases store: refuted.
WIDE = (0.05, 0.45)


async def setup(rig, consumer, monkeypatch, *, away_leg=False):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    if away_leg:  # market 1's other leg, not yet priced
        async with rig.maker() as session:
            session.add(FuturesOutcome(
                id=AWAY, market_id=1, external_id="away-1", name="Miami Marlins",
                current_probability=None, rank=2,
                last_updated=datetime.now(timezone.utc),
            ))
            await session.commit()
        t.p.ns["event_id_by_outcome"][AWAY] = EVENT
        t.p.ns["market_by_outcome"][AWAY] = 1
    t.p.ns["withdraw_book_refuted_prices"] = pm.withdraw_book_refuted_prices
    t.r.withdrawal_debt = pm.PMWithdrawalDebt()
    t.invalidations = []

    async def sink(payload):
        async with rig.engine.connect() as conn:
            if "outcome_ids" in payload:
                return
            eid = payload["event_id"]
            row = (await conn.execute(
                text(
                    "SELECT win_probability_sources, win_probability_sources_rev "
                    "FROM events WHERE id = :id"
                ),
                {"id": eid},
            )).one()
            assert row.win_probability_sources_rev == payload["rev"][str(eid)]
            if payload.get("invalidation"):
                # Only a committed removal can be acknowledged.
                assert "polymarket" not in row.win_probability_sources
                t.invalidations.append((eid, payload["rev"][str(eid)]))
                return
            stored = row.win_probability_sources["polymarket"]["value"]
            assert stored == payload["source_value"]
            t.pubs.append((0.0, eid, stored, payload["rev"][str(eid)]))

    client = SimpleNamespace(connection_pool=_Pool(sink))
    t.r._client = lambda: client
    return t


async def flush(t):
    """One untimed flush, then every stamp it started."""
    t.flush_starts.append(None)  # the rig's write recorder reads it
    result = await t.p.ns["flush_prices"](flush_started=None)
    await t.boundary.join_stamps()
    return result


async def prime(t, value=0.6):
    t.accept(OUTCOME, value)
    assert await flush(t) is True
    await wait_for(lambda: any(e == EVENT and v == value for _, e, v, _ in t.pubs))


async def state(rig):
    async with rig.engine.connect() as conn:
        price = await conn.scalar(
            text("SELECT current_probability FROM futures_outcomes WHERE id = :id"),
            {"id": OUTCOME},
        )
        sources = await conn.scalar(
            text("SELECT win_probability_sources FROM events WHERE id = :id"),
            {"id": EVENT},
        )
        owed = await conn.scalar(
            text("SELECT count(*) FROM owed_chart_points WHERE source = :s"),
            {"s": pm.PM_WITHDRAWAL_DEBT_SOURCE},
        )
        vertices = await conn.scalar(
            text(
                "SELECT count(*) FROM win_prob_snapshots WHERE event_id = :id "
                "AND source = 'polymarket' AND home_win_probability IS NULL "
                "AND (game_state->>'live_source_withdrawal')::boolean IS TRUE"
            ),
            {"id": EVENT},
        )
    return SimpleNamespace(
        price=None if price is None else float(price),
        source=sources.get("polymarket"), owed=owed, vertices=vertices,
    )


def spy_withdrawals(t):
    returned = []
    shipped = t.p.ns["flush_withdrawals"]

    async def recorded(**kwargs):
        result = await shipped(**kwargs)
        returned.append(result)
        return result

    t.p.ns["flush_withdrawals"] = recorded
    return returned


def removed_once(s):
    return s.price is None and s.source is None and s.owed == 0 and s.vertices == 1


async def test_a_withdrawal_removes_the_source_once_and_settles_its_row(
    rig, consumer, monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
    assert await flush(t) is True
    s = await state(rig)
    assert removed_once(s), s
    assert [eid for eid, _ in t.invalidations] == [EVENT]
    assert t.r.withdrawal_debt.owed == {}
    assert OUTCOME not in t.p.ns["withdraw_buffer"]


async def test_a_held_removal_keeps_the_committed_leg_and_its_retry_returns_it(
    rig, consumer, monkeypatch,
):
    """R-A. Pass 1: the price withdrawal commits; PM has no other leg, so the
    removal needs the event row, which a holder keeps past its lock budget.
    The away leg is then priced by another writer (the REST poll), with no
    stamp of this run. Pass 2 finds the home price already NULL and the
    removal refused (PM still speaks): the owed leg must still be returned,
    or nothing re-stamps the event and it keeps the withdrawn leg's value."""
    t = await setup(rig, consumer, monkeypatch, away_leg=True)
    await prime(t)
    before = (await state(rig)).source
    assert list(before["observed_basis"]) == [OUTCOME_KEY]
    returned = spy_withdrawals(t)
    conn, tx, _pid = await hold_event_row(rig, EVENT)
    try:
        t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
        await flush(t)
        held = await state(rig)
        assert held.price is None and held.owed == 1, held
        assert held.source == before  # the removal never committed
        assert returned[-1] == []
    finally:
        await tx.rollback()
        await conn.close()
    async with rig.engine.begin() as other_writer:
        await other_writer.execute(text(
            "UPDATE futures_outcomes SET current_probability = 0.35, "
            "last_updated = now(), price_changed_at = now() WHERE id = :id"
        ), {"id": AWAY})
    await asyncio.sleep(0.3)  # the removal's retry cooldown
    assert await flush(t) is True
    assert returned[-1] == [OUTCOME]
    s = await state(rig)
    assert s.owed == 0 and s.vertices == 0, s  # the away leg still speaks
    assert s.source is not None
    assert list(s.source["observed_basis"]) == [str(AWAY)], s.source
    assert s.source["value"] == pytest.approx(0.65)
    assert t.invalidations == []


async def test_a_removal_lost_with_its_process_is_recovered_from_its_row(
    rig, consumer, monkeypatch,
):
    """R-B. The removal dies after the withdrawal committed (as a SIGKILL or a
    cancelled acknowledgement leaves it). A new run — empty memory, no book,
    no catalog entry for the leg — removes the source from the row alone."""
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    shipped = pm.withdraw_attributed_event_sources

    async def died(*_a, **_kw):
        raise RuntimeError("process gone before the removal committed")

    monkeypatch.setattr(pm, "withdraw_attributed_event_sources", died)
    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
    assert await flush(t) is False
    lost = await state(rig)
    assert lost.price is None and lost.owed == 1 and lost.source is not None, lost

    monkeypatch.setattr(pm, "withdraw_attributed_event_sources", shipped)
    t.r.withdrawal_debt = pm.PMWithdrawalDebt()
    t.p.ns["withdraw_buffer"].clear()
    t.p.ns["event_id_by_outcome"].pop(OUTCOME)
    returned = spy_withdrawals(t)
    assert await flush(t) is True
    assert OUTCOME in returned[-1]
    s = await state(rig)
    assert removed_once(s), s
    assert [eid for eid, _ in t.invalidations] == [EVENT]


async def test_a_cancelled_commit_acknowledgement_is_recovered_by_the_same_run(
    rig, consumer, monkeypatch,
):
    """R-B's ambiguous commit. The price withdrawal and its owed row commit,
    then cancellation lands on the commit's await, so this run's memory never
    adopts the debt. The next flush — same run, no new book — re-reads the row
    and removes the source; a run that trusted memory alone would wait for a
    restart or a book that may never come."""
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = t.r.withdrawal_debt
    armed = {"on": False, "fired": False}
    shipped_record = debt.record

    async def record(session, rows):
        recorded = await shipped_record(session, rows)
        armed["on"] = bool(recorded)
        return recorded

    debt.record = record
    shipped_sessions = t.p.ns["get_task_session"]

    @contextlib.asynccontextmanager
    async def sessions(*args, **kwargs):
        async with shipped_sessions(*args, **kwargs) as session:
            yield session
        if armed["on"] and not armed["fired"]:
            armed["fired"] = True
            raise asyncio.CancelledError  # committed; the acknowledgement was not

    t.p.ns["get_task_session"] = sessions
    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
    with pytest.raises(asyncio.CancelledError):
        await flush(t)
    assert armed["fired"]
    cut = await state(rig)
    assert cut.price is None and cut.owed == 1 and cut.source is not None, cut
    assert debt.owed == {}  # memory never adopted it

    t.p.ns["withdraw_buffer"].clear()  # no new book
    returned = spy_withdrawals(t)
    assert await flush(t) is True
    assert OUTCOME in returned[-1]
    s = await state(rig)
    assert removed_once(s), s
    assert [eid for eid, _ in t.invalidations] == [EVENT]


async def test_a_price_the_rest_poll_withdrew_first_is_removed_once_on_a_wide_book(
    rig, consumer, monkeypatch,
):
    """R-B's REST-first entrance (#9399's game arm), then replays."""
    from app.tasks.polymarket import _withdraw_book_refuted_legs

    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    async with rig.maker() as session:
        assert await _withdraw_book_refuted_legs(session, 1, {"home-1": WIDE}) == 1
        await session.commit()
    rest = await state(rig)
    assert rest.price is None and rest.source is not None and rest.owed == 0

    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
    assert await flush(t) is True
    assert removed_once(await state(rig))
    assert len(t.invalidations) == 1

    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE  # the same run, a repeat book
    assert await flush(t) is True
    t.r.withdrawal_debt = pm.PMWithdrawalDebt()  # a new run's resubscribe
    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
    assert await flush(t) is True
    assert removed_once(await state(rig))
    assert len(t.invalidations) == 1


async def test_an_ordinary_null_without_a_book_is_never_removed(
    rig, consumer, monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    async with rig.engine.begin() as conn:
        await conn.execute(text(
            "UPDATE futures_outcomes SET current_probability = NULL, "
            "price_changed_at = now() WHERE id = 1"
        ))
    for _ in range(2):
        assert await flush(t) is True
    s = await state(rig)
    assert s.source is not None and s.vertices == 0 and s.owed == 0, s
    assert t.invalidations == []


async def test_a_null_whose_change_predates_the_stamped_basis_is_never_removed(
    rig, consumer, monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    basis = (await state(rig)).source["observed_basis"][OUTCOME_KEY]
    before = datetime.fromtimestamp(basis, timezone.utc) - timedelta(seconds=1)
    async with rig.engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE futures_outcomes SET current_probability = NULL, "
                "price_changed_at = :at WHERE id = 1"
            ),
            {"at": before},
        )
    t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
    assert await flush(t) is True
    s = await state(rig)
    assert s.source is not None and s.vertices == 0 and s.owed == 0, s
    assert t.invalidations == []


async def test_the_real_newer_overlay_interleaving_writes_then_removes(
    rig, consumer, monkeypatch,
):
    """A held quote stamps a basis newer than the stored row (#11138); a wide
    book then releases it and queues the withdrawal. While the price row is
    held, the withdrawal waits with its event; after release the flush writes
    the held price first and withdraws THAT, so the removal owns the newest
    observation and the older-observation refusal never decides."""
    t = await setup(rig, consumer, monkeypatch)
    held = await wire_held_quotes(t, consumer)
    await prime(t)
    # The held quote's flush starts one refresher floor after prime's stamp,
    # as the real cadence would (`min_refresh_interval_s=PERIOD`). Called
    # back to back, the held write returns within its 1-50 ms lock budget and
    # its stamp lands inside the floor: owed, never run, because nothing else
    # flushes (CI 2 of 2 on 7c297/f82; locally the gap was 0.26-0.37 s against
    # the 0.25 s floor, so it passed by tens of milliseconds).
    await asyncio.sleep(max(
        0.0,
        t.r._last_refresh_at[EVENT] + t.r.min_refresh_interval_s - blend._mono(),
    ))
    conn, tx = await hold_price_row(rig, OUTCOME)
    try:
        t.accept(OUTCOME, 0.65)
        await flush(t)
        # Preconditions, named so a recurrence says what it is: #11138 orders a
        # held quote only after a DB-clock sample that completed within its
        # bound. A sample that timed out (a contended database) leaves the
        # quote unordered and nothing to overlay; that is not this property.
        assert held.sample_failures == 0, (
            f"precondition: {held.sample_failures} DB-clock sample(s) timed out"
        )
        assert held._quotes.get(OUTCOME, (None,))[0] == 0.65, "quote not held"
        assert EVENT not in t.r._throttle_deferred, (
            "precondition: the held quote's stamp fell inside the refresher floor"
        )
        await wait_for(lambda: any(v == 0.65 for _, e, v, _ in t.pubs if e == EVENT))
        overlay = await state(rig)
        assert overlay.price == 0.6 and overlay.source["value"] == 0.65
        stored_at = await conn.scalar(text(
            "SELECT extract(epoch FROM last_updated) FROM futures_outcomes WHERE id = 1"
        ))
        assert overlay.source["observed_basis"][OUTCOME_KEY] > float(stored_at)
        # `handle_book`'s wide arm: queue the withdrawal, release the held quote.
        t.p.ns["withdraw_buffer"][OUTCOME] = WIDE
        held.release([OUTCOME])
        await flush(t)
        waiting = await state(rig)
        assert waiting.price == 0.6 and waiting.source is not None, waiting
        assert waiting.owed == 0 and waiting.vertices == 0
    finally:
        await tx.rollback()
        await conn.close()
    for _ in range(20):
        await asyncio.sleep(0.05)
        await flush(t)
        if (await state(rig)).source is None:
            break
    s = await state(rig)
    assert removed_once(s), s
    assert [eid for eid, _ in t.invalidations] == [EVENT]


OUTCOME_KEY = str(OUTCOME)
