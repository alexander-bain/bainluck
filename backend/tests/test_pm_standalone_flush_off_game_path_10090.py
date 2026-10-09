"""A standalone open contract's write no longer holds the next game quote. #10090.

WHAT THIS SHIPS. The Polymarket socket wrote every buffered row in ONE flush
loop: the game legs, their blend refresh, then up to two 500-row chunks of
standalone open contracts (Discover futures with no event), then the
withdrawal tail. The loop starts the next flush only when the previous one
returns, so a game quote that arrived while a standalone chunk was writing
waited for that chunk before it could even be written. Standalone legs feed no
blend, so the game page was paying for work that could never move its number.

Now a leg that is open, has no event and whose binary partner has none either
is written by its own loop at the base cadence, with its own withdrawals after
its own prices. The game flush keeps every linked and bridged leg, every blend
refresh and the price-then-withdrawal order. The final drain takes everything.

THE CASES:

    TestTheSplit ........ which legs leave the game flush: standalone only;
                          a bridged leg, a slate leg and a pair with one
                          bridged side stay.
    TestTheTwoFlushes ... the shipped closures (exec rig, no database): the
                          game flush neither writes nor withdraws a standalone
                          leg; `flush_standalone` writes it, THEN withdraws it,
                          and refreshes no blend.
    TestTheConsumer ..... the real `_run_polymarket_ws_consumer` over a real
                          PostgreSQL session: with a standalone chunk parked
                          at its UPDATE, a later game quote is stored and its
                          event refreshed. Before, it waited for the release.
    TestTheShutdown ..... Root review of 962ced1dc6: a standalone write the
                          shutdown cancels mid-UPDATE finishes unwinding before
                          the final drain writes the same leg again; and the
                          cancelled game flush's refresh unwinds before the
                          drain's (Live's c686 guard, on the Polymarket arm).
"""

import asyncio

import pytest
from tests.pm_bulk_test_support import cleanup_pg_engines  # noqa: F401
from tests.test_polymarket_withdrawal_speed_10651 import rig as exec_rig
from tests.pm_bulk_test_support import price_writes
from tests.test_kalshi_shutdown_stamp_join_10090 import _SlowUnwind
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)
from tests.test_ws_polymarket_open_contract_prices_9484 import (
    EVENT_ID,
    GAME_OUTCOME,
    GAME_SLATE,
    GAME_TOKEN,
    OPEN_MARKET_ROWS,
    OPEN_OUTCOME_ROWS,
    _database,
    _drive,
    _frames_by_token,
    _HeldUpdate,
    _Rig,
    _Session,
    _stored,
    _tick,
)

from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as lbr
import app.tasks.polymarket_open_contracts as open_mod
from app.tasks.polymarket_ws import standalone_open_outcome_ids

pytestmark = pytest.mark.asyncio


class TestTheSplit:
    async def test_only_eventless_open_legs_leave_the_game_flush(self):
        open_ids = {71, 72, 81, 91, 92}
        events = {51: 900, 81: 14780550, 92: 14780551}
        complement = {71: 72, 72: 71, 91: 92, 92: 91}
        assert standalone_open_outcome_ids(
            [51, 71, 72, 81, 91, 92, 99], open_ids, events, complement,
        ) == {71, 72}

    async def test_nothing_is_standalone_before_admission(self):
        assert standalone_open_outcome_ids([71, 81], set(), {}, {}) == set()


class TestTheTwoFlushes:
    async def test_each_loop_writes_then_withdraws_only_its_own_legs(self):
        r = exec_rig(
            batch={1: 0.6, 2: 0.4, 900: 0.1},
            mapping={1: 10, 2: 10},  # 900: open, no event -> standalone
            books={1: (0.1, 0.9), 900: (0.3, 0.7)},
        )
        r.release.set()
        assert await r.ns["flush_prices"](flush_started=100)
        game = list(r.trace)
        assert ("write", [900]) not in game
        assert all(not (k == "withdraw" and 900 in v) for k, v in game)
        assert game.index(("write", [1, 2])) < game.index(("withdraw", [1]))
        assert 900 in r.ns["price_buffer"] and 900 in r.books

        del r.trace[:]
        assert await r.ns["flush_standalone"](flush_started=102)
        assert r.trace.index(("write", [900])) < r.trace.index(("withdraw", [900]))
        assert all(k not in ("refresh", "pending") for k, _v in r.trace)
        assert not r.ns["price_buffer"] and not r.books

    async def test_the_final_drain_still_takes_a_standalone_leg(self):
        r = exec_rig(batch={900: 0.1}, mapping={}, books={900: (0.3, 0.7)})
        r.release.set()
        assert await r.ns["flush_prices"](final=True)
        assert r.trace.index(("write", [900])) < r.trace.index(("withdraw", [900]))


