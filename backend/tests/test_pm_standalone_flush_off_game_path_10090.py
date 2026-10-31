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
import contextlib
import json

import pytest
import websockets
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
    _Replayed,
    _Rig,
    _Session,
    _stored,
    _tick,
)

from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

import app.tasks.live_blend_refresh as lbr
import app.tasks.polymarket_open_contracts as open_mod
import app.tasks.polymarket_ws as poly_task
from app.tasks.polymarket_ws import standalone_open_outcome_ids
from tests._pm_slate_market_read_10663 import answer_slate_market_read

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
        r.ns["open_outcome_ids"].add(900)
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
                    and 71 in dict(price_writes(stmt, *a[:1]))
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


# ------------------------------------------------ the catalog handover ----
#
# Root's 18:19Z hypothesis on v5719's two production handovers (blocked
# 1.092 s / 1.033 s, almost all of it `drain`): the periodic catalog handover
# closed the GAME door before it waited for an unrelated standalone write, so a
# game quote that arrived while a standalone chunk was writing waited for that
# chunk after all — the same wait the split above removed, put back once per
# catalog refresh. These drive the real consumer over the real PostgreSQL
# price write with a standalone UPDATE parked, let the TIMER handover start,
# and send game quotes into its drain.


class _Recorded(poly_task._PMCatalogFlushBoundary):
    """The consumer's own boundary; each handover's start/end is observable."""

    instances: list = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.handovers: list = []
        self.active_at_map: list = []
        _Recorded.instances.append(self)

    @contextlib.asynccontextmanager
    async def updating(self, timing=None):
        done = asyncio.Event()
        self.handovers.append(done)
        try:
            async with super().updating(timing):
                self.active_at_map.append(self.active)
                yield
        finally:
            done.set()

    async def next_handover(self):
        """The first handover that starts after this call."""
        seen = len(self.handovers)
        while len(self.handovers) == seen:
            await asyncio.sleep(0.005)
        return self.handovers[seen]


def _slate_session(base):
    """Answer every catalog read with the same slate, so the timer handover
    re-reads the game market instead of the empty tail of a replay list."""

    class _Catalog(base):
        async def execute(self, stmt, *a, **kw):
            sql = str(stmt)
            if isinstance(stmt, Select) and sql not in (
                str(open_mod.open_contract_markets_stmt()),
                str(open_mod.open_contract_outcomes_stmt()),
            ):
                if "linked_event_id" in sql:
                    return _Replayed(answer_slate_market_read(stmt, GAME_SLATE[0]))  # #10663
                if "futures_markets.market_metadata" in sql:
                    return _Replayed(answer_slate_market_read(stmt, GAME_SLATE[1]))
                if sql.startswith(
                    "SELECT futures_outcomes.id, futures_outcomes.market_id, "
                    "futures_outcomes.external_id"
                ):
                    return _Replayed(GAME_SLATE[2])
            return await super().execute(stmt, *a, **kw)

    return _Catalog


class _Venue:
    """Venue sockets the test can send frames into after they subscribe."""

    def __init__(self, first):
        self.first = first
        self.sockets = []

    def connect(self, *_a, **_kw):
        venue = self

        class _Socket:
            def __init__(self):
                self.assets = None
                self.queue = asyncio.Queue()
                venue.sockets.append(self)

            async def send(self, payload):
                if payload == "PING":
                    return
                self.assets = json.loads(payload).get("assets_ids") or []
                for token in self.assets:
                    for frame in venue.first.get(token, []):
                        self.queue.put_nowait(frame)

            def __aiter__(self):
                return self

            async def __anext__(self):
                return await self.queue.get()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        return _Socket()

    def send(self, token, frame):
        sockets = [s for s in self.sockets if s.assets and token in s.assets]
        assert sockets, f"no socket subscribed {token}"
        sockets[-1].queue.put_nowait(frame)


async def _settles(engine, outcome_id, value, within):
    deadline = asyncio.get_running_loop().time() + within
    while asyncio.get_running_loop().time() < deadline:
        if _stored(engine, outcome_id) == pytest.approx(value):
            return True
        await asyncio.sleep(0.01)
    return _stored(engine, outcome_id) == pytest.approx(value)


async def _consumer(monkeypatch, rig, venue, session, refresh=0.3, flush=0.04):
    import app.tasks.base as task_base
    import app.tasks.redis_state as redis_state

    class _Refresher(lbr.LiveBlendRefresher):
        async def refresh(self, event_ids, **_kw):
            rig.refreshed.append(set(event_ids))
            return None

        async def refresh_pending(self, **_kw):
            return None

    class _Ctx:
        async def __aenter__(self):
            self.real = Session(rig.engine)
            return session(self.real, rig)

        async def __aexit__(self, exc_type, *_exc):
            try:
                if exc_type is None:
                    self.real.commit()
                else:
                    self.real.rollback()
            finally:
                self.real.close()
            return False

    monkeypatch.setattr(_Recorded, "instances", [])
    monkeypatch.setattr(poly_task, "_PMCatalogFlushBoundary", _Recorded)
    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", refresh)
    monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", flush)
    monkeypatch.setattr(lbr, "LiveBlendRefresher", _Refresher)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: rig.redis)
    monkeypatch.setattr(websockets, "connect", venue.connect)
    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
    monkeypatch.setattr(open_mod, "FLUSH_CHUNK_ROWS", 1)
    stop = asyncio.Event()
    task = asyncio.create_task(poly_task._run_polymarket_ws_consumer(stop=stop))
    return stop, task


async def _finish(stop, task, held):
    held.release.set()
    stop.set()
    try:
        return await asyncio.wait_for(task, 5)
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


