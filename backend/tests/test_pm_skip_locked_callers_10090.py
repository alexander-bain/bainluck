"""#10090 — every caller of `write_chunk` treats held-back units as lock-held.

A committed chunk may now return `skipped_ids`: units a row lock elsewhere
held back while the rest committed (`chunk_price_update_stmt(skip_units=)`).
For those rows, and only those, each caller keeps exactly what a refused
(None) chunk keeps:

* the game flush: an event split across chunks is never stamped from a board
  its held legs have not reached (no torn stamp);
* the game flush: a held unit is never acknowledged as an unchanged
  observation (the DNPL preview's continuity bypass);
* the bridged writer: a held event is not handed back as committed work;
* the props loop: a held question's withdrawal waits for its price.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.tasks import polymarket_ws as pm
from app.tasks.polymarket_open_contracts import plan_flush_chunks
from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions
from tests.test_ws_flush_cadence_10090 import _FakeTime

pytestmark = pytest.mark.asyncio


async def test_an_event_split_across_chunks_is_not_stamped_while_its_held_legs_wait(
    monkeypatch,
):
    # Event 10's legs 1, 2 share chunk 1 with event 90 (two units); its leg 3
    # is chunk 2's. Row 1 is held: 1 and 2 are held back, 900 and 3 commit.
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(
        clock, batch={1: 0.6, 2: 0.4, 900: 0.7, 3: 0.8},
        mapping={1: 10, 2: 10, 3: 10, 900: 90}, books={},
    )
    r.ns["FLUSH_CHUNK_ROWS"] = 3
    r.ns["open_outcome_ids"] = set()
    pending, admitted = {10, 90}, []
    original = r.ns["blend_refresher"]

    class Refresher:
        publish_market_changes = original.publish_market_changes

        def pending_event_ids(self):
            return frozenset(pending)

        async def refresh(self, ids, **kwargs):
            due = (set(ids) | pending) - set(kwargs.get("defer_event_ids", ()))
            admitted.append(due)
            pending.difference_update(due)
            await original.refresh(ids, **kwargs)

        async def refresh_pending(self, **kwargs):
            await self.refresh(set(), **kwargs)

    r.ns["blend_refresher"] = Refresher()
    assert await r.ns["flush_prices"](flush_started=1000)
    assert state.attempts == [(1000, (1, 2, 900)), (1000, (3,))]
    assert state.commits == [900, 3]
    # Leg 3 committed, but legs 1 and 2 are still unwritten: event 10 is
    # never due, so no stamp reads its half-written board. Event 90 is.
    assert all(10 not in due for due in admitted), admitted
    assert any(90 in due for due in admitted), admitted
    assert pending == {10}

    state.held = False
    clock.t = 1001
    assert await r.ns["flush_prices"](flush_started=1001)
    assert not pending and not r.ns["price_buffer"]


async def test_a_held_unit_is_never_acknowledged_as_an_unchanged_observation(monkeypatch):
    clock = _FakeTime(monkeypatch, t=1030)
    database = {1: 0.5, 2: 0.5, 900: 0.2}  # every leg has changed
    r, state = writer_rig(clock, database=database, books={})
    r.ns["FLUSH_CHUNK_ROWS"] = 10
    r.ns["blend_refresher"].preview_events = {10}
    r.ns["observation_continuity"].update({1: (0, 0.6), 2: (0, 0.4)})
    r.ns["successful_price_write_at"].update(dict.fromkeys(database, 1029))

    assert await r.ns["flush_prices"](flush_started=1030)
    assert state.skip == [True] and state.commits == [900]
    boundary = r.ns["catalog_boundary"]
    # Held back, NOT acknowledged: the database never took these values.
    assert 1 not in boundary.observation_ack and 2 not in boundary.observation_ack
    assert 1 not in boundary.observation_pending and 2 not in boundary.observation_pending


async def test_the_bridged_writer_hands_back_only_the_events_that_committed():
    writer = pm._PMBridgeWriter()
    published = []

    async def publish(session):
        published.append(session)

    async def write(chunk, *, start_market_publish):
        assert set(chunk) == {2, 3}
        start_market_publish("session")  # straight after COMMIT
        return pm._PMPriceWriteResult((3,), skipped_ids={2}, skipped_events={20})

    writer.offer(
        [2, 3], {20, 30}, write=write, publish=publish, side_writer=asyncio.Lock(),
        buffer_lock=asyncio.Lock(), price_buffer={2: 0.7, 3: 0.5}, input_marks={},
    )
    await writer.join()
    assert published == ["session"]
    # Event 20 wrote no leg: it is not handed back as committed work, and the
    # writer no longer reserves it, so the game flush offers its leg again.
    owed = []
    refresher = SimpleNamespace(keep_owed=lambda events, marks: owed.append(set(events)))
    assert writer.transfer(refresher) == 1
    assert owed == [{30}]
    assert not writer.reserved and not writer.unstamped


async def test_the_props_loop_defers_only_the_held_questions_withdrawal():
    calls = []
    boundary = pm._PMCatalogFlushBoundary()

    async def write_chunk(chunk):
        calls.append(dict(chunk))
        return pm._PMPriceWriteResult((5,), skipped_ids={6})

    async def flush_withdrawals(**kwargs):
        calls.append(("withdraw", set(kwargs["exclude_events"])))
        return []

    ns = dict(
        buffer_lock=asyncio.Lock(), price_buffer={5: 0.4, 6: 0.6},
        standalone_open_outcome_ids=lambda *a: set(), open_outcome_ids=set(),
        event_id_by_outcome={5: 50, 6: 60}, open_complement_of={},
        non_blend_outcome_ids={5, 6}, withdraw_buffer={}, catalog_boundary=boundary,
        plan_flush_chunks=plan_flush_chunks,
        FLUSH_CHUNK_ROWS=500, lock_retry_events=set(), market_by_outcome={5: 5, 6: 6},
        write_chunk=write_chunk, flush_withdrawals=flush_withdrawals,
        event_ids_for_outcomes=lambda m, ids: {m[oid] for oid in ids if oid in m},
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["_flush_props"], ns)
    assert await ns["_flush_props"]() is True
    assert calls == [{5: 0.4, 6: 0.6}, ("withdraw", {60})]