class TestTheConsumer:
    async def test_a_game_quote_is_stamped_while_a_standalone_chunk_is_parked(
        self, monkeypatch, tmp_path
    ):
        """THE SHIP. Standalone 71's UPDATE is parked; the game tick arrives
        after it. The game row is stored and its event handed to the blend
        refresher while 71 is still parked, and 71 lands after release."""
        engine = _database(tmp_path)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({
                "711": [(0.0, _tick("711"))],
                GAME_TOKEN: [(0.15, _tick(GAME_TOKEN, "0.60", "0.62"))],
            }),
        )
        monkeypatch.setattr(open_mod, "FLUSH_CHUNK_ROWS", 1)
        held = _HeldUpdate(71)
        stamped = asyncio.Event()

        def on_refresh(ids):
            if EVENT_ID in ids:
                stamped.set()

        task = asyncio.create_task(_drive(
            monkeypatch, rig, refresh=2.5, flush=0.04,
            session=held.session(), on_refresh=on_refresh,
        ))
        try:
            await asyncio.wait_for(held.blocked.wait(), 2)
            try:
                await asyncio.wait_for(stamped.wait(), 1.0)
            except asyncio.TimeoutError:
                pass
            assert stamped.is_set(), (
                "the game quote waited behind a standalone chunk's write"
            )
            assert _stored(engine, GAME_OUTCOME) == pytest.approx(0.61)
            assert _stored(engine, 71) == pytest.approx(0.30), "71 is parked"
        finally:
            held.release.set()
            try:
                stats = await asyncio.wait_for(task, 5)
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise

        assert _stored(engine, 71) == pytest.approx(0.42)
        assert stats["errors"] == 0
        assert stats["final_flush_dropped"] == 0
        assert {EVENT_ID} in rig.refreshed


class TestTheShutdown:
    async def test_the_final_drain_waits_for_the_cancelled_standalone_write(
        self, monkeypatch, tmp_path
    ):
        """Standalone 71's UPDATE is parked when the recycle cancels its loop,
        and its rollback takes a moment. The final drain still holds 71 in the
        buffer (entries leave only after a write lands), so draining at once
        would write 71 beside the unwinding one. Premise asserted: the cancel
        landed inside 71's write."""
        engine = _database(tmp_path)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({"711": [(0.0, _tick("711"))]}),
        )
        monkeypatch.setattr(open_mod, "FLUSH_CHUNK_ROWS", 1)
        seen = {"in_flight": 0, "most": 0, "cancelled": 0, "writes": 0}
        never = asyncio.Event()

        class _Unwinding(_Session):
            async def execute(self, stmt, *a, **kw):
                if not (
                    isinstance(stmt, Update)
                    and stmt.table.name == "futures_outcomes"
                    and 71 in dict(price_writes(stmt))
                ):
                    return await super().execute(stmt, *a, **kw)
                seen["writes"] += 1
                seen["in_flight"] += 1
                seen["most"] = max(seen["most"], seen["in_flight"])
                try:
                    if seen["writes"] == 1:
                        try:
                            await never.wait()  # parked until the recycle
                        except asyncio.CancelledError:
                            seen["cancelled"] += 1
                            await asyncio.sleep(0.05)  # rollback unwinding
                            raise
                    return await super().execute(stmt, *a, **kw)
                finally:
                    seen["in_flight"] -= 1

        stats = await asyncio.wait_for(_drive(
            monkeypatch, rig, refresh=0.3, flush=0.04, session=_Unwinding,
        ), 5)

        assert seen["cancelled"] == 1, "premise: the recycle cancelled 71's write"
        assert seen["writes"] >= 2, "premise: the final drain wrote 71 too"
        assert seen["most"] == 1, "the drain wrote 71 beside the unwinding write"
        assert _stored(engine, 71) == pytest.approx(0.42)
        assert stats["final_flush_dropped"] == 0
        assert stats["loops_unreaped"] == 0

    async def test_the_final_drain_waits_for_the_cancelled_game_flush(
        self, monkeypatch
    ):
        module, consumer, slate = _arm(monkeypatch, "polymarket")
        monkeypatch.setattr(_SlowUnwind, "instances", [])
        monkeypatch.setattr(lbr, "LiveBlendRefresher", _SlowUnwind)
        monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", 0.01)
        _install_quiet_socket(monkeypatch)
        _timing(monkeypatch, module, refresh=0.3)
        _install_session(monkeypatch, slate, lambda n: [])

        stats = await asyncio.wait_for(consumer(), timeout=5)

        (refresher,) = _SlowUnwind.instances
        assert refresher.cancelled == 1, "premise: the recycle cancelled a refresh"
        assert refresher.calls >= 2, "premise: the final drain refreshed too"
        assert refresher.most_running == 1, "the drain refreshed beside the flush"
        assert stats["loops_unreaped"] == 0