class TestTheCatalogHandover:
    async def test_game_quotes_keep_landing_while_the_handover_drains_a_standalone_write(
        self, monkeypatch, tmp_path
    ):
        """THE CANDIDATE'S SHIP. Standalone 71's UPDATE is parked when the
        timer handover starts. Three game quotes sent into that drain are each
        stored within a second, in order, while 71 is still parked and the
        handover has NOT finished; the handover then lands with no flush of
        either kind running, and a quote after it is stored too (recovery).
        On 5d39e56bdb (v5719) the first quote waits for 71's release."""
        engine = _database(tmp_path)
        rig = _Rig(engine, [], (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS), None)
        venue = _Venue({"711": [_tick("711")]})
        held = _HeldUpdate(71)
        stop, task = await _consumer(
            monkeypatch, rig, venue, _slate_session(held.session()),
        )
        try:
            await asyncio.wait_for(held.blocked.wait(), 2)
            (boundary,) = _Recorded.instances
            done = await asyncio.wait_for(boundary.next_handover(), 2)
            maps_before = len(boundary.active_at_map)
            await asyncio.sleep(0.05)  # the timer handover is inside its drain
            assert not done.is_set(), "premise: the handover waits for 71"
            for bid, ask, mid in (
                ("0.50", "0.52", 0.51), ("0.60", "0.62", 0.61), ("0.70", "0.72", 0.71),
            ):
                venue.send(GAME_TOKEN, _tick(GAME_TOKEN, bid, ask))
                assert await _settles(engine, GAME_OUTCOME, mid, 1.0), (
                    f"game quote {mid} waited behind the handover's standalone drain"
                )
            assert not done.is_set(), "premise: 71 still holds the handover"
            assert _stored(engine, 71) == pytest.approx(0.30), "71 is parked"
            assert {EVENT_ID} in rig.refreshed
            held.release.set()
            await asyncio.wait_for(done.wait(), 2)
            assert boundary.active_at_map[maps_before:] == [0], (
                "maps changed beside a flush"
            )
            venue.send(GAME_TOKEN, _tick(GAME_TOKEN, "0.80", "0.82"))
            assert await _settles(engine, GAME_OUTCOME, 0.81, 1.0), "no recovery"
        finally:
            stats = await _finish(stop, task, held)

        assert _stored(engine, 71) == pytest.approx(0.42)
        assert stats["catalog_refreshes"] >= 1
        assert stats["errors"] == 0
        assert stats["final_flush_dropped"] == 0
        assert stats["loops_unreaped"] == 0

    async def test_control_a_held_game_leg_still_holds_the_handover_and_the_next_game_quote(
        self, monkeypatch, tmp_path
    ):
        """CONTROL. The parked row IS the game leg. The game loop is serial, so
        the next game quote waits for it on parent and candidate alike, and the
        handover waits too; neither the quote nor a standalone write lands
        beside the maps. After release, both land and the maps changed with
        nothing running."""
        engine = _database(tmp_path)
        rig = _Rig(engine, [], (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS), None)
        venue = _Venue({GAME_TOKEN: [_tick(GAME_TOKEN, "0.50", "0.52")]})
        held = _HeldUpdate(GAME_OUTCOME)
        stop, task = await _consumer(
            monkeypatch, rig, venue, _slate_session(held.session()),
        )
        try:
            await asyncio.wait_for(held.blocked.wait(), 2)
            (boundary,) = _Recorded.instances
            done = await asyncio.wait_for(boundary.next_handover(), 2)
            maps_before = len(boundary.active_at_map)
            await asyncio.sleep(0.05)
            venue.send(GAME_TOKEN, _tick(GAME_TOKEN, "0.60", "0.62"))
            venue.send("711", _tick("711"))
            assert not await _settles(engine, GAME_OUTCOME, 0.61, 0.5)
            assert _stored(engine, 71) == pytest.approx(0.30)
            assert not done.is_set(), "the held game write holds the handover"
            held.release.set()
            await asyncio.wait_for(done.wait(), 2)
            assert boundary.active_at_map[maps_before:] == [0], (
                "maps changed beside a flush"
            )
            assert await _settles(engine, GAME_OUTCOME, 0.61, 1.0), "no recovery"
            assert await _settles(engine, 71, 0.42, 1.0)
        finally:
            stats = await _finish(stop, task, held)

        assert stats["errors"] == 0
        assert stats["final_flush_dropped"] == 0
        assert stats["loops_unreaped"] == 0

    async def test_continuous_game_flushes_do_not_starve_the_handover(self):
        """Game flushes back to back through the whole fence: once the
        standalone write ends, the handover waits for at most the game flush
        in flight, and every game flush after it sees the NEW maps."""
        boundary = poly_task._PMCatalogFlushBoundary()
        release, owners, seen = asyncio.Event(), {1: 900}, []
        stop = asyncio.Event()

        async def standalone():
            async with boundary.flushing(standalone=True):
                await release.wait()

        async def game_loop():
            while not stop.is_set():
                async with boundary.flushing():
                    seen.append(owners[1])
                    await asyncio.sleep(0.002)

        async def handover():
            async with boundary.updating():
                assert boundary.active == 0
                owners[1] = 901

        held = asyncio.create_task(standalone())
        await asyncio.sleep(0)
        games = asyncio.create_task(game_loop())
        update = asyncio.create_task(handover())
        await asyncio.sleep(0.05)
        during = len(seen)
        assert during >= 5 and set(seen) == {900}, "game flushes held by the fence"
        release.set()
        await asyncio.wait_for(update, 1)
        await asyncio.sleep(0.02)
        stop.set()
        await asyncio.gather(held, games)
        after = seen[during:]
        assert 901 in after and after == sorted(after), (
            "an old-map game flush ran after the maps changed"
        )
