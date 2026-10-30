"""Polymarket WebSocket consumer task.

Streams live prices and resolution events from Polymarket's CLOB WebSocket.
No auth required. Runs alongside the Kalshi WS consumer on the same dyno.

Events:
  - best_bid_ask: price updates → FuturesOutcome.current_probability
  - last_trade_price: trade executions → FuturesOutcome.current_probability
  - market_resolved: settlement → FuturesMarket resolved + is_winner
"""

import asyncio
import contextlib
import json
import logging
import math
import os
import time
from collections.abc import Collection, Iterable, Iterator, Mapping
from typing import Any, NamedTuple, Optional
from datetime import datetime, timezone

from sqlalchemy import text

from app.tasks.kalshi_ws import (
    FINAL_FLUSH_ATTEMPTS,
    PRICE_FLUSH_SECONDS,
    SUBSCRIPTION_REFRESH_SECONDS,
)
from app.tasks.polymarket import _poly_book_is_untradeable
from app.tasks.ws_consumer_sessions import owns_consumer_sessions  # #2471
from app.utils.market_quote_push import queue_market_change
from app.utils.market_settlement import settled_values
from app.utils.repair_lock_budget import (
    LOCK_NOT_AVAILABLE_SQLSTATE,
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)

logger = logging.getLogger(__name__)

# Ordinary chunks retain their whole rollback boundary; the final drain has
# no later periodic retry and keeps its existing database wait behavior.
PRICE_CHUNK_LOCK_TIMEOUT_MS = 500
#: #10090 — the price-row UPDATE alone waits this long for a lock. Its lock
#: timeout arms no cooldown: the rows stay known-held and the next flush probes
#: them NOWAIT. A holder of 50–500 ms therefore costs one failed attempt and a
#: write at the next flush (the held-quote overlay carries the blend meanwhile;
#: the row's own price lags until that write), where it used to be waited out
#: in the same flush. What a held chunk costs the later chunks of its flush
#: falls from up to 500 ms to 50 ms. Rerank and commit keep the chunk budget.
PRICE_STATEMENT_LOCK_TIMEOUT_MS = 50
#: #10090 (Root attempt71) — a whole GAME chunk on a game flush this fast or
#: faster tries its price rows for only this long: the next game flush probes
#: within one period, and the held-quote overlay publishes the newer quote
#: about 40 ms sooner. Props, standalone/open legs, unknown or mixed chunks and
#: any slower game cadence keep the 50 ms above: on a 250 ms loop a 1 ms try
#: turned a 20 ms hold into a 270 ms prop/standalone wait (real PG, 50 ms: 34–49).
FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS = 1
FAST_GAME_FLUSH_SECONDS = 0.025

# Optional DNPL game writers must not hold later arrivals inside a slow price
# statement. Keep the separate lock budget; preserve any tighter prior cap.
DNPL_PRICE_STATEMENT_TIMEOUT_MS = 250
ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL = text("""
    WITH prior AS MATERIALIZED (
        SELECT current_setting('statement_timeout') AS value
    )
    SELECT value, set_config('statement_timeout', CASE
        WHEN CAST(value AS interval) > interval '0'
         AND CAST(value AS interval) < CAST(CAST(:ms AS text) AS interval) THEN value
        ELSE CAST(:ms AS text) END, true)
    FROM prior
""")

#: #10090 — after an idle input wakes the price flush, wait this long (fixed,
#: once) before it snapshots the buffer, so the rest of an already-arriving
#: burst — a game's other leg, sent right behind the first — joins the same
#: flush instead of stamping the event half-updated (see run_flush_cadence).
PM_WAKE_COALESCE_SECONDS = 0.005


class _PMCatalogFlushBoundary:
    """Catalog handover waits for both disjoint flushes without serializing them.

    #10090: in two steps. First only standalone flushes are fenced and the
    handover waits out the one writing — game flushes keep running on the
    unchanged maps meanwhile, so an unrelated standalone UPDATE no longer
    holds every game's next price. The stamp attempts queued or running when
    that write clears (a game flush may have started or extended the call
    during the fence) then return with games still flowing and the call's
    door open: a later game is admitted beside a held stamp instead of being
    fenced behind it. That frontier is fixed, so arrivals cannot extend it.
    Then game flushes are fenced too and the handover waits for the one in
    flight (the game loop is serial) and joins the call, door closed first:
    only attempts admitted since the frontier remain — the parent's residual
    at its own fence instant. Maps change only with no flush of either kind
    and no stamp running.

    "Standalone" here means every SIDE flush: the standalone legs' loop and
    the linked props' loop (`flush_props`). Both are fenced in the first step.
    They write disjoint rows but take turns on one connection
    (`side_writer`), so the socket's five-connection pool still holds three
    stamps, the game writer and one side writer.
    """

    def __init__(self, *, game_period: float | None = None):
        # #10090: the game chunks' first price-row wait, from the run's own
        # game cadence (see FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS).
        self.game_price_lock_timeout_ms = (
            FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS
            if game_period is not None and game_period <= FAST_GAME_FLUSH_SECONDS
            else PRICE_STATEMENT_LOCK_TIMEOUT_MS
        )
        self.condition = asyncio.Condition()
        self.active = 0
        self.standalone_active = 0
        self.standalone_fenced = False
        self.changing = False
        self.stamps: Optional["_PMStampOwner"] = None
        self.flush_wake = asyncio.Event()
        self.flush_work = 0
        # Optional observations never own price/stamp debt. A successful
        # unchanged acknowledgement permits only its uninterrupted input value.
        self.observation_ack = {}
        self.observation_pending = {}
        self.observation_wake = asyncio.Event()
        self.observation_writing = set()
        self.observation_write_epoch = {}
        self.observation_drain = None
        # #10090: the linked props' own loop (`flush_props`).
        self.prop_wake = asyncio.Event()
        self.prop_work = 0
        # #10090: arrival order for every side loop; a live bridged cohort
        # (and, with `PM_BRIDGED_SIDE_FIRST`, every bridged one) takes the
        # first turn (`_PMBridgeWriter`).
        self.side_writer = _PMSideWriter()
        #: #10090: bridged open cohorts written beside the game flush.
        self.bridges = _PMBridgeWriter(wake=self.flush_wake)

    def stamp_owner(self, refresher) -> "_PMStampOwner":
        if self.stamps is None:
            self.stamps = _PMStampOwner(refresher, wake=self.flush_wake)
        return self.stamps

    def wake_for_outcomes(
        self,
        outcome_ids: Iterable[int],
        open_outcome_ids,
        event_id_by_outcome: dict[int, int],
        non_blend_outcome_ids=(),
    ) -> None:
        """Set `flush_wake` when any outcome can advance in the next game flush.

        Outcomes whose headline event already had a buffered cohort fenced by
        the running stamp stay quiet until that event's stamp releases: another
        flush while the stamp still holds the event would only fence it again.
        Standalone open legs belong to their own loop. Non-speaking props
        (`non_blend_outcome_ids`) wake theirs (`prop_wake`), never the game
        flush, which no longer writes them.
        """
        fenced = (
            self.stamps.fenced
            if self.stamps is not None
            and self.stamps.task is not None
            and not self.stamps.task.done()
            else ()
        )
        for oid in outcome_ids:
            if oid in open_outcome_ids and event_id_by_outcome.get(oid) is None:
                continue
            if oid in non_blend_outcome_ids:
                self.prop_wake.set()
                continue
            if fenced and event_id_by_outcome.get(oid) in fenced:
                continue
            # A bridged cohort still being written: its writer wakes the game
            # flush when it is done (`_PMBridgeWriter`).
            if event_id_by_outcome.get(oid) in self.bridges.reserved:
                continue
            self.flush_wake.set()
            return

    async def join_stamps(self, *, cancel=False) -> None:
        if self.stamps is not None:
            await self.stamps.join(cancel=cancel)

    @contextlib.asynccontextmanager
    async def flushing(self, *, standalone=False):
        """``standalone``: the flush may write standalone legs (the standalone
        loop and the final drain), so the handover's first step fences it."""
        async with self.condition:
            await self.condition.wait_for(
                lambda: not self.changing
                and not (standalone and self.standalone_fenced)
            )
            self.active += 1
            self.standalone_active += standalone
        try:
            yield
        finally:
            async with self.condition:
                self.active -= 1
                self.standalone_active -= standalone
                self.condition.notify_all()

    async def _settle_stamp(self) -> None:
        """#10090 — the stamp attempts queued or running as the fence's
        standalone write clears return before game flushes are fenced. The
        call's door stays open meanwhile, so a game arriving now is admitted
        beside a held stamp, not held behind it. Only that frontier of
        attempts (or the call's end): a later admission — even a re-admission
        of a frontier event — is joined under the fence, never waited for
        here, so continuous arrivals cannot extend the settle. A call whose
        task has not yet had its first turn holds nothing readable: the
        frontier is fixed once it opens its door (or it ends), never left
        unset — an unset frontier would wait on the whole, extendable call.
        Cancelled here, the call is cancelled and joined as in the stamps
        phase."""
        owner = self.stamps
        task = None if owner is None else owner.task
        if task is None or task.done():
            return
        reader = getattr(owner.refresher, "holding_frontier", None)
        opened = getattr(owner.refresher, "admission_opened", None)
        try:
            frontier = reader() if reader is not None else None
            while frontier is None and opened is not None and not task.done():
                await asyncio.wait({task, opened()}, return_when=asyncio.FIRST_COMPLETED)
                frontier = reader()
            while not task.done() and not (frontier is not None and frontier.drained()):
                waits = {task}
                if frontier is not None:
                    waits.add(frontier.changed())
                await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            await owner.join(cancel=True)
            raise

    @contextlib.asynccontextmanager
    async def updating(self, timing: Optional["_PMCatalogHandoverTiming"] = None):
        if timing is None:
            timing = _PMCatalogHandoverTiming(None)
        async with self.condition:
            self.standalone_fenced = True
            timing.enter("fence", flushes=self.active)
            try:
                await self.condition.wait_for(lambda: self.standalone_active == 0)
            except BaseException as exc:
                self.standalone_fenced = False
                self.condition.notify_all()
                timing.finish(_handover_outcome(exc))
                raise
        try:
            # #10090: no bridged cohort starts while side flushes are fenced
            # (`_flush_prices`); the one already running finishes, so its
            # committed cohort is handed over before any map changes.
            await self.bridges.join()
            await self._settle_stamp()
        except BaseException as exc:
            async with self.condition:
                self.standalone_fenced = False
                self.condition.notify_all()
            timing.finish(_handover_outcome(exc))
            raise
        async with self.condition:
            self.changing = True
            timing.enter("drain")
            try:
                await self.condition.wait_for(lambda: self.active == 0)
            except BaseException as exc:
                self.standalone_fenced = self.changing = False
                self.condition.notify_all()
                timing.finish(_handover_outcome(exc))
                raise
        outcome = "ok"
        try:
            # No maps change beneath a stamp left running by an earlier batch.
            timing.enter("stamps")
            await self.join_stamps()
            if self.stamps is not None:
                # Committed bridged cohorts no game flush has stamped yet become
                # debt keyed by event, which survives the new maps.
                self.bridges.transfer(self.stamps.refresher)
            yield
        except BaseException as exc:
            outcome = _handover_outcome(exc)
            raise
        finally:
            try:
                async with self.condition:
                    self.standalone_fenced = self.changing = False
                    self.condition.notify_all()
            finally:
                timing.finish(outcome)


def _handover_outcome(exc: BaseException) -> str:
    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    return f"failed:{type(exc).__name__}"


class _PMCatalogHandoverTiming:
    """#10090 — where one catalog handover's blocked interval went.

    Every PM flush waits while `changing` is set, so a slow handover delays
    every game's next price. `fence` (standalone flushes held, game flushes
    still running — through the standalone write and then the stamp attempts
    held when it cleared) comes first and is reported beside `blocked`,
    not inside it; `blocked` starts at `drain`. Phases are monotonic durations; a phase runs
    until the next one opens (the boundary opens drain and stamps, the
    caller names its body's phases) or the release. One INFO line per
    handover, written once, with the phase the handover ended in when it
    was cancelled or failed. Reads before the boundary block no flush and
    are reported beside it, not inside `blocked`.
    """

    def __init__(
        self,
        reason: Optional[str],
        *,
        slate_read_s: Optional[float] = None,
        open_read_s: Optional[float] = None,
        clock=time.monotonic,
    ) -> None:
        self.reason = reason
        self.reads = (("slate_read", slate_read_s), ("open_read", open_read_s))
        self.clock = clock
        self.durations: dict[str, float] = {}
        self.phase: Optional[str] = None
        self.phase_started = 0.0
        self.blocked_started: Optional[float] = None
        self.blocked_s: Optional[float] = None
        self.flushes: Optional[int] = None
        self.ended_in: Optional[str] = None
        self.outcome: Optional[str] = None

    def _close(self, now: float) -> None:
        if self.phase is not None:
            self.durations[self.phase] = now - self.phase_started
            self.phase = None

    def enter(self, phase: str, *, flushes: Optional[int] = None) -> None:
        if self.outcome is not None:
            return
        now = self.clock()
        self._close(now)
        if flushes is not None:
            self.flushes = flushes
        if self.blocked_started is None and phase != "fence":
            self.blocked_started = now
        self.phase, self.phase_started = phase, now

    def finish(self, outcome: str) -> None:
        if self.outcome is not None:
            return
        now = self.clock()
        self.ended_in = self.phase
        self._close(now)
        if self.blocked_started is not None:
            self.blocked_s = now - self.blocked_started
        elif self.durations:
            self.blocked_s = 0.0  # ended in `fence`: no game flush was held
        self.outcome = outcome
        if self.reason is not None:
            logger.info("%s", self.line())

    def line(self) -> str:
        def seconds(value: Optional[float]) -> str:
            return "-" if value is None else f"{value:.3f}s"

        outcome = self.outcome or "open"
        if outcome != "ok" and self.ended_in is not None:
            outcome = f"{outcome}@{self.ended_in}"
        parts = [f"reason={self.reason}", f"outcome={outcome}"]
        parts += [f"{name}={seconds(value)}" for name, value in self.reads]
        parts += [
            f"{name}={seconds(self.durations.get(name))}"
            for name in ("fence", "drain", "stamps", "lock", "map", "open")
        ]
        parts.append(f"blocked={seconds(self.blocked_s)}")
        parts.append(
            f"flushes_at_start={'-' if self.flushes is None else self.flushes}"
        )
        return "Polymarket WS catalog handover: " + " ".join(parts)


class _PMStampOwner:
    """One consumer's refresh task and committed cohorts, across price batches.

    Price writes stay serial. A later unrelated whole cohort may join this
    owner's actual shared admission window; overlap/withdrawal/catalog/final
    boundaries join it instead. No second mutable refresher call runs beside it.
    """

    def __init__(self, refresher, *, wake: Optional[asyncio.Event] = None) -> None:
        self.refresher = refresher
        self.wake = wake
        self._task: Optional[asyncio.Task] = None
        self.events: Optional[set[int]] = None
        self.fresh: set[int] = set()
        #: #10090: events whose buffered price/withdrawal was fenced by a game
        #: flush while this owner's refresh held them; releasing one wakes the
        #: game flush loop so the buffered cohort does not wait for the next
        #: periodic timer on a quiet market.
        self.fenced: set[int] = set()
        #: #10090: seconds flushes spent waiting here on a running refresh.
        self.waited_s = 0.0
        if hasattr(refresher, "release_wake"):
            refresher.release_wake = self._on_release

    @property
    def task(self) -> Optional[asyncio.Task]:
        return self._task

    @task.setter
    def task(self, value: Optional[asyncio.Task]) -> None:
        self._task = value
        if value is not None and hasattr(value, "add_done_callback"):
            value.add_done_callback(self._on_task_done)

    def note_fenced(self, event_ids: Iterable[int]) -> None:
        if self._task is None or self._task.done():
            return
        held = self.held_events()
        if held is None:
            self.fenced.update(event_ids)
        else:
            self.fenced.update(held.intersection(event_ids))

    def _on_release(self, event_ids: Iterable[int]) -> None:
        if not self.fenced:
            return
        released = self.fenced.intersection(event_ids)
        if not released:
            return
        self.fenced.difference_update(released)
        if (
            self.wake is not None
            and self._task is not None
            and not self._task.cancelling()
        ):
            self.wake.set()

    def _on_task_done(self, task: asyncio.Task) -> None:
        if self._task is not task:
            return
        if not self.fenced:
            return
        self.fenced.clear()
        if (
            self.wake is not None
            and not task.cancelled()
            and task.exception() is None
        ):
            self.wake.set()

    def held_events(self) -> Optional[set[int]]:
        """#10090 — the events the running refresh is still stamping.

        The refresher's own fence (`holding_event_ids`) once it reports one —
        whole: the call also stamps owed events it takes after it started
        (`window.debt`), which this owner's captured membership never lists;
        until then everything the call was started with or admitted. None
        while membership is unknown. Twin of the Kalshi owner's.
        """
        if self.events is None:
            return None
        reader = getattr(self.refresher, "holding_event_ids", None)
        holding = reader() if reader is not None else None
        if holding is None:
            return self.events
        return set(holding)

    async def join(self, *, cancel=False) -> None:
        if self._task is None:
            return
        task = self._task
        if cancel:
            self.fenced.clear()
        if not task.done():
            # #10090: a running call keeps admitting later flushes' cohorts.
            # A join is a lifecycle drain: close the door first, so this waits
            # for what is already queued and never for a later arrival.
            stop = getattr(self.refresher, "stop_admitting", None)
            if stop is not None:
                stop()
        if cancel and not task.cancelling():
            task.cancel()
        interrupted = None
        started = time.monotonic()
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
                self.fenced.clear()
                if not task.cancelling():
                    task.cancel()
        self.waited_s += time.monotonic() - started
        if self._task is not task:
            # #10090: a catalog settle's cancel joins while game flushes still
            # run, so a flush's join of the same call can finish first and
            # start the next call. That joiner already took this call's debt;
            # the slot (and its cohort) now belong to the next call.
            if interrupted is not None:
                raise interrupted
            return
        self._task = None
        self.fenced.clear()
        fresh, self.fresh = self.fresh, set()
        self.events = None
        if task.cancelled() or task.exception() is not None:
            # Also covers cancellation before refresh takes the staged cohort.
            self.refresher.adopt_pending(fresh)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "Polymarket WS: blend refresh raised after its write committed",
                exc_info=task.exception(),
            )
        if interrupted is not None:
            raise interrupted


#: #10090: bridged cohorts queued or being written at once. Past this a pure
#: bridged event's prices stay buffered for a later flush (oldest first); the
#: game flush never writes them itself, so a held bridged write cannot
#: reach an unrelated game through a full queue.
PM_BRIDGE_QUEUE_LIMIT = 2

#: #10090: a queued pre-game bridged cohort that has waited this long is the
#: next one written, ahead of live cohorts. Live cohorts lead the queue, so
#: without this a live stream at or above the writer's throughput left a
#: pre-game event's price (and the withdrawal waiting with it) unwritten for
#: as long as the load lasted (lane1, #11769 review). Two 0.25 s game flushes;
#: a live cohort then waits at most one pre-game write (<=0.28 s measured).
PM_PREGAME_BRIDGE_MAX_WAIT_S = 0.5


def _bridged_side_first_env() -> bool:
    """#10090 — env `PM_BRIDGED_SIDE_FIRST`, read once at import.

    Missing, blank, "0"/"false"/"off"/"no" is off (today's FIFO side
    connection, the same `asyncio.Lock`); "1"/"true"/"on"/"yes" is on;
    anything else is off with one warning.
    """
    raw = os.environ.get("PM_BRIDGED_SIDE_FIRST")
    if raw is None or not raw.strip():
        return False
    value = raw.strip().lower()
    if value in ("1", "true", "on", "yes"):
        return True
    if value not in ("0", "false", "off", "no"):
        logger.warning(
            "Polymarket WS: PM_BRIDGED_SIDE_FIRST=%r is not on/off; using off", raw,
        )
    return False


#: #10090: a pure bridged cohort feeds its event's blend; a standalone leg and
#: a linked prop feed none, yet all three take turns on the one side connection
#: (`side_writer`) in arrival order. Production 2026-10-28 23:16Z: 24 pre-game
#: events' prices received 23:16:24.6-35.2 were written in ONE bridged cohort
#: that read the buffer after 35.2 s, while live games' prices committed and
#: stamped 0.3-2.2 s after arrival. On, the bridged writer takes the side
#: connection ahead of any side loop waiting for it: it waits for the one side
#: transaction in flight, never for the queue behind it. Off, only a cohort of
#: live events does (Argon rank 4: switch unset, live bridged writes waited up
#: to 3.73 s for that connection behind standalone and prop chunks).
PM_BRIDGED_SIDE_FIRST = _bridged_side_first_env()

_PM_BRIDGE_TIMING_KEYS = (
    "bridged_cohorts", "bridged_side_wait_s", "bridged_side_wait_max_s",
    "bridged_write_s", "bridged_write_max_s",
    "bridged_live_cohorts", "bridged_live_wait_s", "bridged_live_wait_max_s",
)


class _PMSideWriter:
    """#10090 — the one side connection, with a bridged-first turn.

    `async with writer:` waits in arrival order, as `asyncio.Lock`;
    `async with writer.first():` goes ahead of every waiter that is not itself
    first, behind the transaction in flight (never pre-empted). A plain waiter
    holding a ``ticket`` can be moved into the first turn while it waits
    (`promote`). Release is synchronous (a hand-over to the next waiter), so a
    cancellation can never leave the connection marked held.
    """

    def __init__(self) -> None:
        self._held = False
        #: [first, future, ticket], first turns ahead, each in arrival order.
        self._waiters: list[list] = []

    def locked(self) -> bool:
        return self._held

    def _insert(self, waiter: list) -> None:
        if waiter[0]:
            ahead = sum(1 for other in self._waiters if other[0])
            self._waiters.insert(ahead, waiter)
        else:
            self._waiters.append(waiter)

    async def acquire(self, first: bool = False, ticket: object = None) -> bool:
        if not self._held and not self._waiters:
            self._held = True
            return True
        waiter = [first, asyncio.get_running_loop().create_future(), ticket]
        self._insert(waiter)
        try:
            await waiter[1]
        except asyncio.CancelledError:
            if waiter[1].done() and not waiter[1].cancelled():
                # Handed the connection, then cancelled before running.
                self.release()
            elif waiter in self._waiters:
                self._waiters.remove(waiter)
            raise
        return True

    def promote(self, ticket: object) -> bool:
        """Move the plain waiter holding ``ticket`` to the back of the first
        turn; False when no such waiter is still waiting."""
        for waiter in self._waiters:
            if waiter[2] is ticket and ticket is not None:
                if not waiter[0] and not waiter[1].done():
                    self._waiters.remove(waiter)
                    waiter[0] = True
                    self._insert(waiter)
                return not waiter[1].done()
        return False

    def release(self) -> None:
        while self._waiters:
            _first, future, _ticket = self._waiters.pop(0)
            if not future.done():
                future.set_result(True)  # handed over; stays held
                return
        self._held = False

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, *exc):
        self.release()

    @contextlib.asynccontextmanager
    async def turn(self, first: bool = False, ticket: object = None):
        await self.acquire(first=first, ticket=ticket)
        try:
            yield
        finally:
            self.release()

    def first(self):
        return self.turn(first=True)


def _pm_pure_bridged_legs(
    batch_ids,
    open_outcome_ids,
    event_id_by_outcome: dict,
    complement_of: dict,
    non_blend_outcome_ids,
) -> dict[int, list[int]]:
    """#10090 — the buffered open legs of PURE bridged events, by event, in
    buffer order.

    Pure: the event's every blend-read outcome in the WHOLE catalog is an open
    leg. One linked slate outcome anywhere in the catalog (a silent sibling
    with nothing buffered included) keeps the event on the game flush, so the
    two writers never share an event and no stamp needs both. A venue-refuted
    prop (`non_blend_outcome_ids`) is not read by the blend and has its own
    loop already, so it does not make an event mixed. A binary pair travels
    whole: a partner that is not open, or names another event, keeps both
    events on the game flush (CERT-3868). Scans the catalog only when a
    bridged leg is buffered.
    """
    by_event: dict[int, list[int]] = {}
    mixed: set[int] = set()
    for oid in batch_ids:
        if oid not in open_outcome_ids:
            continue
        eid = event_id_by_outcome.get(oid)
        other = complement_of.get(oid)
        other_eid = None if other is None else event_id_by_outcome.get(other)
        if eid is None:
            eid = other_eid
        if eid is None:
            continue
        if other is not None and (
            other not in open_outcome_ids or other_eid not in (None, eid)
        ):
            mixed.add(eid)
            if other_eid is not None:
                mixed.add(other_eid)
        by_event.setdefault(eid, []).append(oid)
    if not by_event:
        return {}
    mixed.update(
        eid for oid, eid in event_id_by_outcome.items()
        if eid in by_event
        and oid not in open_outcome_ids
        and oid not in non_blend_outcome_ids
    )
    return {eid: legs for eid, legs in by_event.items() if eid not in mixed}


class _PMBridgeWriter:
    """#10090 — the one bounded writer for PURE event-bridged open cohorts.

    A bridged open leg feeds its event's blend, so it stays off the standalone
    loop; written inside the game flush, one slow bridged transaction held the
    flush's return and every unrelated game's next quote with it (Root's
    bridged-tail rig: the selected event's 0.65 unwritten after 1 s, unheld
    control passed). The game flush now hands a pure bridged event's whole
    cohort here and moves on (`_pm_pure_bridged_legs`: membership is by whole
    event over the full catalog, so no event is written by both). This writer
    takes the existing side connection (`side_writer`), so no new pool member
    competes, and never stamps: each committed cohort is handed back as owed
    work (`take_completed`) that the next game flush stamps through the one
    existing stamp owner, before this writer waits for the cohort's market
    notification. A cohort of live events (``live``) leads the queue and takes
    the side connection's first turn, though never past a pre-game cohort that
    has waited ``PM_PREGAME_BRIDGE_MAX_WAIT_S``; it is still this one serial
    writer, and each cohort reads its prices from the buffer only once it holds
    the turn, so no outcome is ever written by two writers or with an older
    value after a newer one.

    ``reserved`` — events a queued or running cohort may still write or
    notify: game writes and withdrawals skip them, and no newer cohort of the
    same event is offered, so one event's writes and notifications stay in
    order. ``unstamped`` — the reserved events not yet committed: every stamp
    defers them, so no stamp reads a board this writer is about to change.
    A committed price whose stamp is owed is never lost: the commit is
    recorded before any cancellable step and settled in ``finally``. Before
    COMMIT, cancellation leaves the prices buffered.
    """

    def __init__(self, wake: Optional[asyncio.Event] = None) -> None:
        self.wake = wake
        self.task: Optional[asyncio.Task] = None
        self.reserved: set[int] = set()
        self.unstamped: set[int] = set()
        #: (ids, events, live, offered_at); live cohorts first, each part in
        #: arrival order.
        self.queue: list[tuple] = []
        self.completed: list[tuple[list, dict, set]] = []
        #: The side-connection ticket of a turn this writer is waiting for.
        self._asking: Optional[object] = None
        #: A failed (non-lock) write leaves later cohorts buffered until this
        #: clock, as the game flush's own failure would: no retry storm.
        self.hold_until = 0.0
        #: Retry-held events' last offer (`_flush_prices` rotates them).
        self.retry_offered: dict[int, float] = {}
        self._entry: Optional[dict] = None
        #: #10090: per cohort, seconds waiting for the side connection and
        #: seconds in its own write; sums since start, maxima since the last
        #: minute line (`take_timing`).
        self.timing = dict.fromkeys(_PM_BRIDGE_TIMING_KEYS, 0.0)

    def take_timing(self) -> dict:
        """The open-contract minute line's bridged fields; resets the maxima."""
        timing = dict(self.timing)
        self.timing["bridged_side_wait_max_s"] = 0.0
        self.timing["bridged_write_max_s"] = 0.0
        self.timing["bridged_live_wait_max_s"] = 0.0
        return timing

    def _note_timing(self, name: str, seconds: float) -> None:
        self.timing[f"bridged_{name}_s"] += seconds
        key = f"bridged_{name}_max_s"
        self.timing[key] = max(self.timing[key], seconds)

    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    def accepting(self, live: bool = False) -> bool:
        """Room for one more cohort. Live and pre-game cohorts each count only
        their own kind outstanding against the bound (at most twice the bound
        in all), so neither kind keeps the other out."""
        if time.monotonic() < self.hold_until:
            return False
        outstanding = [queued[2] for queued in self.queue]
        if self._entry is not None:
            outstanding.append(self._entry["live"])
        mine = sum(1 for is_live in outstanding if is_live == bool(live))
        return mine < PM_BRIDGE_QUEUE_LIMIT

    def _next_index(self, now: float) -> int:
        """The queued cohort to write next: the head (a live cohort when one is
        queued), unless the oldest pre-game cohort has waited
        ``PM_PREGAME_BRIDGE_MAX_WAIT_S`` — so a live stream cannot starve it."""
        for index, (_ids, _events, live, offered) in enumerate(self.queue):
            if not live:
                return index if now - offered >= PM_PREGAME_BRIDGE_MAX_WAIT_S else 0
        return 0

    def offer(
        self, ids, events, *, write, publish,
        side_writer, buffer_lock, price_buffer, input_marks, live=False,
    ) -> None:
        """Queue one bridged cohort; reserves ``events`` before returning.
        ``live``: it goes ahead of every queued pre-game cohort, and a plain
        side-connection wait already under way moves to the first turn."""
        events = set(events)
        self.reserved.update(events)
        self.unstamped.update(events)
        queued = (list(ids), events, bool(live), time.monotonic())
        if live:
            self.queue.insert(sum(1 for other in self.queue if other[2]), queued)
            promote = getattr(side_writer, "promote", None)
            if self._asking is not None and promote is not None:
                promote(self._asking)
        else:
            self.queue.append(queued)
        if not self.busy():
            self.task = asyncio.create_task(
                self._run(write, publish, side_writer, buffer_lock, price_buffer, input_marks),
                name="polymarket-bridged-open-writer",
            )
            self.task.add_done_callback(self._on_done)

    def take_completed(self) -> list[tuple[list, dict, set]]:
        completed, self.completed = self.completed, []
        return completed

    def transfer(self, refresher) -> int:
        """Hand committed cohorts to the refresher's debt (lifecycle only:
        catalog handover before maps change, shutdown before the drain)."""
        completed = self.take_completed()
        keep_owed = getattr(refresher, "keep_committed", None) or getattr(
            refresher, "keep_owed", None
        )
        for ids, marks, events in completed:
            if events and keep_owed is not None:
                keep_owed(events, marks=[marks[oid] for oid in ids if oid in marks])
            elif events:
                refresher.adopt_pending(events)
        return len(completed)

    def _expose(self, entry: dict) -> None:
        # Once per cohort: its committed ids (every chunk id when the write's
        # own result never arrived; none when a zero-return write changed no
        # row) owe a stamp, and no stamp defers the event any longer.
        if entry["exposed"]:
            return
        entry["exposed"] = True
        self.unstamped.difference_update(entry["events"])
        ids = entry["committed"] or []
        self._complete(
            ids, {oid: entry["marks"][oid] for oid in ids if oid in entry["marks"]},
            entry["events"],
        )

    def _complete(self, ids, marks, events) -> None:
        if ids:
            self.completed.append((list(ids), dict(marks), set(events)))
            if self.wake is not None:
                self.wake.set()

    def _settle_entry(self, entry: dict) -> None:
        self._expose(entry)
        self.reserved.difference_update(entry["events"])
        self.unstamped.difference_update(entry["events"])
        if entry["events"] and self.wake is not None:
            # Inputs on a reserved event did not wake the game flush
            # (`wake_for_outcomes`); a cohort that committed nothing (a refused
            # lock, a failure, an emptied chunk) still owes them that wake.
            self.wake.set()

    async def _run(self, write, publish, side_writer, buffer_lock, price_buffer, input_marks):
        turn = getattr(side_writer, "turn", None)
        while self.queue:
            # #10090: the turn is taken BEFORE the cohort is chosen, so a live
            # cohort offered during the wait is the one written next (unless a
            # pre-game cohort has waited past its bound, `_next_index`), and
            # its offer moves a plain wait to the first turn. A live cohort
            # leads the queue, so its head says whether one is waiting.
            go_first = PM_BRIDGED_SIDE_FIRST or self.queue[0][2]
            entry = None
            publishing = None
            asked = time.monotonic()
            ticket = self._asking = object()
            try:
                async with turn(go_first, ticket) if turn is not None else side_writer:
                    self._asking = None
                    took = time.monotonic()
                    ids, events, live, offered = self.queue.pop(self._next_index(took))
                    entry = self._entry = {
                        "events": events, "committed": None, "marks": {},
                        "exposed": False, "live": live,
                    }
                    self.timing["bridged_cohorts"] += 1
                    self._note_timing("side_wait", took - max(asked, offered))
                    if live:
                        # From hand-off to the turn: the bridged queue included.
                        self.timing["bridged_live_cohorts"] += 1
                        self._note_timing("live_wait", took - offered)
                    async with buffer_lock:
                        chunk = {oid: price_buffer[oid] for oid in ids if oid in price_buffer}
                        entry["marks"] = {
                            oid: input_marks[oid] for oid in chunk if oid in input_marks
                        }
                    if not chunk:
                        continue

                    def committed(session):
                        nonlocal publishing
                        # Synchronous, straight after COMMIT: the stamp is owed
                        # from here even if the rest of this task is cancelled.
                        entry["committed"] = list(chunk)
                        self.unstamped.difference_update(events)
                        publishing = asyncio.create_task(
                            publish(session), name="polymarket-bridged-market-publish",
                        )

                    try:
                        wrote = await write(chunk, start_market_publish=committed)
                    finally:
                        self._note_timing("write", time.monotonic() - took)
                    if wrote and entry["committed"] is not None:
                        entry["committed"] = list(getattr(wrote, "written_ids", chunk))
                    elif wrote is False:
                        self.hold_until = time.monotonic() + PRICE_FLUSH_SECONDS
                    # The event's stamp goes ahead of its market notification,
                    # as a game chunk's does (`test_pm_event_before_notification`):
                    # a held notification no longer holds the event frame.
                    self._expose(entry)
            finally:
                self._asking = None
                if entry is not None:
                    try:
                        if publishing is not None:
                            # Committed but interrupted before `_expose` above
                            # (a cancellation in write_chunk's buffer cleanup,
                            # after its commit callback): the stamp is owed
                            # now, from every chunk id, not after a held
                            # notification.
                            self._expose(entry)
                            await _join_publication(publishing)
                    finally:
                        self._entry = None
                        self._settle_entry(entry)

    def _on_done(self, task: asyncio.Task) -> None:
        if self.task is not task:
            return
        # Cancelled before its first turn or between cohorts: queued cohorts
        # wrote nothing, so their prices are still buffered and owe nothing.
        if self._entry is not None:
            self._settle_entry(self._entry)
            self._entry = None
        self.queue.clear()
        self.reserved.clear()
        self.unstamped.clear()
        if self.wake is not None:
            self.wake.set()
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "Polymarket WS: bridged open writer raised", exc_info=task.exception(),
            )

    async def join(self) -> None:
        """Wait for the writer to finish — to completion, never cancelled: a
        second cancellation is recorded and re-raised after the join."""
        interrupted = None
        while self.busy():
            try:
                await asyncio.wait({self.task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if interrupted is not None:
            raise interrupted


async def _join_publication(task: asyncio.Task) -> None:
    """Await a committed market publication; a cancellation cancels it, waits
    for it, then propagates. Its own failure is logged, never raised."""
    interrupted = None
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError as exc:
            interrupted = exc
            if not task.cancelling():
                task.cancel()
    if not task.cancelled() and task.exception() is not None:
        logger.error(
            "Polymarket WS: committed market publication failed",
            exc_info=task.exception(),
        )
    if interrupted is not None:
        raise interrupted


def pm_non_speaking_metadata(metadata: Any) -> bool:
    """Only the shared venue-label refutation can exclude a loaded question."""
    from types import SimpleNamespace
    from app.utils.content_understanding import venue_label_refutes_full_contest_winner

    return venue_label_refutes_full_contest_winner(
        SimpleNamespace(market_metadata=metadata)
    )


class _PMHeadlineEvents(Mapping[int, int]):
    """Live owner-map view; only venue-refuted questions leave WIN cohorts."""

    def __init__(self, events: Mapping[int, int], non_speakers: Collection[int]):
        self.events = events
        self.non_speakers = non_speakers

    def __getitem__(self, outcome_id: int) -> int:
        if outcome_id in self.non_speakers:
            raise KeyError(outcome_id)
        return self.events[outcome_id]

    def __iter__(self) -> Iterator[int]:
        return (oid for oid in self.events if oid not in self.non_speakers)

    def __len__(self) -> int:
        return sum(1 for _ in self)


#: A leg whose external id ends in one of these is the book of Gamma's
#: ``outcomes[1]``, the second CLOB token. ``_side1`` is a named two-sided
#: game's complement (``polymarket.py``, the ``_side1`` writer); ``_no`` is a
#: Yes/No binary's.
_SECOND_TOKEN_SUFFIXES = ("_side1", "_no")
_FIRST_TOKEN_SUFFIXES = ("_yes",)


def _token_index(ext: str) -> Optional[int]:
    ext = ext or ""
    if ext.endswith(_SECOND_TOKEN_SUFFIXES):
        return 1
    # A bare condition id (``0x...``, no suffix at all) is the first token.
    if ext.endswith(_FIRST_TOKEN_SUFFIXES) or (ext and "_" not in ext):
        return 0
    return None


#: #9733. The smallest order Polymarket accepts on a market is 5 shares
#: (Gamma ``orderMinSize``), so a trade smaller than that can only be the
#: leftover of an order someone else mostly filled. On the tape of market
#: 61380825 ("Yankees advance to the ALCS", condition ``0x8bd936dd…``, read
#: 2026-09-30) every trade at an absurd price was such a leftover — No 0.38 × 2
#: (the one that set No = Yes = 0.38 and printed "No 38%" on search), No 0.29
#: × 0.5, No 0.04 × 1.77, Yes 0.48 × 0.87 — while the trades at the market's
#: real price were 3.3 shares and up.
MIN_PRICE_SETTING_TRADE_SHARES = 5.0


def trade_sets_a_price(msg: dict) -> bool:
    """False for a ``last_trade_price`` smaller than the venue's smallest order.

    Such a leftover is a real execution but not a price: nobody could have
    placed an order at that size, so its price tells a reader nothing about
    the market. A frame that states no size, or a size that is not a number, is
    let through exactly as before — this rule refuses only what it can read.
    """
    size = msg.get("size")
    if size is None:
        return True
    try:
        return float(size) >= MIN_PRICE_SETTING_TRADE_SHARES
    except (TypeError, ValueError):
        return True


def trade_prints_outside_wide_book(prob: float, books: tuple) -> bool:
    """True for a trade that swept through a book too wide to price anything.

    #9913. PHI @ ATL, 2026-09-30 18:54Z: the Braves series token's book was
    0.12 × 5 / 0.11 × 394 bid, 0.73 ask, and a 20-share SELL printed at 0.1125,
    the average of 0.12 × 5 and 0.11 × 15 (the tick is a cent, so no resting
    order sat at 0.1125). It cleared #9733's size floor, became Braves 11% and,
    through ``with_complements``, Phillies 89%, while Kalshi read Atlanta 71%.

    A trade fills at resting prices, so it prints at the edge of the book it
    hit or, when it eats more than the top level, beyond it. Beyond the edge of
    a book wider than ``_poly_book_is_untradeable``'s bar means someone emptied
    what little was left, which says nothing about the market's price.

    ``books`` is ``(latest, previous)`` for the token, each ``(bid, ask)`` or
    None. The venue does not promise whether the post-trade book arrives before
    or after the trade: before, the latest book already lacks the level the
    trade ate (0.11 bid, and 0.1125 sits inside it), so the previous book is
    read too, but only when the latest is also wide. A market whose book has
    come back tight is priced by its midpoint and is not second-guessed here.
    """
    latest = books[0] if books else None
    if latest is None or not _poly_book_is_untradeable(*latest):
        return False
    for book in books:
        if book is None or not _poly_book_is_untradeable(*book):
            continue
        bid, ask = book
        if prob < bid or prob > ask:
            return True
    return False


def with_complements(
    targets: list, prob: float, complement_of: dict
) -> list[tuple[int, float]]:
    """``(leg, price)`` for each leg a tick prices, then each one's complement.

    #9733 follow-on. A price for one token of a binary is also a price for the
    other: ``1 - p``. Writing both keeps a Yes/No pair adding to 100 whichever
    token the venue quoted last. Before this, a leg whose own quotes were
    refused or silent kept an old number beside a sibling that moved (Kittle
    524.5+ receiving yards served Yes 77% / No 10%).

    ``complement_of`` holds only the pairs ``complement_pairs`` proved. Any
    other leg comes back alone, at the tick's price, exactly as before. A
    complement that is itself one of ``targets`` keeps its own price.
    """
    priced = [(oid, prob) for oid in targets]
    named = set(targets)
    for oid in targets:
        other = complement_of.get(oid)
        if other is not None and other not in named:
            priced.append((other, round(1.0 - prob, 6)))
            named.add(other)
    return priced


def books_with_complements(
    targets: list, bid: float, ask: float, complement_of: dict
) -> list[tuple[int, float, float]]:
    """``(leg, bid, ask)`` for each leg a book speaks for, then each complement.

    #9934. ``with_complements``' twin for a book instead of a price: the other
    leg of a proved binary is quoted ``1 - ask`` bid, ``1 - bid`` ask. A missing
    bid (0) becomes an ask of 1.0, which ``book_refutes_price`` can never exceed.
    """
    judged = [(oid, bid, ask) for oid in targets]
    named = set(targets)
    for oid in targets:
        other = complement_of.get(oid)
        if other is not None and other not in named:
            judged.append((other, round(1.0 - ask, 6), round(1.0 - bid, 6)))
            named.add(other)
    return judged


async def withdraw_book_refuted_prices(session, books: dict) -> list:
    """Withdraw each held price its leg's current wide book prices out (#9934).

    WHAT A READER SAW. ``/events/15321782`` (PHI @ ATL, Wild Card G2, Top 10th,
    PHI 4–3, 2026-09-30 21:06Z): the Polymarket series card read Braves 93 /
    Phillies 8 while Kalshi read Atlanta 55. The Braves leg held 0.925 from a
    trade at 20:29Z, when ATL led 3–1. By 21:08Z the Braves token's book was
    0.28 bid / 0.91 ask: anyone could buy Braves at 91c, so 92.5 was no longer a
    price. ``handle_price`` refuses a wide book's midpoint (#1578), which is
    right, and that refusal was the only thing it did with the book.

    THE RULE IS #9399's, ported to the socket. ``books`` is ``{leg: (bid, ask)}``
    from the latest wide book per leg. Each stored ``current_probability`` is
    asked ``book_refutes_price`` — #5121's predicate with its half-cent
    tolerance and its empty-book carve-out — and a refuted one is withdrawn:
    the two rendered columns go to NULL, ``price_changed_at`` moves (a price
    going away is a move), ``last_updated`` does not (no price is fresher than
    the one withdrawn), and a crowned or graded row is never touched. Each
    UPDATE re-asserts the value it read. A price inside the book is kept: a
    skip is still a skip.

    Returns the withdrawn rows as ``(id, market_id, last_updated)``.
    """
    if not books:
        return []
    from sqlalchemy import select, update
    from app.models.models import FuturesOutcome
    from app.utils.kalshi_empty_book import book_refutes_price
    from app.utils.price_change_stamp import price_changed_at_value

    table = FuturesOutcome.__table__
    rows = (
        await session.execute(
            select(table.c.id, table.c.current_probability).where(
                table.c.id.in_(sorted(books)),
                table.c.current_probability.isnot(None),
                table.c.is_winner.isnot(True),
                table.c.resolution_source.is_(None),
            )
        )
    ).all()
    withdrawn = []
    for outcome_id, stored in rows:
        bid, ask = books[outcome_id]
        if not book_refutes_price(bid, ask, float(stored)):
            continue
        result = await session.execute(
            update(table)
            .where(
                table.c.id == outcome_id,
                table.c.current_probability == stored,
                table.c.is_winner.isnot(True),
                table.c.resolution_source.is_(None),
            )
            .values(
                current_probability=None,
                current_american_odds=None,
                price_changed_at=price_changed_at_value(
                    table.c.current_probability, table.c.price_changed_at, None
                ),
            )
            .returning(table.c.id, table.c.market_id, table.c.last_updated)
        )
        withdrawn.extend(result.all())
    return withdrawn


#: #10090 — `owed_chart_points.source` for a committed explicit Polymarket
#: withdrawal whose source removal is still owed. Distinct from 'polymarket':
#: each chart drain reads only its own source exactly (`OwedChartCustody.load`),
#: so neither drain nor any chart reader ever sees one of these rows.
PM_WITHDRAWAL_DEBT_SOURCE = "polymarket_withdrawal"
#: Rows memory takes per load. A fuller table is read again on the next flush.
PM_WITHDRAWAL_DEBT_LOAD_LIMIT = 1024
#: A failed load is tried again at most this often.
PM_WITHDRAWAL_DEBT_RETRY_S = 30.0


class PMWithdrawal(NamedTuple):
    """One leg whose explicit withdrawal still owes its source removal."""

    id: int  #: the `futures_outcomes` leg
    market_id: int
    last_updated: Optional[datetime]  #: the observation the withdrawal cleared
    event_id: int
    #: Its `owed_chart_points` row; None for a book-qualified stray (`strays`).
    custody_id: Optional[int]
    #: Stray only: the row's `price_changed_at`, which must follow the basis.
    changed_at: Optional[float] = None


class PMWithdrawalMarketPublisher:
    """One market sender, coalesced pending plain frames, no retained session.

    A withdrawal's market signal must not gate its event-source removal or the
    next game price. Market signals invalidate REST reads, so the existing
    per-market union/max/terminal coalescing also applies between flushes.
    """

    def __init__(self):
        self.pending: list[dict] = []
        self.task: Optional[asyncio.Task] = None

    def enqueue(self, session, refresher):
        from app.utils.market_quote_push import (
            take_committed_market_changes, coalesce_market_changes,
        )
        self.pending = coalesce_market_changes(
            self.pending + take_committed_market_changes(session),
        )
        self.start(refresher)

    def _observe(self, task):
        if not task.cancelled() and task.exception() is not None:
            logger.error("Polymarket WS: market publication owner failed", exc_info=task.exception())

    def start(self, refresher):
        if self.task is not None and self.task.done():
            task, self.task = self.task, None
            self._observe(task)
        if self.task is None and self.pending:
            self.task = asyncio.create_task(
                self._send(refresher), name="polymarket-withdrawal-market-publish",
            )

    async def offer(self, session, refresher, *, background=False):
        self.enqueue(session, refresher)
        if not background:
            await self.join()

    async def _send(self, refresher):
        from app.utils.market_quote_push import coalesce_market_changes

        while self.pending:
            changes, self.pending = self.pending, []
            try:
                await refresher.publish_market_frames(changes)
            except BaseException as exc:
                # A canceled sender still owns its detached committed batch.
                # Newer pending observations win the ordinary coalescing rule.
                self.pending = coalesce_market_changes(changes + self.pending)
                if not isinstance(exc, Exception):
                    raise
                logger.exception("Polymarket WS: market publication owner failed")
                return  # a later flush/final drain can start the retained work

    async def join(self, *, cancel=False):
        task = self.task
        if task is None:
            return
        interrupted = None
        if cancel and not task.done():
            task.cancel()
        try:
            while not task.done():
                try:
                    await asyncio.wait({task})
                except asyncio.CancelledError as exc:
                    if not cancel:
                        raise  # this waiter does not own the shared sender
                    interrupted = exc
            self._observe(task)
        finally:
            if task.done() and self.task is task:
                self.task = None
        if interrupted is not None:
            raise interrupted


class PMWithdrawalOwnershipDeferred(RuntimeError):
    """Withdrawal remains owed while this consumer lacks ownership."""


class PMWithdrawalDebt:
    """#10090 — durable custody of committed withdrawals until removal settles.

    WHY. The price withdrawal commits on its own, so it never waits on the
    event row (attempt85), and the source removal follows in a second
    transaction. Held only in memory, that removal was lost when the process
    died between the two, when cancellation cut off a commit's acknowledgement,
    or when the final drain's removal failed. So each withdrawn leg on a live
    event is also a row in `owed_chart_points` under its own source:

    * `record` INSERTs it in the price-withdrawal transaction, so the withdrawal
      commits only with its row. No foreign key: the insert locks no event.
    * `settle` DELETEs it first in the removal transaction, so removal and
      settlement commit together or not at all, and a row another process
      already settled is never attributed again.
    * `load` reads the rows memory does not hold, oldest first, when the
      consumer starts. Recovery needs no new book and no catalog membership.

    The exact ``polymarket_withdrawal_owner`` source is a separate, persistent
    coordination row: event_id/value are 0 and reading holds the owner token.
    Claiming a replacement updates it under an exclusive row lock; both
    withdrawal transaction bodies hold its shared lock through commit. It is
    not owed chart/notification work and is excluded from drain counts by its
    exact source, never a prefix. Do not delete it as a cleanup operation.

    Startup recovery adopts both withdrawal and notification custody after
    claiming ownership. Existing recovery stays active through worker changes;
    completeness across old unguarded writers requires the separate transition
    boundary and a subsequent guarded startup scan.

    Only the RETURNING rows of the withdrawal UPDATE become debt. A stored NULL
    alone never does; `strays` admits one only with a fresh untradeable book and
    a `price_changed_at` after the observation the source carries.
    """

    def __init__(self):
        #: custody id -> debt, mirroring the durable rows this process holds.
        self.owed: dict[int, PMWithdrawal] = {}
        self.loaded = False
        self._startup_recovery_logged = False
        self._startup_recovery_rows = [0, 0]
        self._load_running = False
        self._uncertain_commit = False
        self._uncertain_xids: set[str] = set()
        self._unknown_outcomes = 0
        from uuid import uuid4
        self._owner_token = str(uuid4())
        self._owner_id = None
        self._owner_claim_at = 0.0
        self._owner_warning_sent = False
        self._recovery_scan_at = 0.0
        self.publications: dict[int, dict] = {}
        self._publication_task: Optional[asyncio.Task] = None
        self._peer_publication_task: Optional[asyncio.Task] = None
        self._publication_claims: dict[asyncio.Task, dict[int, dict]] = {}
        self._publication_attempted: set[int] = set()
        self._publication_retry_at = 0.0
        self._publication_failures = 0
        # One debt owner is created per consumer; its only final drain may
        # cross many chunk boundaries/passes. Each custody row gets one final
        # attempt, including rows discovered or committed during that drain.
        self._final_publication_attempted: set[int] = set()
        self._retry_at = 0.0
        #: stray leg -> the `price_changed_at` already judged, so a repeated
        #: wide book on the same stored NULL is not judged again.
        self._judged: dict[int, float] = {}

    async def _claim_owner(self, sessions):
        """Fence old withdrawal writers before this consumer's first scan."""
        if self._owner_id is not None:
            return True
        if time.monotonic() < self._owner_claim_at:
            return False
        self._owner_claim_at = time.monotonic() + 0.25
        from sqlalchemy import select, insert, update, text
        from app.models.models import OwedChartPoint
        owner_source = PM_WITHDRAWAL_DEBT_SOURCE + "_owner"
        async with sessions() as db:
            locked = (await db.execute(text(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"
            ), {"key": owner_source})).scalar_one()
            if not locked:
                return False
            row_id = (await db.execute(select(OwedChartPoint.id).where(
                OwedChartPoint.source == owner_source
            ).with_for_update(nowait=True))).scalar_one_or_none()
            if row_id is None:
                row_id = (await db.execute(insert(OwedChartPoint).values(
                    event_id=0, source=owner_source, value=0.0,
                    reading={"owner": self._owner_token},
                ).returning(OwedChartPoint.id))).scalar_one()
            else:
                # FOR SHARE in every old transaction blocks this handoff until
                # that transaction's commit/rollback is definitive.
                await db.execute(update(OwedChartPoint).where(
                    OwedChartPoint.id == row_id,
                ).values(reading={"owner": self._owner_token}))
            await db.commit()
        self._owner_id = row_id  # only after the claim commit is acknowledged
        return True

    def _defer_owner(self, reason):
        if not self._owner_warning_sent:
            logger.warning("Polymarket WS: withdrawal ownership deferred: %s", reason)
            self._owner_warning_sent = True
        raise PMWithdrawalOwnershipDeferred(reason)

    async def guard_owner(self, session):
        from sqlalchemy import select
        from app.models.models import OwedChartPoint
        if self._owner_id is None:
            self._defer_owner("withdrawal ownership not acquired")
        # Look up the canonical source, not the remembered row id: deletion
        # followed by another owner's insertion must still fence this token.
        reading = (await session.execute(select(OwedChartPoint.reading).where(
            OwedChartPoint.source == PM_WITHDRAWAL_DEBT_SOURCE + "_owner",
        ).with_for_update(read=True))).scalar_one_or_none()
        if reading is None:
            # Only absence allows re-claim. A different token remains fenced.
            self._owner_id = None
            self.loaded = False
            self._retry_at = 0.0
            self._defer_owner("withdrawal ownership row missing")
        if not isinstance(reading, dict) or reading.get("owner") != self._owner_token:
            self._defer_owner("withdrawal ownership superseded")

    def legs(self) -> dict[int, int]:
        """Owed leg -> its event."""
        return {debt.id: debt.event_id for debt in self.owed.values()}

    def require_reload(self, *, uncertain=True, xid=None):
        if not uncertain or xid is None:
            self.loaded = False
        if uncertain:
            if xid is None:
                # Unknown identity cannot be expired on a wall clock.
                self._uncertain_commit = True
            else:
                self._uncertain_xids.add(str(xid))

    @property
    def _outcome_pending(self):
        return self._uncertain_commit or bool(self._uncertain_xids)

    async def load(self, sessions) -> int:
        """Move durable rows memory does not hold into memory. Never raises."""
        now = time.monotonic()
        # Urgent commit discovery has its own250ms budget. An older ordinary
        # load failure must not impose its30s gate on an uncertain outcome.
        if self._load_running or (not self._outcome_pending and now < self._retry_at):
            return 0
        if self._outcome_pending:
            if now < self._recovery_scan_at:
                return 0
            # Claim the next slot before awaiting so all three callers share
            # one recovery scan budget, including when a query is slow.
            self._recovery_scan_at = now + 0.25
        elif self.loaded:
            return 0
        from sqlalchemy import select, text

        from app.models.models import OwedChartPoint

        query = select(
            OwedChartPoint.id, OwedChartPoint.event_id, OwedChartPoint.reading,
            OwedChartPoint.source,
        ).where(OwedChartPoint.source.in_([
            PM_WITHDRAWAL_DEBT_SOURCE, PM_WITHDRAWAL_DEBT_SOURCE + "_publish",
        ]))
        known = set(self.owed) | set(self.publications)
        if known:
            query = query.where(OwedChartPoint.id.not_in(sorted(known)))
        self._load_running = True
        resolved = set()
        try:
            if not await self._claim_owner(sessions):
                return 0
            async with sessions() as session:
                pending = sorted(self._uncertain_xids)
                if pending:
                    try:
                        # A rejected xid must not abort the READ COMMITTED
                        # custody scan in this same recovery opportunity.
                        async with session.begin_nested():
                            statuses = (await session.execute(text(
                                "SELECT xid, pg_xact_status(xid::xid8) "
                                "FROM unnest(CAST(:xids AS text[])) AS xid"
                            ), {"xids": pending})).all()
                    except Exception:
                        statuses = [(xid, None) for xid in pending]
                    unknown = sum(status not in {"committed", "aborted", "in progress"}
                                  for _, status in statuses)
                    if unknown:
                        if not self._unknown_outcomes:
                            logger.warning("Polymarket WS: transaction outcome unavailable; retaining recovery")
                        self._unknown_outcomes += unknown
                    aborted = {xid for xid, status in statuses if status == "aborted"}
                    resolved = {xid for xid, status in statuses if status == "committed"}
                    self._uncertain_xids.difference_update(aborted)
                    if not self._outcome_pending and self.loaded:
                        return 0
                rows = (
                    await session.execute(
                        query.order_by(OwedChartPoint.id)
                        .limit(PM_WITHDRAWAL_DEBT_LOAD_LIMIT)
                    )
                ).all()
        except Exception as exc:
            if self._owner_id is None and is_lock_timeout(exc):
                self._retry_at = time.monotonic() + 0.25
                return 0  # expected handoff contention; do not log an outage
            # Cancellation still propagates. The rows stay owed in the table.
            self._retry_at = time.monotonic() + (
                0.25 if self._outcome_pending or self._owner_id is None else PM_WITHDRAWAL_DEBT_RETRY_S
            )
            logger.exception("Polymarket WS: withdrawal debt not loaded; retrying")
            return 0
        finally:
            self._load_running = False
        for custody_id, event_id, reading, source in rows:
            if source == PM_WITHDRAWAL_DEBT_SOURCE + "_publish":
                self.publications[custody_id] = reading["frame"]
                continue
            observed = reading["last_updated"]
            self.owed[custody_id] = PMWithdrawal(
                int(reading["outcome_id"]),
                int(reading["market_id"]),
                None if observed is None else datetime.fromisoformat(observed),
                event_id,
                custody_id,
            )
        self.loaded = len(rows) < PM_WITHDRAWAL_DEBT_LOAD_LIMIT
        if self.loaded:
            # A scan after pg_xact_status reports committed sees that commit.
            # Keep the identity through failures and LIMIT continuation pages.
            self._uncertain_xids.difference_update(resolved)
        if not self._startup_recovery_logged:
            publications = sum(
                source == PM_WITHDRAWAL_DEBT_SOURCE + "_publish"
                for _, _, _, source in rows
            )
            self._startup_recovery_rows[0] += len(rows) - publications
            self._startup_recovery_rows[1] += publications
            if self.loaded:
                logger.info(
                    "Polymarket WS: startup recovery scan complete "
                    "polymarket_withdrawal=%d polymarket_withdrawal_publish=%d",
                    *self._startup_recovery_rows,
                )
                self._startup_recovery_logged = True
        return len(rows)

    async def record(self, session, rows) -> list[PMWithdrawal]:
        """INSERT each withdrawn leg of a live event, in the withdrawal's transaction.

        The caller adopts the returned debt only after that transaction commits.
        A leg with no observation stamp is never attributable, so owes nothing.
        """
        stamped = [row for row in rows if row.last_updated is not None]
        if not stamped:
            return []
        from sqlalchemy import insert, select

        from app.models.models import Event, FuturesMarket, OwedChartPoint

        event_of = dict(
            (
                await session.execute(
                    select(FuturesMarket.id, FuturesMarket.event_id)
                    .join(Event, Event.id == FuturesMarket.event_id)
                    .where(
                        FuturesMarket.id.in_(sorted({row.market_id for row in stamped})),
                        FuturesMarket.source == 'polymarket',
                        Event.status == 'live',
                        Event.completed_at.is_(None),
                    )
                )
            ).all()
        )
        debts = []
        for row in stamped:
            event_id = event_of.get(row.market_id)
            if event_id is None:
                continue
            custody_id = (
                await session.execute(
                    insert(OwedChartPoint)
                    .values(
                        source=PM_WITHDRAWAL_DEBT_SOURCE,
                        event_id=event_id,
                        # A withdrawal owes no chart value; the column is NOT NULL.
                        value=0.0,
                        reading={
                            "outcome_id": row.id,
                            "market_id": row.market_id,
                            "last_updated": row.last_updated.isoformat(),
                        },
                    )
                    .returning(OwedChartPoint.id)
                )
            ).scalar_one()
            debts.append(PMWithdrawal(
                row.id, row.market_id, row.last_updated, event_id, custody_id,
            ))
        return debts

    def adopt(self, debts) -> None:
        for debt in debts:
            self.owed[debt.custody_id] = debt

    async def strays(self, session, legs) -> list[PMWithdrawal]:
        """Stored-NULL legs of live events that a fresh untradeable book names.

        For a leg another writer withdrew first (the REST poll's #9399 arm), or
        whose debt a process lost before `record` existed. Read-only. The removal
        additionally requires `price_changed_at` after the source's basis, so a
        NULL that was never the withdrawal of the observed value removes nothing.
        """
        if not legs:
            return []
        from sqlalchemy import select

        from app.models.models import Event, FuturesMarket, FuturesOutcome

        rows = (
            await session.execute(
                select(
                    FuturesOutcome.id, FuturesOutcome.market_id,
                    FuturesOutcome.last_updated, FuturesOutcome.price_changed_at,
                    FuturesMarket.event_id,
                )
                .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                .join(Event, Event.id == FuturesMarket.event_id)
                .where(
                    FuturesOutcome.id.in_(sorted(legs)),
                    FuturesOutcome.current_probability.is_(None),
                    FuturesOutcome.is_winner.isnot(True),
                    FuturesOutcome.resolution_source.is_(None),
                    FuturesMarket.source == 'polymarket',
                    Event.status == 'live',
                    Event.completed_at.is_(None),
                )
            )
        ).all()
        found = []
        for oid, market_id, last_updated, changed, event_id in rows:
            if last_updated is None or changed is None:
                continue
            if self._judged.get(oid) == changed.timestamp():
                continue
            found.append(PMWithdrawal(
                oid, market_id, last_updated, event_id, None, changed.timestamp(),
            ))
        return found

    async def settle(self, session, debts) -> list[PMWithdrawal]:
        """DELETE the debts' rows first in the removal transaction.

        Returns the debts this transaction now owns: those whose row was still
        owed, and every stray. A row already gone was settled elsewhere.
        """
        ids = sorted({d.custody_id for d in debts if d.custody_id is not None})
        owned: set[int] = set()
        if ids:
            from sqlalchemy import delete

            from app.models.models import OwedChartPoint

            owned = set(
                (
                    await session.execute(
                        delete(OwedChartPoint)
                        .where(
                            OwedChartPoint.id.in_(ids),
                            OwedChartPoint.source == PM_WITHDRAWAL_DEBT_SOURCE,
                        )
                        .returning(OwedChartPoint.id)
                    )
                ).scalars()
            )
        return [d for d in debts if d.custody_id is None or d.custody_id in owned]

    def settled(self, debts) -> None:
        """After the removal transaction commits: nothing here is owed now."""
        for debt in debts:
            if debt.custody_id is None:
                self._judged[debt.id] = debt.changed_at
            else:
                self.owed.pop(debt.custody_id, None)

    async def record_publications(self, session, frames):
        """Custody commits atomically with source removal and its revision."""
        from sqlalchemy import insert
        from app.models.models import OwedChartPoint
        pending = {}
        for frame in frames:
            cid = (await session.execute(insert(OwedChartPoint).values(
                source=PM_WITHDRAWAL_DEBT_SOURCE + "_publish",
                event_id=frame["event_id"], value=0.0, reading={"frame": frame},
            ).returning(OwedChartPoint.id))).scalar_one()
            pending[cid] = frame
        return pending

    def _defer_publication(self):
        # Publication recovery has its own budget: the catalog/debt-load retry
        # is 30s. First failure retries after one game period; persistent faults
        # back off to2s without stopping healthy price delivery.
        self._publication_failures += 1
        delay = min(2.0, 0.25 * (2 ** min(self._publication_failures - 1, 3)))
        self._publication_retry_at = time.monotonic() + delay

    def _observe_publication(self, task):
        """A failed recovery owner must never fail its caller's price loop."""
        if task not in self._publication_claims:
            return
        self._publication_claims.pop(task)
        if self._publication_task is task:
            self._publication_task = None
        if self._peer_publication_task is task:
            self._peer_publication_task = None
        if task.cancelled():
            self._defer_publication()
            return
        error = task.exception()
        if error is not None:
            self._defer_publication()
            logger.error("Polymarket WS: publication owner failed; custody retained",
                         exc_info=error)

    async def join_publications(self, *, cancel=False):
        """Ordinary joiner cancellation leaves the shared owners running.

        Teardown explicitly cancels and joins them, retaining durable custody.
        Failed owners are observed, never raised into a healthy caller.
        """
        tasks = list(self._publication_claims)
        if not tasks:
            return
        if cancel:
            for task in tasks:
                if not task.done() and not task.cancelling():
                    task.cancel()
        interrupted = None
        while any(not task.done() for task in tasks):
            try:
                await asyncio.wait(tasks)
            except asyncio.CancelledError as exc:
                if not cancel:
                    raise
                interrupted = exc
                for task in tasks:
                    if not task.done() and not task.cancelling():
                        task.cancel()
        for task in tasks:
            self._observe_publication(task)
        if interrupted is not None:
            raise interrupted

    async def publish_pending(self, refresher, sessions, *, background=False, final=False):
        """Two bounded sends; custody and event claims never overlap."""
        for task in list(self._publication_claims):
            if task.done():
                self._observe_publication(task)
        if len(self._publication_claims) < 2:
            claimed_ids = {cid for batch in self._publication_claims.values() for cid in batch}
            claimed_events = {frame["event_id"] for batch in self._publication_claims.values()
                              for frame in batch.values()}
            retry_ready = time.monotonic() >= self._publication_retry_at
            pending = {cid: frame for cid, frame in self.publications.items()
                       if cid not in claimed_ids and frame["event_id"] not in claimed_events
                       and ((cid not in self._final_publication_attempted) if final else
                            (cid not in self._publication_attempted or retry_ready))}
            if pending:
                self._publication_attempted.update(pending)
                if final:
                    self._final_publication_attempted.update(pending)
                task = asyncio.create_task(
                    self._publish_pending(refresher, sessions, final, pending),
                    name="polymarket-withdrawal-publication",
                )
                self._publication_claims[task] = pending
                if self._publication_task is None:
                    self._publication_task = task
                else:
                    self._peer_publication_task = task
        if not background:
            await self.join_publications()

    async def _publish_pending(self, refresher, sessions, final=False, pending=None):
        try:
            await self._publish_pending_once(refresher, sessions, final, pending)
        except Exception:
            # SELECT, DELETE, context close and unexpected transport errors
            # all preserve durable custody. Cancellation remains cancellation.
            self._defer_publication()
            logger.exception("Polymarket WS: publication recovery failed; retrying")

    async def _publish_pending_once(self, refresher, sessions, final=False, pending=None):
        """Retry owed invalidations, retaining exact original revisions.

        The transport makes one bounded attempt. Durable retries may duplicate
        an acknowledged-but-unsettled frame; they never mint a new revision.
        """
        if pending is None:
            pending = {cid: frame for cid, frame in self.publications.items()
                       if not final or cid not in self._final_publication_attempted}
        if not pending:
            return
        if final:
            # Claim before any await, including a failed SELECT or send.
            # Later final calls may attempt NEW custody, never replay this
            # failed set while the price drain is trying to finish.
            self._final_publication_attempted.update(pending)
        from sqlalchemy import select
        from app.models.models import Event
        async with sessions() as session:
            rows = (await session.execute(select(
                Event.id, Event.win_probability_sources_rev,
                Event.status, Event.completed_at,
            ).where(Event.id.in_({f["event_id"] for f in pending.values()})))).all()
            current = {eid: (rev, status, completed_at)
                       for eid, rev, status, completed_at in rows}
        # Completion can change without changing the source revision.
        # Never replay a live invalidation for an already terminal event.
        obsolete = {cid for cid, frame in pending.items()
                    if current.get(frame["event_id"], (None, None, None))[1:]
                    != ("live", None)}
        controls = []
        for cid, frame in pending.items():
            if cid in obsolete:
                continue
            # A newer sibling price does not prove the reader adopted the
            # removal or its history. Keep original identity and revision.
            controls.append({**frame, "reconcile": {
                "event_id": frame["event_id"],
                "custody_id": f"pm-withdrawal:{cid}",
                "removal_rev": dict(frame["rev"]),
            }, "reconcile_only": current[frame["event_id"]][0]
                != frame["rev"][str(frame["event_id"]) ]})
        acknowledged = await _publish_committed_withdrawals(refresher, controls)
        ids = [cid for cid, frame in pending.items()
               if cid in obsolete or (frame["event_id"], frame["rev"][str(frame["event_id"])])
               in (acknowledged or set())]
        if not ids:
            self._defer_publication()
            return
        from sqlalchemy import delete
        from app.models.models import OwedChartPoint
        # Deletion failure/cancellation retains the row for safe replay.
        async with sessions() as session:
            await session.execute(delete(OwedChartPoint).where(
                OwedChartPoint.id.in_(ids),
                OwedChartPoint.source == PM_WITHDRAWAL_DEBT_SOURCE + "_publish",
            ))
        for cid in ids:
            self.publications.pop(cid, None)
            self._publication_attempted.discard(cid)
        if any(cid not in ids for cid in pending):
            self._defer_publication()
        elif not self.publications:
            self._publication_retry_at = 0.0
            self._publication_failures = 0


async def withdraw_attributed_event_sources(session, withdrawn_rows):
    """#10090: remove only a PM source whose speaker was explicitly withdrawn.

    Runs in its own transaction after the price withdrawal committed (never
    inside it: the price must not wait on the event row). ``withdrawn_rows``
    are `PMWithdrawal` debts `PMWithdrawalDebt.settle` already owns in this
    transaction. Returns frames to publish AFTER COMMIT. An ordinary missing
    reading never reaches this path.
    """
    from sqlalchemy import select, update, func
    from app.models.models import Event, FuturesMarket, WinProbSnapshot
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from app.utils.live_blend import compute_source_home_probability
    from app.utils.live_push import build_frame

    by_market = {}
    withdrawn_observations = {}
    changed_after = {}
    for row in withdrawn_rows:
        oid = str(row.id)
        by_market.setdefault(row.market_id, set()).add(oid)
        stamp = None if row.last_updated is None else row.last_updated.timestamp()
        # Two committed withdrawals of one leg: the newer observation bounds it.
        if stamp is None:
            withdrawn_observations.setdefault(oid, None)
        elif withdrawn_observations.get(oid) is None or stamp > withdrawn_observations[oid]:
            withdrawn_observations[oid] = stamp
        if getattr(row, "changed_at", None) is not None:
            changed_after[oid] = row.changed_at
    if not by_market:
        return []
    event_ids = set((await session.execute(
        select(FuturesMarket.event_id).where(
            FuturesMarket.id.in_(by_market),
            FuturesMarket.source == 'polymarket',
            FuturesMarket.event_id.isnot(None),
        )
    )).scalars())
    if not event_ids:
        return []
    # Re-read the whole source population in the removal transaction, after
    # the independent price withdrawal committed. A newly stored quote wins.
    # This transaction helper has no consumer shutdown/drain lifecycle.
    # It reads ordinary DNPL context but cannot own background maintenance.
    groups = await LiveBlendRefresher(
        'polymarket', owns_preview_maintenance=False,
    )._read_groups(session, sorted(event_ids))
    frames = []
    for event_id, (event, group) in groups.items():
        if event.status != 'live' or event.completed_at is not None:
            continue
        prior = (event.win_probability_sources or {}).get('polymarket')
        if not isinstance(prior, dict):
            continue
        eligibility = prior.get('eligibility')
        market_id = eligibility.get('market_id') if isinstance(eligibility, dict) else None
        basis = prior.get('observed_basis')
        if (market_id not in by_market or not isinstance(basis, dict)
                or by_market[market_id].isdisjoint(basis)):
            continue
        # IDs alone are insufficient: the same leg may already have a newer
        # stamped overlay. The withdrawal only owns observations no newer than
        # the actual row it cleared. Both stamps use the database clock domain.
        # A stray also needs its price to have changed after that observation.
        matched = by_market[market_id].intersection(basis)
        if any(
            isinstance(basis[oid], bool)
            or not isinstance(basis[oid], (int, float))
            or not math.isfinite(basis[oid])
            or withdrawn_observations[oid] is None
            or basis[oid] > withdrawn_observations[oid]
            or (oid in changed_after and not basis[oid] < changed_after[oid])
            for oid in matched
        ):
            continue
        if compute_source_home_probability(group, event.home_team_name, event.away_team_name) is not None:
            continue
        removed = (await session.execute(
            update(Event).where(
                Event.id == event_id, Event.status == 'live', Event.completed_at.is_(None),
                Event.win_probability_sources['polymarket'] == prior,
            ).values(
                win_probability_sources=Event.win_probability_sources.op('-')('polymarket'),
            ).returning(
                Event.win_probability_sources_rev, Event.status, func.clock_timestamp(),
            ).execution_options(synchronize_session=False)
        )).first()
        if removed is None:
            continue  # newer source/terminal state won while this read was pending
        revision, status, removed_at = removed
        # A NULL history vertex stops carry-forward; it is not a fabricated
        # zero probability. It commits with the source removal or neither does.
        session.add(WinProbSnapshot(
            event_id=event_id, source='polymarket', captured_at=removed_at,
            home_win_probability=None, away_win_probability=None,
            valid_until=removed_at, game_state={'live_source_withdrawal': True},
        ))
        frame = build_frame(event_id=event_id,
            probability=None, source=None,
            source_value=None, updated_at=removed_at.isoformat(), status=status, rev=revision)
        frame['invalidation'] = True
        frames.append(frame)
    return frames


async def _publish_committed_withdrawals(refresher, frames):
    """Own one bounded event send after commit, even if the caller cancels.

    No retry of an ambiguous Redis send. The existing publisher bounds its
    attempt; this owner joins it before allowing cancellation to leave.
    """
    if not frames:
        return
    import asyncio

    previews = []
    for frame in frames:
        if frame.get('reconcile_only'):
            continue  # old control cannot invalidate a newer writer cache
        event_id = frame['event_id']
        refresher._last_written_value.pop(event_id, None)
        refresher._last_refresh_at.pop(event_id, None)
        refresher._last_snapshot_at.pop(event_id, None)
        if event_id in getattr(refresher, 'preview_events', ()):
            # #10090 (preview arm, canary events only): the withdrawn source
            # may not keep speaking in a provisional blend.
            from app.utils.blend_preview import registry

            previews.extend(registry().refused(event_id, refresher.source, 'withdrawn'))
    task = asyncio.create_task(
        refresher._publish(frames), name='polymarket-withdrawal-event-publish',
    )
    interrupted = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            if task.cancelled():
                raise
            interrupted = exc
    acknowledged = task.result()
    if interrupted is not None:
        raise interrupted
    if previews:
        # After the invalidation, whose newer revision already hides them.
        await refresher._publish_previews(previews)
    return acknowledged


class _PMPriceWriteResult:
    """A committed acknowledgement; only written rows may stage fresh receipts."""

    def __init__(self, written_ids, *, clock_owner=None):
        self.written_ids = tuple(written_ids)
        self.clock_owner = clock_owner


PM_QUOTE_LIVENESS_SECONDS = 30.0

#: #10090: PostgreSQL's server message when a NOWAIT row lock on the price
#: table is refused. A lock_timeout cancellation shares its SQLSTATE (55P03)
#: but reads "canceling statement due to lock timeout".
PRICE_ROW_LOCK_REFUSAL_MESSAGE = (
    'could not obtain lock on row in relation "futures_outcomes"'
)


def is_price_row_lock_refusal(exc: BaseException) -> bool:
    """True iff ``exc`` is PostgreSQL refusing a NOWAIT row lock on the price table.

    Identified by what the database said, not by how long the answer took to
    arrive: a refusal received 60 ms late is still a refusal that waited for
    nothing. Narrowly positive — the SQLSTATE and the exact server message must
    sit on the same driver exception (asyncpg's ``message``, psycopg's
    ``diag.message_primary``). A lock_timeout cancellation, a localised or
    unrecognised message, or any other error returns False and keeps the
    caller's ordinary cooldown. ``is_lock_timeout`` is unchanged.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        message = getattr(cur, "message", None)
        if not isinstance(message, str):
            message = getattr(getattr(cur, "diag", None), "message_primary", None)
        if code == LOCK_NOT_AVAILABLE_SQLSTATE and message == PRICE_ROW_LOCK_REFUSAL_MESSAGE:
            return True
        nxt = getattr(cur, "orig", None)
        if nxt is None or nxt is cur:
            nxt = cur.__cause__
        cur = nxt
    return False


def is_price_statement_timeout(exc: BaseException) -> bool:
    """Require PostgreSQL's statement-timeout diagnostic, not just 57014.

    Operator cancellation shares 57014. Unknown/localised messages stay on
    the ordinary failure path; elapsed time never authorizes held admission.
    """
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        message = getattr(cur, "message", None)
        if not isinstance(message, str):
            message = getattr(getattr(cur, "diag", None), "message_primary", None)
        if code == "57014" and message == "canceling statement due to statement timeout":
            return True
        nxt = getattr(cur, "orig", None)
        if nxt is None or nxt is cur:
            nxt = cur.__cause__
        cur = nxt
    return False


def chunk_price_update_stmt(chunk: dict, force_ids=None, nowait=False):
    """#10664: a flush chunk's price writes as ONE UPDATE ... RETURNING.

    ``write_chunk`` awaited one UPDATE per outcome — 500 round trips for a full
    chunk before its commit and publication. One statement now preserves:

    * the SAME set clause: the price bound as ``NUMERIC(7, 6)`` and compared as
      ``FLOAT`` through :func:`price_changed_at_value`, exactly as the per-row
      statement binds them, so rounding and the change-stamp cannot drift;
    * the SAME row-lock order: ``locked`` takes the row locks one at a time in
      chunk order (``ORDER BY ord ... FOR UPDATE``; LockRows runs above the
      Sort), as the per-row loop did, so the binary-pair and lock-cycle work
      that reasons about that order still holds;
    * returned-row attribution: a buffered id whose row is gone joins nothing
      and returns nothing; ``ord`` names only rows actually written. Unchanged
      database prices are acknowledged without locks/writes unless the caller
      forces a first observation or a bounded real liveness write.

    One parameter per column (arrays), so the prepared statement is shared by
    every chunk size.

    #10090 ``nowait``: take the row locks ``NOWAIT``. A refusal raises the same
    ``lock_not_available`` (55P03) as a lock timeout, so the caller's retained
    rows, cooldown and rollback boundary are unchanged; only the wait is gone.
    """
    from sqlalchemy import (
        ARRAY,
        Boolean,
        Float,
        Integer,
        Numeric,
        bindparam,
        cast,
        column,
        func,
        or_,
        select,
        update,
    )
    from app.models.models import FuturesOutcome
    from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column

    table = FuturesOutcome.__table__
    prices = list(chunk.values())
    forced = set(chunk) if force_ids is None else force_ids
    given = (
        func.unnest(
            bindparam("chunk_ids", list(chunk), type_=ARRAY(Integer)),
            bindparam("chunk_prices", prices, type_=ARRAY(Numeric(7, 6))),
            bindparam("chunk_compare", prices, type_=ARRAY(Float)),
            bindparam("chunk_force", [oid in forced for oid in chunk], type_=ARRAY(Boolean)),
        )
        .table_valued(
            column("id", Integer),
            column("price", Numeric(7, 6)),
            column("compared", Float),
            column("force_write", Boolean),
            with_ordinality="ord",
        )
        .render_derived(name="given")
    )
    locked = (
        select(table.c.id, given.c.ord, given.c.price, given.c.compared)
        .join_from(given, table, table.c.id == given.c.id)
        # Compare against the DATABASE value at its stored precision. A local
        # repeated tick still repairs a price changed by another writer. Put
        # this before LockRows so an unchanged row does not acquire a lock.
        .where(or_(
            given.c.force_write,
            table.c.current_probability.is_distinct_from(
                cast(given.c.price, table.c.current_probability.type)
            ),
        ))
        .order_by(given.c.ord)
        .with_for_update(of=table, nowait=nowait)
        .cte("locked")
        .prefix_with("MATERIALIZED")
    )
    return (
        update(table)
        .where(table.c.id == locked.c.id)
        .values(
            current_probability=locked.c.price,
            last_updated=func.now(),
            price_changed_at=price_changed_at_value(
                table.c.current_probability, table.c.price_changed_at, locked.c.compared
            ),
        )
        .returning(
            locked.c.ord,
            table.c.id,
            table.c.market_id,
            table.c.last_updated,
            quote_moved_column(table),
            func.clock_timestamp().label("database_clock"),
            # #10090 `preview_from_commit`: the committed row's resolver
            # inputs, so its preview is composed without reading it back.
            table.c.current_probability,
            table.c.is_winner,
            table.c.resolution_source,
        )
    )


def _pm_lock_isolated_chunks(
    chunks: list[list[int]],
    retry_events: set[int],
    event_by_outcome: dict[int, int],
    market_by_outcome: dict[int, int],
    complement_of: dict[int, int],
    chunk_rows: int,
    *, first_events: Iterable[int] = (),
) -> list[list[int]]:
    """Isolate selected admitted event cohorts without splitting questions.

    Callers select lock retries or acknowledged optional observation cohorts.
    Changed preview events may go first only when none of their indivisible
    units shares an outside event. Selection never bypasses the ordinary writer.

    The caller passes separately planned headline and prop transactions. Never
    admit another buffered row or change the open cap here. Within the admitted
    population a whole question and its complements stay indivisible; an
    oversized question keeps one transaction rather than exposing half of it.
    Unaffected rows retain their original chunks and order, ahead of the
    retried cohorts they share no event with.
    """
    first_events = set(first_events).difference(retry_events)
    if not retry_events and not first_events:
        return chunks
    admitted = [oid for chunk in chunks for oid in chunk]
    parents = {oid: oid for oid in admitted}

    def root(oid):
        while parents[oid] != oid:
            parents[oid] = parents[parents[oid]]
            oid = parents[oid]
        return oid

    def join(left, right):
        parents[root(right)] = root(left)

    first_by_market = {}
    for oid in admitted:
        market = market_by_outcome.get(oid)
        if market is not None:
            if market in first_by_market:
                join(first_by_market[market], oid)
            else:
                first_by_market[market] = oid
        other = complement_of.get(oid)
        if other in parents:
            join(oid, other)
    units = {}
    for oid in admitted:
        units.setdefault(root(oid), []).append(oid)
    if first_events:
        # Only promote complete events whose indivisible units share no outside
        # event. Propagate exclusion through shared units so no sibling of a
        # promoted event remains behind the unrelated transaction.
        unit_events = [
            {event_by_outcome[oid] for oid in unit if oid in event_by_outcome}
            for unit in units.values()
        ]
        while True:
            blocked = set().union(*(events for events in unit_events
                                    if not events.issubset(first_events)))
            kept = first_events.difference(blocked)
            if kept == first_events:
                break
            first_events = kept
    selected_events = set(retry_events) | first_events
    groups = {}
    group_by_outcome = {}
    for unit in units.values():
        events = frozenset(
            event_by_outcome[oid] for oid in unit if oid in event_by_outcome
        )
        if events.isdisjoint(selected_events):
            continue
        groups.setdefault(events, []).append(unit)
        group_by_outcome.update(dict.fromkeys(unit, events))
    packed = {}
    for events, event_units in groups.items():
        packed[events] = []
        current = []
        for unit in event_units:
            if current and len(current) + len(unit) > chunk_rows:
                packed[events].append(current)
                current = []
            current.extend(unit)
        if current:
            packed[events].append(current)
    # A retried cohort is the one most likely still held, and each attempt can
    # wait the full chunk lock budget. Its retained rows also lead the buffer,
    # so first-appearance placement put that wait ahead of the fresh unrelated
    # remainder. Run the remainder first; a cohort sharing an event with a
    # remainder chunk is released ahead of it, in order, so overlapping events
    # keep their write order.
    result = []
    emitted = set()
    held = []
    for chunk in chunks:
        remainder = [oid for oid in chunk if oid not in group_by_outcome]
        remainder_emitted = False
        for oid in chunk:
            events = group_by_outcome.get(oid)
            if events is None:
                if not remainder_emitted:
                    remainder_events = {
                        event_by_outcome[o] for o in remainder if o in event_by_outcome
                    }
                    last = max(
                        (i for i, cohort in enumerate(held)
                         if not cohort.isdisjoint(remainder_events)),
                        default=-1,
                    )
                    for cohort in held[: last + 1]:
                        result.extend(packed[cohort])
                    del held[: last + 1]
                    result.append(remainder)
                    remainder_emitted = True
            elif events not in emitted:
                # Each cohort keeps its first-appearance order among cohorts;
                # the unaffected remainder keeps its original transaction.
                held.append(events)
                emitted.add(events)
    for cohort in held:
        result.extend(packed[cohort])
    if first_events:
        first, rest = [], []
        for chunk in result:
            events = {event_by_outcome[oid] for oid in chunk if oid in event_by_outcome}
            (first if events.intersection(first_events) else rest).append(chunk)
        result = first + rest
    return result


def standalone_open_outcome_ids(
    outcome_ids,
    open_outcome_ids,
    event_id_by_outcome: dict,
    complement_of: dict,
) -> set[int]:
    """#10090: the buffered legs no blend reads — open, with no event, and a
    binary partner (if any) with none either.

    These leave the game flush for their own loop, so a standalone chunk's
    write never holds the next game quote. A bridged leg (#10091) feeds its
    event's blend and stays; a pair with one bridged side stays whole on the
    game side (CERT-3868: one transaction or wait together). Read at flush
    time: admission bridges a leg before it marks it open, with no await
    between, so a leg is never standalone ahead of its bridge.
    """
    def eventless_open(oid) -> bool:
        return oid in open_outcome_ids and event_id_by_outcome.get(oid) is None

    standalone: set[int] = set()
    for oid in outcome_ids:
        other = complement_of.get(oid)
        if eventless_open(oid) and (other is None or eventless_open(other)):
            standalone.add(oid)
    return standalone


def legs_in_token_order(pairs: list) -> list:
    """Order one market's ``(outcome_id, external_id)`` legs as its CLOB tokens are.

    #8403. Only a market whose legs are exactly one first-token leg and one
    second-token leg, each named by its own suffix, is reordered. Any other
    shape keeps the id order the caller passed, which is what it did before, so
    a shape nobody measured cannot be moved by this.
    """
    indexed = [(_token_index(ext), oid, ext) for oid, ext in pairs]
    if len(indexed) == 2 and {i for i, _, _ in indexed} == {0, 1}:
        return [(oid, ext) for _, oid, ext in sorted(indexed, key=lambda t: t[0])]
    return list(pairs)


#: #9418: what one ``market_resolved`` push may write, decided before any write.
#:
#: ``winner`` — the CLOB names exactly one winning token and it is a leg of this
#: market; ``void`` — the venue closed the market and paid every token 0.5, so
#: it named no outcome; ``unconfirmed`` — anything else (CLOB unreachable, not
#: yet flipped, disagreeing with the push, a token we cannot place). Only
#: ``winner`` grades; ``void`` records the void; ``unconfirmed`` grades nothing
#: and leaves the market to the Gamma rail, which reads the venue's prices.
WS_RESOLUTION_WINNER = "winner"
WS_RESOLUTION_VOID = "void"
WS_RESOLUTION_UNCONFIRMED = "unconfirmed"

#: Ceiling on the CLOB read behind one resolution. The read retries a 429 at
#: most twice with ≤10 s waits; past this the verdict is ``unconfirmed``.
RESOLUTION_CLOB_TIMEOUT_S = 25.0

#: Polymarket's payout on a void: every token settles at exactly half.
_VOID_PAYOUT = 0.5


def ws_resolution_verdict(
    push_winning_asset_id, clob_market, market_outcome_ids, asset_to_outcome
):
    """Decide what a ``market_resolved`` push may write (#9418). Pure.

    🔴 THE PUSH'S LABEL IS NEVER READ. ``winning_outcome`` is the venue's
    display word for the winning side — ``"Over"``, ``"Stefan Kozlov"``,
    ``"Yes"`` — and the old writer graded a leg only when that word was literally
    yes/no AND the leg's id ended ``_yes``/``_no``. Every other market (totals,
    named sides, and every ``{condition}``/``_side1`` leg) was written with
    BOTH legs ``is_winner=False`` under the tier-3 ``clob_authoritative`` stamp:
    2,471 of the 2,618 markets this socket settled on production 2026-09-30/10-01,
    10 of 12 sampled having a real venue winner (BOS@NYY "O/U 3.5", Over paid
    1/0, both legs stored lost). The winner is named by TOKEN instead, through
    ``asset_to_outcome`` — the same token→leg map every price tick is routed by
    (Q489/#8403), so a leg is graded by the contract it is, never by its
    position or its name.

    🔴 THE TOKEN IS CONFIRMED AGAINST THE CLOB BEFORE IT GRADES. The push's
    ``winning_asset_id`` is optional in the venue's schema and a void is not
    documented on it, so on its own it cannot tell a winner from a void. CLOB
    ``/markets/{condition}`` can: exactly one token ``winner: true`` is a result,
    and every token ``winner: false`` at price 0.5 on a closed market is a void
    (Kozlov v Kim, 15320860: both 0.5, Gamma's "Completed Match" No). Anything
    between — a CLOB that has not flipped yet, two winners, a winner that is not
    the pushed token — is ``unconfirmed``: a wrong tier-3 grade is never
    overwritten by the Gamma rail's void skip, so declining is the only safe
    answer.

    Returns ``(kind, winner_outcome_id)``; the id is set only for ``winner``.
    """
    unconfirmed = (WS_RESOLUTION_UNCONFIRMED, None)
    if not isinstance(clob_market, dict):
        return unconfirmed
    tokens = clob_market.get("tokens")
    if not isinstance(tokens, list) or len(tokens) < 2:
        return unconfirmed
    winners = [t for t in tokens if isinstance(t, dict) and t.get("winner") is True]
    if not winners:
        if clob_market.get("closed") is not True:
            return unconfirmed
        try:
            prices = [float(t.get("price")) for t in tokens]
        except (TypeError, ValueError, AttributeError):
            return unconfirmed
        if all(abs(p - _VOID_PAYOUT) < 1e-9 for p in prices):
            return (WS_RESOLUTION_VOID, None)
        return unconfirmed
    if len(winners) != 1:
        return unconfirmed
    token = str(winners[0].get("token_id") or "")
    if not token:
        return unconfirmed
    if push_winning_asset_id and str(push_winning_asset_id) != token:
        return unconfirmed
    owner = asset_to_outcome.get(token)
    if owner is None or owner not in set(market_outcome_ids):
        return unconfirmed
    return (WS_RESOLUTION_WINNER, owner)


#: Re-asks after a push the venue had not yet confirmed (#9418 after-check),
#: seconds after the previous ask. Measured 2026-10-01 05:3x–06:0xZ on 16 of 16
#: pushes: Gamma closes the market at T, records `umaResolutionStatus:
#: "resolved"` with 0/1 `outcomePrices` by ~T+10 s, the socket push lands at
#: ~T+60 s — and CLOB `/markets` still reads `closed: false`, no winner, more
#: than five minutes later. The first ask therefore almost always answers from
#: Gamma; these cover a Gamma read that is itself a few seconds behind. Total
#: 220 s, inside the 600 s recycle; a recycle that cancels the wait leaves the
#: market where it is today (resolved, ungraded, the Gamma rail's).
RESOLUTION_RECHECK_DELAYS_S = (10.0, 30.0, 60.0, 120.0)


def _price_list(raw) -> Optional[list]:
    """Gamma serves list fields as JSON strings (``'["0", "1"]'``) or lists."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, list) else None


def gamma_resolution_verdict(
    push_winning_asset_id, gamma_market, market_outcome_ids, asset_to_outcome
):
    """The same decision as :func:`ws_resolution_verdict`, read from Gamma. Pure.

    CLOB `/markets` flips ``winner`` minutes after the venue settles; Gamma's
    record of the same settlement is readable before the push even arrives
    (measured, see :data:`RESOLUTION_RECHECK_DELAYS_S`). It is the record the
    Gamma rail already grades from, so this is not a new authority, only an
    earlier read of it — under the same rules:

    - only a market Gamma calls ``closed`` with ``umaResolutionStatus ==
      "resolved"`` is read at all (a price at 0.999 is a market, not a result);
    - the winner is a TOKEN: ``clobTokenIds`` is index-aligned with
      ``outcomePrices``, exactly one price must be 1 and every other 0, and the
      token at that index must be the push's ``winning_asset_id`` when the push
      names one and must belong to a leg of THIS market via ``asset_to_outcome``
      — never a label, never a position in our rows;
    - every price at exactly 0.5 is a void;
    - anything else is ``unconfirmed``.
    """
    unconfirmed = (WS_RESOLUTION_UNCONFIRMED, None)
    if not isinstance(gamma_market, dict):
        return unconfirmed
    if gamma_market.get("closed") is not True:
        return unconfirmed
    if gamma_market.get("umaResolutionStatus") != "resolved":
        return unconfirmed
    tokens = _price_list(gamma_market.get("clobTokenIds"))
    raw_prices = _price_list(gamma_market.get("outcomePrices"))
    if not tokens or not raw_prices or len(tokens) != len(raw_prices) or len(tokens) < 2:
        return unconfirmed
    try:
        prices = [float(p) for p in raw_prices]
    except (TypeError, ValueError):
        return unconfirmed
    if all(abs(p - _VOID_PAYOUT) < 1e-9 for p in prices):
        return (WS_RESOLUTION_VOID, None)
    winners = [i for i, p in enumerate(prices) if abs(p - 1.0) < 1e-9]
    if len(winners) != 1:
        return unconfirmed
    if any(abs(p) >= 1e-9 for i, p in enumerate(prices) if i != winners[0]):
        return unconfirmed
    token = str(tokens[winners[0]] or "")
    if not token:
        return unconfirmed
    if push_winning_asset_id and str(push_winning_asset_id) != token:
        return unconfirmed
    owner = asset_to_outcome.get(token)
    if owner is None or owner not in set(market_outcome_ids):
        return unconfirmed
    return (WS_RESOLUTION_WINNER, owner)


async def settle_with_rechecks(ask, write, *, delays=None, sleep=None):
    """Write the first answer, then re-ask until the venue decides (#9418).

    ``ask()`` returns a verdict; ``write(verdict)`` applies it. The FIRST answer
    is always written — a settled market reads settled at once — and only an
    ``unconfirmed`` one is re-asked, on ``delays``; the first decided verdict
    is written over it and the loop stops. A write that fails on a re-ask
    propagates, like the first. Returns ``(final verdict, decided_late)``.
    """
    delays = RESOLUTION_RECHECK_DELAYS_S if delays is None else delays
    sleep = asyncio.sleep if sleep is None else sleep
    verdict = await ask()
    await write(verdict)
    if verdict[0] != WS_RESOLUTION_UNCONFIRMED:
        return verdict, False
    for delay in delays:
        await sleep(delay)
        verdict = await ask()
        if verdict[0] != WS_RESOLUTION_UNCONFIRMED:
            await write(verdict)
            return verdict, True
    return verdict, False


async def _apply_ws_resolution(session, market_id, outcomes, verdict):
    """Apply a Polymarket ``market_resolved`` settlement to the DB.

    Queue #261 Item 2: sets ``status='resolved'`` on the market and ``is_winner``
    on its outcomes, routed through the resolution-authority contract — and NEVER
    writes ``calibration_probability``. A terminal price must not both define the
    winner AND grade the earlier/current forecast (self-grading leakage, C20/C21);
    the terminal price still reaches ``current_probability`` via the ordinary
    buffered flush loop, and the published forecast is left to the timestamped
    snapshot pipeline. An outcome already settled by an authoritative source
    (tier 3) is left untouched — a bare websocket push must not downgrade it.

    Queue #284 Item 1: every applied winner write stamps its registered tier-3
    ``resolution_source`` (``clob_authoritative``) in the SAME UPDATE — winner and
    provenance are atomic, so a failed/partial write can never leave a graded
    outcome with a NULL source (which the authority ladder treats as tier -1,
    silently overwritable by a later guess).

    #9418: ``verdict`` is :func:`ws_resolution_verdict`'s ``(kind, winner_id)``.
    Only ``winner`` writes a grade. ``void`` writes the venue's void the way the
    Kalshi sweep does (``venue_voided`` merged into ``market_metadata``, no grade
    — a void names NO outcome, #1852), which is what lets #5811's
    ``venue_closed_no_winner`` speak for a match both venues cancelled.
    ``unconfirmed`` marks the market resolved and grades nothing; the legs stay
    eligible for the Gamma rail exactly as an ungraded resolved market is.

    Module-level (not a closure) so the leakage contract is unit-testable.
    Returns the number of outcome winner-writes applied.
    """
    from sqlalchemy import select, text, update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.tasks.kalshi_resolution_sweep import VOID_UPDATE_SQL
    from app.utils.resolution_authority import is_authoritative

    # A CLOB `market_resolved` push is the venue's own settlement delivered over
    # the socket — the same authority as the CLOB REST resolver
    # (`clob_resolve.py`). Stamp its registered tier-3 source so the winner write
    # carries audit-grade provenance, survives the authority ladder (a later
    # guess-family pass can no longer silently overwrite a NULL-source winner),
    # and is calibration-truth eligible. Do NOT invent a new source string.
    _WS_RESOLUTION_SOURCE = "clob_authoritative"

    kind, winner_id = verdict

    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == market_id)
        .values(status="resolved", **settled_values(FuturesMarket.settled_at))
    )

    if kind == WS_RESOLUTION_VOID:
        # The Kalshi sweep's own statement, unforked: merged, never assigned, so
        # `shape` survives, and the two venues' voids are one fact to every
        # reader (`venue_closed_without_winner`, #7035's retirement).
        await session.execute(
            text(VOID_UPDATE_SQL),
            {"id": market_id, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        return 0

    if kind != WS_RESOLUTION_WINNER or winner_id is None:
        return 0

    outcome_ids = [oid for oid, _ in outcomes]
    existing_sources: dict = {}
    if outcome_ids:
        existing_sources = {
            r.id: r.resolution_source
            for r in (
                await session.execute(
                    select(
                        FuturesOutcome.id, FuturesOutcome.resolution_source
                    ).where(FuturesOutcome.id.in_(outcome_ids))
                )
            ).all()
        }

    written = 0
    for oid, _ext in outcomes:
        if is_authoritative(existing_sources.get(oid)):
            continue  # venue already settled authoritatively — leave it
        # Winner AND provenance in the SAME statement (Queue #284 Item 1): an
        # atomic write means a failed/partial apply can never leave is_winner set
        # with a NULL resolution_source. Deliberately NOT setting
        # calibration_probability here (Queue #261) — no price self-grading.
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == oid)
            .values(
                is_winner=(oid == winner_id),
                resolution_source=_WS_RESOLUTION_SOURCE,
            )
        )
        written += 1
    return written


#: How long after its scheduled start an event that is STILL 'scheduled' may
#: hold a place in the subscription. A start time is not a finish time (gotcha:
#: "scheduled kickoff timestamps are not actual start/finish"), so this is
#: deliberately far longer than any game: a rain-delayed baseball game, a
#: five-set match and a full day of status-updater lag all stay subscribed.
#:
#: It bounds the `scheduled` arm ONLY. Nothing here is ever applied to a live
#: event — see `_slate_event_window`.
#:
#: The exact value is not a judgement call, because the population it cuts is a
#: CLIFF rather than a gradient. Measured on production 2026-09-23 02:5xZ, the
#: slate held nothing at all between 6 h and 48 h old — a floor of 6, 12, 24 or
#: 48 hours each kept the identical 594 markets — while the nearest stale event
#: was 2 days old and the bulk (101 events, 1,175 markets) was the US Open,
#: three weeks finished. 24 h is the widest margin that still costs nothing.
SLATE_MAX_AGE_HOURS = 24


def _slate_event_window():
    """The event window the socket subscribes to — the scheduled arm bounded
    at BOTH ends, the live arm at neither.

    The upper bound (start within 6 h) was always here. The floor was not, and
    without it ``status='scheduled'`` is not a statement about the future: it is
    whatever the status updater last managed to write. Every event that never
    left ``scheduled`` stayed in the subscription forever, so the slate silently
    accumulated months of finished sport.

    Measured on production 2026-09-23 02:5xZ, before this floor existed:

        CURRENT (live, or starting within 6 h) ....  640 markets,  79 events
        STALE   (started > 6 h ago, still
                 'scheduled') ....................  1,248 markets, 107 events
                 oldest commence_time 2026-06-01 — nearly four months

    So **66 % of the subscription was finished sport**, and the venue confirms
    those rows are not merely quiet but gone: of 30 randomly sampled stale
    tokens, 27 answered ``/book`` with *"No orderbook exists for the requested
    token id"*, against 30 of 30 alive for a same-size current control. That is
    the whole of #837's unexplained ``served=1413/3367`` — four contiguous
    shards reading 14/500, 26/500, 36/500, 39/500 while the two holding current
    sport read 500/500 and 488/500. The subscription was not being truncated by
    the venue; we were asking it for dead tokens.

    What that cost a reader, which is why this is a fix and not hygiene: the
    token top-up that gives a market its ``clob_token_ids`` is capped per
    recycle, and its queue was **253 stale against 46 current**. It is ordered
    by a rotating cursor, not by whether anyone is watching, so live games
    waited behind finished ones for a budget 85 % of which could never pay.
    At the moment of the measurement 42 markets on games *in progress* had no
    tokens and therefore no price stream at all — eight MLB games among them,
    including the Dodgers/Padres game filed as #8156.

    THE FLOOR BINDS THE ``scheduled`` ARM ONLY, AND THE LIVE ARM STAYS
    CLOCK-FREE. This is the whole of the fix's shape, so it is worth the
    paragraph. A first draft applied the floor once, above the ``or_()``,
    reasoning that a ``scheduled``-only floor is re-admitted through the wider
    ``live`` sibling the first time an event sticks at ``status='live'``. That
    hazard is real (see below) but the cure regressed the thing #837 exists to
    protect: above the ``or_()`` the 24-hour bound applies to live rows too, so
    an event the graph still calls live is unsubscribed after 24 hours — a
    multi-day tournament, a suspended game, any delayed state advancement. That
    is a hero stream going dark, decided by a clock we do not trust, which is
    the premise of the constant above.

    (The ``IS NOT NULL`` in that draft was inert rather than harmful:
    ``events.commence_time`` is NOT NULL in the model and in production, so it
    can never exclude a row. It is kept below inside the scheduled arm, where
    the pre-#837 code had it, as belt-and-braces against the column being
    loosened — not because it fires. The Postgres contract asserts the schema
    that makes it inert, so that assumption fails loudly if it changes.)

    The ship does not need the live floor. Measured on production 2026-09-23
    03:4xZ over ALL events (a superset of the slate, so a zero here is a zero
    there):

        live ....... 58 rows,     0 older than 24 h
        scheduled .. 3,284 rows, 850 older than 24 h

    Every row the floor is for is a ``scheduled`` row, and the live arm's copy
    of the floor cuts nothing at all today. It is pure downside on exactly the
    row a reader is watching, so the live arm fails OPEN: no clock test, no
    NULL test, subscribed.

    The stuck-at-live hazard is therefore NOT fixed here, deliberately. An
    event wedged at ``status='live'`` for weeks is a state-machine defect in
    whatever should have advanced it, and it cannot be answered by dropping
    live rows out of the price stream — that trades a rare stale subscription
    for a routine dark hero. It needs a status-freshness signal (an advanced-at
    stamp, or the venue's own resolution) rather than a clock this module is
    already on record as not trusting. ``the_event_stuck_at_live`` stays in the
    Postgres contract as a live-preservation control, asserting it KEEPS its
    subscription, so nobody re-lands the above draft by accident.
    """
    # Imported in-function like every other SQLAlchemy use in this module: the
    # consumer is started by `run_kalshi_ws.py`, and module scope here stays
    # light on purpose.
    from sqlalchemy import text, or_, and_

    from app.models.models import Event
    from app.tasks.ws_slate import suspended_open_market_arm

    return or_(
        # Clock-free and fail-open, on purpose. Unchanged from before the floor
        # existed — the fix narrows the sibling arm and leaves this one alone.
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time.isnot(None),
            # int() by construction: the interval literal can never carry
            # anything but a number, whatever a future edit does to the
            # constant.
            Event.commence_time >= text(
                f"NOW() - INTERVAL '{int(SLATE_MAX_AGE_HOURS)} hours'"
            ),
            Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
        ),
        # #9484: an open market on a recently suspended event. Floored like the
        # scheduled arm, because nothing advances a suspended row out; this arm
        # also reads `futures_markets`, which every caller already joins.
        suspended_open_market_arm(),
    )


def _slate_market_filter():
    """A market our own rows already record the venue as having SETTLED is not
    subscribed — the market-level half of the slate, and the signal the event
    window says it needs.

    ``_slate_event_window`` deliberately leaves the live arm clock-free, and
    says in as many words that the stuck-at-live hazard "needs a
    status-freshness signal (an advanced-at stamp, or the venue's own
    resolution) rather than a clock this module is already on record as not
    trusting". ``futures_markets.status = 'resolved'`` IS the venue's own
    resolution: it is written by this module's ``handle_resolved`` off a
    ``market_resolved`` push, and by ``sync_polymarket_resolved_status`` off the
    venue's closed/terminal read. Nothing here infers a finish from a clock.

    WHAT IT COSTS TO LEAVE THEM IN, measured on production 2026-09-23 05:2xZ.
    Of the 709 Polymarket markets the event window then selected, **54 markets /
    108 outcomes on 12 events were already ``status='resolved'`` in our own
    database** — 7.6% of a subscription whose per-shard budget is BYTE-capped
    and was sitting at 40,594 of 40,960 bytes, i.e. effectively full. Those
    tokens cannot pay: a 120-second probe of the public CLOB socket (8 assets,
    one connection, ``initial_dump``) returned **nothing whatsoever** for the
    four tokens of two such markets — not even the opening ``book`` frame every
    open market answers with — while the same connection's control arm got its
    books at once and 726 ``price_change`` frames on one of them. Two matches in
    the same M25 Yinchuan tournament, one resolved and one open, split exactly
    that way, so this is not a tier or a thin-book story.

    WHAT A READER SAW. Those 12 events were still ``status='live'`` on the site
    with no score and no ``completed_at``, showing a Polymarket price last
    written when the venue settled the market — four of them frozen over an
    hour, one at 733 minutes. Dropping the settled MARKET does not touch the
    event or its open siblings, so this returns the budget without taking a
    single price off a game still being played.

    FAIL OPEN, WHICH IS WHY THE NULL ARM IS HERE AND NOT A PLAIN ``!=``. In SQL
    ``status != 'resolved'`` is NULL — not true — for a NULL status, so the
    plain form silently DROPS a market whose status was never written. That is
    the dark-hero direction this module refuses everywhere else, and the case is
    reachable on the schema that actually serves readers: the model's
    ``Mapped[str]`` reads as NOT NULL, but **production's column is
    ``is_nullable = YES`` with ``DEFAULT 'open'``** (``information_schema``,
    2026-09-23 05:3xZ), so a raw-SQL writer can leave it NULL there while a
    ``create_all`` test database refuses the same row. The contract test relaxes
    its column to match production rather than let the stricter schema retire
    the control. Values in production today: ``open`` (29,039) and ``resolved``
    (784,156). ``suspended`` — the third the model's own comment names — is
    KEPT: a suspended market can reopen, and only ``resolved`` is terminal.
    """
    from sqlalchemy import or_

    from app.models.models import FuturesMarket

    return or_(
        FuturesMarket.status.is_(None),
        FuturesMarket.status != "resolved",
    )


def _slate_metadata_keys() -> tuple[str, ...]:
    """The only ``market_metadata`` keys the slate's market loop reads (#10663)."""
    from app.tasks.polymarket_token_topup import OUTCOME_TOKEN_METADATA_KEY
    from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY

    return (
        "clob_token_ids",
        "clobTokenIds",
        OUTCOME_TOKEN_METADATA_KEY,
        CONTENT_UNDERSTANDING_KEY,
    )


def slate_market_stmt(market_ids: Iterable[int]):
    """The slate's market read: ``(id, external_id, <four keys>, event status)``.

    #10663 — the four keys the loop reads, never the whole metadata blob, the
    same way ``open_contract_markets_stmt`` reads its token keys. A key the row
    does not carry (or a blob that is not an object) reads as SQL NULL.
    """
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket

    meta = FuturesMarket.market_metadata
    return (
        select(
            FuturesMarket.id,
            FuturesMarket.external_id,
            *(meta[key] for key in _slate_metadata_keys()),
            Event.status,
        )
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(FuturesMarket.id.in_(list(market_ids)))
    )


def slate_market_rows(rows: Iterable[Any]) -> Iterator[tuple[Any, Any, dict, Any]]:
    """``slate_market_stmt`` rows as ``(id, external_id, metadata, status)``.

    ``metadata`` holds only the keys that are present, so the loop reads it as
    it read the full blob. A row with no token key is still skipped: an empty
    dict hits ``if not metadata``, where the full blob hit ``if not tokens``.
    """
    keys = _slate_metadata_keys()
    for mid, mext, *values, event_status in rows:
        metadata = {
            key: value
            for key, value in zip(keys, values, strict=True)
            if value is not None
        }
        yield mid, mext, metadata, event_status


def _format_by_shard(ws_stats: dict) -> str:
    """`0:14/500 1:26/500 …` — the per-shard shape behind the coverage ratio.

    The aggregate cannot carry this. `served=1837/3793` is the same 49% whether
    every shard is half-served (a quiet venue, nothing wrong) or four shards sit
    at 3% while four stream in full (a truncated subscription), and only the
    second is a defect. The first production read WAS the second shape, and the
    reader had to reconstruct the denominators from a separate capture to see
    it: the pairs were in `PolymarketWebSocket.stats` the whole time and reached
    no line until the ten-minute recycle, so a minute-resolution reader saw one
    number that could not be acted on.

    BOTH halves per shard, never a bare served count. Shard subscriptions are
    not all the same size — the last shard is a remainder, and the byte bound
    makes shards of different lengths at different id lengths — so `0:14` cannot
    be read as a share by anyone, including the next person to grep this line.

    Degrades to `-` rather than vanishing or raising. The shadow consumer shares
    this client and subscribes without shards, and an exception in the stats loop
    kills the socket's only heartbeat; a field that disappears when empty is also
    a field no grep can rely on.
    """
    served = ws_stats.get("served_by_shard") or {}
    subscribed = ws_stats.get("subscribed_by_shard") or {}
    if not served and not subscribed:
        return "-"

    def _order(key):
        # Shard keys are ints in-process but arrive as strings through any JSON
        # round-trip, and "10" sorts before "2" as text.
        try:
            return (0, int(key), "")
        except (TypeError, ValueError):
            return (1, 0, str(key))

    return " ".join(
        f"{key}:{served.get(key, 0)}/{subscribed.get(key, 0)}"
        for key in sorted(set(served) | set(subscribed), key=_order)
    )


def _log_stats_line(stats: dict, ws_stats: dict, blend: dict) -> None:
    """The once-a-minute socket line, including #837's coverage ratio.

    Module-level rather than inline in the consumer's `stats_loop` for one
    reason: the defect this exists to prevent is a number that is COMPUTED and
    never EMITTED, and a closure three `await`s deep inside a consumer that
    needs a database, a slate and a live socket cannot be asserted on. Lifted
    here, the emitted line is checkable directly, so "the coverage fields
    silently stopped being logged" is a red test rather than something a person
    has to notice in a log tail months later.

    Every field is read with `.get(..., 0)` because the shadow consumer shares
    this client and subscribes without shards: absent coverage keys must print
    a zero, never raise inside a stats loop whose exception would kill the
    socket's only heartbeat.

    `wire=` rides beside `served=` for the reason stated at the top of this
    docstring, applied to the field that was just added: `served` is now the
    intersection against the subscription, so it can no longer exceed its own
    denominator — and an excess that can no longer show up in the ratio would
    stop existing for every reader if the raw total were computed and never
    printed. `wire - served` is the count of ids the venue sent us unasked,
    which was previously being read AS coverage. It is also the only
    served-shaped number the shadow consumer has, since that one subscribes to
    everything and so has no subscription to intersect against.
    """
    logger.info(
        "Polymarket WS: %d prices, %d trades, %d resolutions, %d errors, "
        "%d msgs | coverage shards=%d/%d served=%d/%d wire=%d by_shard=%s "
        "| blend stamped=%d no_reading=%d throttled=%d errors=%d lock_skipped=%d "
        "unobserved=%d stale=%d | trades refused below_min=%d outside_wide_book=%d "
        "| held withdrawn=%d lock_probes_refused=%d fenced=%d stamp_wait_s=%.1f "
        "lock_timeouts=%d",
        stats["price_updates"], stats["trade_updates"],
        stats["resolutions"], stats["errors"],
        ws_stats.get("messages", 0),
        ws_stats.get("shards_connected", 0), ws_stats.get("shards", 0),
        ws_stats.get("assets_served", 0),
        ws_stats.get("assets_subscribed", 0),
        ws_stats.get("assets_on_wire", 0),
        _format_by_shard(ws_stats),
        blend["stamped"], blend["no_reading"],
        blend["throttled"], blend["errors"],
        # #837 tail: stamps re-queued rather than left waiting on a row lock.
        blend.get("lock_skipped", 0),
        # #5661: unchanged prices not re-dated because no writer re-read them.
        blend.get("unobserved_skipped", 0),
        # #8910: readings refused as older than the stored observation.
        blend.get("stale_readings_refused", 0),
        # #9733 / #9913: trades that were not a price. Counted in the consumer
        # and, until this line, never emitted.
        stats.get("trades_below_min_order", 0),
        stats.get("trades_outside_wide_book", 0),
        # #9934: held prices a wide book priced out, withdrawn.
        stats.get("held_prices_withdrawn", 0),
        # #10090: still-held NOWAIT probes, kept out of `errors`.
        stats.get("price_lock_probes_refused", 0),
        # #10090: prices/books left buffered behind their own event's running
        # stamp, and the seconds flushes still spent joining a running refresh.
        stats.get("stamp_fenced", 0),
        stats.get("stamp_wait_s", 0.0),
        # #10090 (lane1 R3): repeat price-statement lock timeouts on rows
        # already known-held. Kept out of `errors`, so a sustained table lock
        # shows here rather than as one error and then silence.
        stats.get("price_lock_timeouts", 0),
    )


def _log_open_contract_line(stats: dict, open_stats: dict) -> None:
    """#9484 — the open-contract client's minute line, beside the game line.

    Its own line so the game line's format (and every grep of it) is untouched.
    `written` is rows that took a price; `deferred` is open rows a periodic
    flush left buffered for the next one — non-zero is a backlog, not a loss.
    `bridged` is #10091's legs/events whose flushed price re-stamps the event
    blend (0/0 with no `bridge_error` = no such contract this run).
    `bridged_writes` (#10090) is the bridged writer's cohorts since start, then
    the seconds they waited for the shared side connection and spent in their
    own write: sum since start / the minute's longest, each. `live_writes` is
    the cohorts of live events among them, then their wait from hand-off to
    the side connection's turn (the bridged queue included), the same way.
    """
    logger.info(
        "Polymarket WS open contracts: assets=%d shards=%d/%d served=%d/%d "
        "msgs=%d snapshot_quotes=%d written=%d deferred=%d "
        "bridged=%d/%d bridged_writes=%d side_wait=%.1f/%.2fs "
        "write=%.1f/%.2fs live_writes=%d live_wait=%.1f/%.2fs%s",
        stats.get("open_contract_assets", 0),
        open_stats.get("shards_connected", 0), open_stats.get("shards", 0),
        open_stats.get("assets_served", 0),
        open_stats.get("assets_subscribed", 0),
        open_stats.get("messages", 0),
        open_stats.get("book_snapshot_quotes", 0),
        stats.get("open_contract_prices_written", 0),
        stats.get("open_contract_flush_deferred", 0),
        stats.get("open_contract_bridged_outcomes", 0),
        stats.get("open_contract_bridged_events", 0),
        int(stats.get("bridged_cohorts", 0)),
        stats.get("bridged_side_wait_s", 0.0),
        stats.get("bridged_side_wait_max_s", 0.0),
        stats.get("bridged_write_s", 0.0),
        stats.get("bridged_write_max_s", 0.0),
        int(stats.get("bridged_live_cohorts", 0)),
        stats.get("bridged_live_wait_s", 0.0),
        stats.get("bridged_live_wait_max_s", 0.0),
        " bridge_error" if stats.get("open_contract_bridge_error") else "",
    )


def _log_unserved_sample(ws) -> None:
    """Name a few of the ids the venue never sent, once per recycle.

    #837's ratio said 49% served and could not say why: `assets_served` counts
    assets that sent at least one message, so a book nobody traded and a
    subscription the venue truncated are the same number. The ids the
    difference is made of already exist in process memory at this point and
    were being discarded. Named, they are answerable — the books can be put to
    Polymarket directly, and the reply turns "49% served" into a share that is
    actually truncated.

    Module-level for the same reason `_log_stats_line` is: the failure this
    guards against is a line that quietly stops being emitted, and a closure
    inside a consumer that needs a database, a slate and a live socket cannot
    be asserted on.

    Defensive around the client because this runs in the recycle path, after
    the `finally` that drained prices: a consumer that raised here would turn
    a planned resubscribe into a crash, trading a diagnostic for the socket.
    """
    # Imported here, not at module scope, for the same reason the client is:
    # nothing on this module's import path should pull the websocket service.
    from app.services.polymarket_ws import UNSERVED_SAMPLE_PER_SHARD

    try:
        sample = ws.unserved_sample()
    except Exception:
        logger.exception("Polymarket WS unserved sample failed (#837)")
        return
    if not sample:
        return
    logger.info(
        "Polymarket WS unserved sample (#837): %d shard(s) with unserved ids, "
        "up to %d spread per shard — %s",
        len(sample),
        UNSERVED_SAMPLE_PER_SHARD,
        sample,
    )


@owns_consumer_sessions("polymarket")
async def _run_polymarket_ws_consumer(*, sessions, stop=None):
    """Stream until cancellation; an explicit stop also runs the final drain."""
    # `text`/`or_`/`and_` left with `_slate_event_window`, which now owns the
    # only expression in this consumer that needed them.
    from sqlalchemy import select

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.tasks.live_blend_refresh import (
        DEFAULT_MIN_REFRESH_INTERVAL_S, HeldRowQuotes, LiveBlendRefresher, TailReceipts,
        OwedChartCustody, adopt_handed_off,
        LOOP_REAP_TIMEOUT_S, event_ids_for_outcomes, hand_off_pending,
        reap_stopped_loops, run_flush_cadence,
    )
    from app.tasks.polymarket_token_topup import (
        topup_clob_tokens, topup_outcome_clob_tokens, condition_id_of,
    )
    from app.tasks.ws_admission import (  # #9418
        unadmitted_live_events,
        watch_for_unadmitted_live_events,
    )
    from app.tasks.polymarket_open_contracts import (  # #9484
        FLUSH_CHUNK_ROWS, OPEN_CONTRACT_MAX_CONCURRENT_HANDSHAKES,
        OpenContractLegs,
        book_snapshot_prices_enabled, open_contract_receiver_process_enabled,
        OPEN_CONTRACT_MAX_QUEUE, OPEN_FLUSH_CHUNKS_PER_FLUSH,
        open_contract_asset_map_cooperatively,
        open_contract_event_candidates_cooperatively,
        open_contract_markets_stmt, open_contract_outcome_stmts,
        open_contract_prices_enabled, plan_flush_chunks, tokens_by_contract,
    )
    from app.tasks.ws_open_contracts import (  # #10091: the Kalshi arm's twin
        open_contract_bridge_event_stmt, open_contract_event_bridge,
    )
    from app.tasks.ws_liveness import report as _report_liveness
    from app.utils.heap_trim import release_free_heap  # #11218
    from app.utils.futures_rank import rerank_market_fields_stmt  # #6598
    # #2471: one engine for this run, a fresh session per operation; the
    # decorator disposes it after the final drain. Same call shape as the
    # task factory, so every site below is unchanged.
    get_task_session = sessions.session

    # #10662: opt in only this consumer. Removing the override restores both
    # the legacy shared timer and the existing blend floor. A faster healthy
    # timer must not also shorten the preexisting failed-write retry period.
    def cadence_override(name):
        value = os.getenv(name)
        if value is None:
            return None
        try:
            seconds = float(value)
        except ValueError as invalid_cadence:
            raise ValueError(
                f"{name} must be a positive finite number"
            ) from invalid_cadence
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError(f"{name} must be a positive finite number")
        return seconds

    flush_period = PRICE_FLUSH_SECONDS
    blend_floor = DEFAULT_MIN_REFRESH_INTERVAL_S
    override = cadence_override("PM_WS_PRICE_FLUSH_SECONDS")
    if override is not None:
        flush_period = override
        blend_floor = flush_period
    # #10090: the game flush and its blend floor alone. Linked props stay on
    # `flush_period` and failed writes keep the legacy retry, so a faster
    # game cadence adds no prop work. Unset, the game follows `flush_period`.
    game_period = flush_period
    game_override = cadence_override("PM_WS_GAME_FLUSH_SECONDS")
    if game_override is not None:
        game_period = game_override
        blend_floor = game_period

    # #9484 — every other unsettled Polymarket contract, for PRICES only, on a
    # second client (`app.tasks.polymarket_open_contracts`). Never added to the
    # settlement maps or to the maps the #9418 admission watcher reads as "this
    # event is subscribed". A failed read costs the arm, never the game slate.
    #
    # Returns ``(admission, failed, bridge, bridge_failed)``. The #10091 EVENT
    # BRIDGE is outcome → event for the admitted game-winner legs whose event is
    # still to be decided (`open_contract_event_candidates`), so the flush
    # re-stamps their event blend like a slate leg's. Its own read fails on its
    # own: a failed bridge costs the blend re-stamp, never the prices.
    async def read_open_contracts(
        taken_assets, excluded_market_ids, taken_tokens_by_contract=None
    ):
        if not open_contract_prices_enabled():
            return None, False, {}, False
        try:
            async with get_task_session() as session:
                market_rows = (
                    await session.execute(open_contract_markets_stmt())
                ).all()
                # #10663: each leg chunk is digested into the pairing's own
                # structures as it arrives (`OpenContractLegs.add`), so the
                # read never holds ~71,000 result rows beside them for the
                # whole mapping. Row order is unchanged: chunks in catalog
                # order, legs in id order within each.
                legs = OpenContractLegs()
                # These markets already belong to the game arm. The mapper
                # skips them before pairing; keep their market rows for counts,
                # but do not read legs that cannot enter the open admission.
                excluded = set(excluded_market_ids)
                for stmt in open_contract_outcome_stmts(
                    r[0] for r in market_rows if r[0] not in excluded
                ):
                    await legs.add_rows_cooperatively(
                        (await session.execute(stmt)).all()
                    )
            # #10090: this mapping shares the loop with every PM socket.
            admission = await open_contract_asset_map_cooperatively(
                market_rows, legs, taken_assets, excluded_market_ids,
                taken_tokens_by_contract,
            )
            # The pairing has read every leg; nothing below needs them.
            legs = None
        except Exception:
            logger.exception(
                "Polymarket WS: open-contract admission read failed; "
                "streaming the linked slate only this run"
            )
            return None, True, {}, False
        candidates = await open_contract_event_candidates_cooperatively(
            market_rows, admission
        )
        if not candidates:
            return admission, False, {}, False
        try:
            async with get_task_session() as session:
                admitted = (
                    await session.execute(
                        open_contract_bridge_event_stmt(candidates.values())
                    )
                ).scalars().all()
        except Exception:
            logger.exception(
                "Polymarket WS: open-contract event-bridge read failed; "
                "streaming their prices without the event blend this run"
            )
            return admission, False, {}, True
        return (
            admission, False, open_contract_event_bridge(candidates, admitted),
            False,
        )

    # Q504-b: see the Kalshi arm — reported before the slate work, so a stall in
    # the token top-up or the slate query is visible as an AGE rather than as a
    # silence indistinguishable from health.
    _report_liveness("polymarket", "loading_slate")

    # #9418: the admission floor is measured from here, the previous recycle.
    run_started_at = time.monotonic()
    # A reconnect/admission book uses the existing game quote guards, even
    # when the venue sends no later move. The shared snapshot switch is the undo.
    ws = PolymarketWebSocket(
        price_book_snapshots=book_snapshot_prices_enabled(),
    )

    async def load_game_slate(*, stored_live_only=False):
        # Load linked Polymarket market asset IDs
        # #10663: one row per linked market. The outcome join still requires a
        # market to have an outcome, but no outcome field is read here: tokens
        # and outcomes come from the reads below. An event id belongs to its
        # market row, so DISTINCT drops only the per-outcome repeats.
        async with get_task_session() as session:
            result = await session.execute(
                select(
                    FuturesOutcome.market_id,
                    FuturesMarket.event_id.label("linked_event_id"),
                )
                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.event_id.isnot(None),
                    _slate_event_window(),
                    _slate_market_filter(),
                    *([Event.status.in_(("live", "suspended"))] if stored_live_only else []),
                )
                .distinct()
            )
            rows = result.all()

        market_ids = set()
        # Q460: linked event per market, so a flushed price can re-stamp the blend.
        event_id_by_market: dict[int, int] = {}
        for market_id, linked_event_id in rows:
            market_ids.add(market_id)
            if linked_event_id is not None:
                event_id_by_market[market_id] = linked_event_id

        # Load clob_token_ids from market_metadata
        asset_ids: list[str] = []
        asset_to_outcome: dict[str, int] = {}  # asset_id → outcome_id
        asset_to_market: dict[str, int] = {}   # asset_id → market_id
        condition_to_market: dict[str, int] = {}  # condition_id → market_id

        tokens_by_market: dict[int, list[str]] = {}
        non_blend_market_ids: set[int] = set()
        live_win_topup_ids: set[int] = set()
        stored_outcome_tokens: dict[int, tuple[int, str]] = {}

        async with get_task_session() as session:
            market_result = await session.execute(slate_market_stmt(market_ids))
            ext_by_market: dict[int, str] = {}
            for mid, mext, metadata, event_status in slate_market_rows(
                market_result.all()
            ):
                # Same authoritative refutation as shared WIN admission, using the
                # catalog metadata this token read already owns. Missing labels
                # remain conservative; titles and outcome names are never guessed.
                if pm_non_speaking_metadata(metadata):
                    non_blend_market_ids.add(mid)
                elif event_status == "live":
                    # Same conservative WIN eligibility as the blend owner map.
                    # Props remain in the fleet but cannot take these ask seats.
                    live_win_topup_ids.add(mid)
                if stored_live_only:
                    # Same persisted per-outcome attribution read by the outcome
                    # top-up. Parent moneylines have no market-level token array.
                    stored = (metadata or {}).get("clob_yes_token_by_outcome")
                    if isinstance(stored, dict):
                        for raw_oid, token in stored.items():
                            if token:
                                try:
                                    stored_outcome_tokens[int(raw_oid)] = (mid, str(token))
                                except (TypeError, ValueError):
                                    pass
                if mext:
                    condition_to_market[mext] = mid
                    ext_by_market[mid] = mext
                if not metadata:
                    continue
                tokens = metadata.get("clob_token_ids") or metadata.get("clobTokenIds")
                if not tokens:
                    continue
                if isinstance(tokens, str):
                    import json
                    try:
                        tokens = json.loads(tokens)
                    except Exception:
                        continue
                for token in tokens:
                    asset_ids.append(str(token))
                    asset_to_market[str(token)] = mid
                tokens_by_market[mid] = [str(t) for t in tokens]

            # Q490 — ask for the slate's tokens instead of waiting for a rotation.
            # The ingest stamp (Q460) is correct and covers the catalogue, but Gamma
            # caps `/events` at offset 2000, so the poll addresses ~2,000 of ~39,000
            # open markets per run on a rotating cursor. Measured 2h after that
            # deploy: 701 markets carried tokens and 0 of the 77 on THIS slate did.
            # `/markets?condition_ids=` does not paginate, so the fast lane can name
            # exactly what it needs. Bounded by the slate size, which is ~77.
            topup_missing = [
                (mid, ext_by_market.get(mid))
                for mid in market_ids
                if mid not in tokens_by_market
            ]
            if topup_missing and not stored_live_only:
                try:
                    topped = await topup_clob_tokens(
                        session,
                        topup_missing,
                        priority_market_ids=live_win_topup_ids,
                    )
                except Exception:
                    # A Gamma outage must not take the socket down with it: the
                    # markets that already have tokens keep streaming, and the next
                    # recycle retries. Loud, because a silently-empty top-up is the
                    # failure this whole queue exists to end.
                    logger.exception(
                        "Polymarket WS: token top-up failed for %d markets; "
                        "continuing with the %d already stamped",
                        len(topup_missing), len(tokens_by_market),
                    )
                    topped = {}
                for mid, tokens in topped.items():
                    tokens_by_market[mid] = tokens
                    for token in tokens:
                        asset_ids.append(token)
                        asset_to_market[token] = mid

            outcome_result = await session.execute(
                select(FuturesOutcome.id, FuturesOutcome.market_id, FuturesOutcome.external_id)
                .where(FuturesOutcome.market_id.in_(list(market_ids)))
                .order_by(FuturesOutcome.id)
            )
            outcomes_by_market: dict[int, list[tuple[int, str]]] = {}
            for oid, mid, ext in outcome_result.all():
                outcomes_by_market.setdefault(mid, []).append((oid, ext or ""))

            # ── THE MONEYLINE LEG ────────────────────────────────────────────────
            # Everything above addresses a market by its OWN condition id, which a
            # parent/field row does not have — its `external_id` is a bare Gamma
            # event id ("917153"), so `condition_id_of` returns None and the
            # market-level top-up skips it by design. That row is the three-way
            # "who wins" market: the ONLY market on the event that
            # `compute_source_home_probability` can read, and therefore the only one
            # whose price is the number the hero renders.
            #
            # Measured on production 2026-09-01 before this block existed: the
            # socket was streaming continuously (7 distinct sub-minute flushes in
            # one minute) into Over/Under and Both-Teams-To-Score props, while
            # across EVERY live event the `polymarket` and `kalshi` blend stamps sat
            # at p50 age 122s — the 120s poll's sawtooth — with 0 of 9 fresher than
            # two minutes, against `betting` at 23s. The fast lane was real and it
            # was pointed at the markets nobody reads.
            #
            # A field market's OUTCOMES each carry a real condition id, so the
            # tokens were reachable one level down the whole time. Only markets
            # still missing tokens after the market-level pass are asked about, so
            # an ordinary binary sub-market costs nothing here.
            outcome_topup_targets: list[tuple[int, int, str]] = [
                (mid, oid, ext)
                for mid in market_ids
                if mid not in tokens_by_market
                for oid, ext in outcomes_by_market.get(mid, [])
            ]
            # The normal top-up reads stored metadata only for markets with
            # at least one addressable outcome. That read returns all persisted
            # siblings, including one whose own external ID is unparseable.
            stored_markets = {
                mid for mid, _oid, ext in outcome_topup_targets
                if condition_id_of(ext) is not None
            }
            outcome_yes_token: dict[int, str] = {
                oid: token
                for oid, (mid, token) in stored_outcome_tokens.items()
                if stored_live_only and mid in stored_markets
            }
            if outcome_topup_targets and not stored_live_only:
                try:
                    outcome_yes_token = {
                        oid: token
                        for oid, (_mid, token) in (
                            await topup_outcome_clob_tokens(
                                session, outcome_topup_targets
                            )
                        ).items()
                    }
                except Exception:
                    # Same posture as the market-level top-up: a Gamma outage must
                    # not take the socket down. The props keep streaming and the
                    # next recycle retries the moneyline.
                    logger.exception(
                        "Polymarket WS: outcome token top-up failed for %d outcomes; "
                        "continuing without the moneyline legs",
                        len(outcome_topup_targets),
                    )
                    outcome_yes_token = {}

            market_by_outcome: dict[int, int] = {
                oid: mid
                for mid, pairs in outcomes_by_market.items()
                for oid, _ext in pairs
            }
            for oid, token in outcome_yes_token.items():
                mid = market_by_outcome.get(oid)
                if mid is None:
                    continue
                asset_ids.append(token)
                asset_to_market[token] = mid
                # Attributed directly, never positionally: this token IS the book
                # for "will <this outcome> win", so the pairing is carried by the
                # condition id rather than reconstructed from ordering.
                asset_to_outcome[token] = oid

        # Q489 — WHICH outcome an asset id belongs to. Both CLOB tokens of a binary
        # (`clobTokenIds == [yesToken, noToken]`) map to the same FuturesMarket, and
        # the price handlers used to resolve every tick to `outcomes[0]` — the
        # Over/Yes leg — because this map was declared and never filled. A No-token
        # `best_bid_ask` therefore wrote P(No) into the Yes outcome, and since both
        # legs stream continuously the rendered number would oscillate between p and
        # 1-p on every tick. That is strictly worse than a stale price: a stale card
        # is wrong once, an inverted card is wrong at random.
        #
        # The pairing is positional and both sides are already ordered the same way:
        # Gamma serves `[yes, no]`, and the ingest inserts the Over/Yes outcome
        # before the Under/No one (`polymarket.py`, the sub-market loop), so ordering
        # by `FuturesOutcome.id` reproduces the token order. `zip` is deliberate — a
        # market whose outcome count disagrees with its token count maps only the
        # pairs it can prove and leaves the rest unmapped, so a shape we did not
        # anticipate drops ticks instead of writing them to the wrong leg.
        #
        # #8403: "ordering by id reproduces the token order" is an ASSUMPTION about
        # insertion order, and on a named two-sided game it fails. The legs are
        # `{condition}` (Gamma `outcomes[0]`, token 0) and `{condition}_side1`
        # (`outcomes[1]`, token 1), and on 21 of 67 live-or-upcoming markets
        # measured 2026-09-24 the `_side1` leg held the LOWER id — so token 0 was
        # zipped onto the second team's row and each team's price streamed onto
        # the other's. The leg's own suffix says which token it is; ordering by it
        # is `legs_in_token_order`.
        for mid, mtokens in tokens_by_market.items():
            for token, (oid, _ext) in zip(
                mtokens, legs_in_token_order(outcomes_by_market.get(mid, []))
            ):
                asset_to_outcome[token] = oid

        unmapped_assets = [a for a in asset_ids if a not in asset_to_outcome]

        return {
            "asset_ids": asset_ids,
            "asset_to_outcome": asset_to_outcome,
            "asset_to_market": asset_to_market,
            "condition_to_market": condition_to_market,
            "market_ids": market_ids,
            "event_id_by_market": event_id_by_market,
            "outcomes_by_market": outcomes_by_market,
            "market_by_outcome": market_by_outcome,
            "non_blend_market_ids": non_blend_market_ids,
            "outcome_yes_token": outcome_yes_token,
            "unmapped_assets": unmapped_assets,
        }

    game_slate = await load_game_slate(stored_live_only=True)
    complete_startup_slate = bool(game_slate["asset_to_outcome"])
    if not complete_startup_slate:
        # Preserve the original full-slate/open-only fallback when nothing
        # attributable can be subscribed from the stored live subset.
        game_slate = await load_game_slate()
    asset_ids = game_slate["asset_ids"].copy()
    asset_to_outcome = game_slate["asset_to_outcome"].copy()
    asset_to_market = game_slate["asset_to_market"].copy()
    condition_to_market = game_slate["condition_to_market"].copy()
    market_ids = game_slate["market_ids"].copy()
    event_id_by_market = game_slate["event_id_by_market"].copy()
    outcomes_by_market = game_slate["outcomes_by_market"].copy()
    market_by_outcome = game_slate["market_by_outcome"].copy()
    non_blend_market_ids = game_slate["non_blend_market_ids"].copy()
    outcome_yes_token = game_slate["outcome_yes_token"].copy()
    unmapped_assets = game_slate["unmapped_assets"].copy()

    preread = None
    if not asset_ids:
        preread = await read_open_contracts(set(), market_ids)
        if preread[0] is None or not preread[0].asset_to_outcome:
            logger.info("Polymarket WS: no game or open-contract asset IDs")
            _report_liveness("polymarket", "no_asset_ids", legs=0)
            return {"status": "no_asset_ids" if market_ids else "no_markets"}

    logger.info(
        "Polymarket WS: %d asset IDs (%d markets), %d mapped to an outcome, "
        "%d unmapped (ticks dropped rather than mis-attributed), "
        "%d moneyline legs subscribed via outcome condition ids",
        len(asset_ids), len(market_ids),
        len(asset_to_outcome), len(unmapped_assets),
        len(outcome_yes_token),
    )

    stats = {
        "assets_subscribed": len(asset_ids),
        # Q489: the number that says whether a tick can land on the right leg.
        # `assets_subscribed` counts what we listen to; this counts what we can
        # actually attribute, and the gap between them is the silent-loss bound.
        "assets_mapped": len(asset_to_outcome),
        "assets_unmapped": len(unmapped_assets),
        # The count this queue exists to move off zero. Every other number here
        # can look healthy while the hero is stale, because props tick loudly
        # and the moneyline is the only leg the rendered blend reads. A run that
        # subscribes 0 moneyline legs on a non-empty slate is the bug, restated.
        "moneyline_legs_subscribed": len(outcome_yes_token),
        "price_updates": 0,
        "trade_updates": 0,
        # #9733: trades refused because they were smaller than the smallest
        # order the venue accepts (`trade_sets_a_price`).
        "trades_below_min_order": 0,
        # #9913: trades refused because they printed beyond the edge of a
        # book too wide to price (`trade_prints_outside_wide_book`).
        "trades_outside_wide_book": 0,
        # #9934: held prices withdrawn because a wide book priced them out
        # (`withdraw_book_refuted_prices`).
        "held_prices_withdrawn": 0,
        "resolutions": 0,
        # #9418: what each resolution was allowed to write
        # (`ws_resolution_verdict`). `unconfirmed` is graded by nobody here.
        "resolutions_winner": 0,
        "resolutions_void": 0,
        "resolutions_unconfirmed": 0,
        # #9418 after-check: decided by Gamma (CLOB not yet flipped), and
        # decided only on a re-ask after the first answer was `unconfirmed`.
        "resolutions_via_gamma": 0,
        "resolutions_confirmed_late": 0,
        "errors": 0,
        # Q491: prices a failed flush put BACK on the buffer instead of dropping.
        # `errors` alone cannot distinguish a retried batch from a lost one.
        "requeued": 0,
        # Q491 repair: the final drain retries instead of requeueing, because
        # nothing runs after it. These two separate "we had to try again" from
        # "we gave up and a price is gone".
        "final_flush_retries": 0,
        "final_flush_dropped": 0,
        # #6598 / CERT-3182: rows whose `rank` a flush corrected. Twin of the
        # Kalshi socket's counter and there for the same reason — this module
        # moves `current_probability` and had never written the column derived
        # from it, so a live crossing left the board ordered by the last poll.
        # Counted unconditionally: the statement is a no-op on a field that did
        # not cross, so 0 is healthy and absence is the failure.
        "ranks_rederived": 0,
        # #9484: the open-contract arm. `open_contract_prices_written` counts
        # rows that TOOK a price, so "the arm is subscribed" and "the arm is
        # moving stored prices" are two numbers, not one; `_flush_deferred`
        # counts open rows a flush left buffered for the next one.
        "open_contract_assets": 0,
        "open_contract_admission_error": False,
        "open_contract_prices_written": 0,
        "open_contract_flush_deferred": 0,
        # #10090, twin of the Kalshi socket's: buffered prices a periodic flush
        # left for the next one because their event's stamp was still queued
        # or running in the run's refresh. Deferred, never dropped.
        "stamp_fenced": 0,
        # #10091 event bridge, twin of the Kalshi socket's: admitted game-winner
        # legs (and their distinct events) whose flushed price re-stamps the
        # event blend. 0 with no error is "no such contract this run".
        "open_contract_bridged_outcomes": 0,
        "open_contract_bridged_events": 0,
        "open_contract_bridge_error": False,
        # #9484, twin of the Kalshi socket's: rows a flush wrote whose price
        # was already what it stored — written (liveness), but no market
        # invalidation sent. #10664: counts observations returned by completed
        # price statements. A failed atomic statement adds none; a later
        # rerank/commit failure may still leave these observations counted.
        "quotes_unchanged": 0,
        # #10090: NOWAIT probes of a known-held cohort that its holder still
        # refused. Not `errors`: one per flush while the hold lasts.
        "price_lock_probes_refused": 0,
        # #10090: a known-held cohort's price statement timed out again (a
        # table lock, or an unrecognised refusal). Not `errors`, same reason.
        "price_lock_timeouts": 0,
    }

    # Buffered price updates
    price_buffer: dict[int, float] = {}
    buffer_lock = asyncio.Lock()
    catalog_boundary = _PMCatalogFlushBoundary(game_period=game_period)
    lock_retry_until: dict[int, float] = {}
    lock_retry_events: set[int] = set()
    successful_price_write_at: dict[int, float] = {}
    withdrawal_retry_until: dict[int, float] = {}
    # Q460: outcome → linked event, for the blend re-stamp after each flush.
    #
    # Built from `market_by_outcome` (every outcome of every slate market) and
    # not, as it first was, from `condition_to_ids` — which is keyed by outcome
    # `external_id` and so silently omits any outcome whose external_id is NULL
    # or empty. An omitted outcome still gets its price written by the flush;
    # it just cannot name its event, so `event_ids_for_outcomes` drops it and
    # the blend is never re-stamped. That is the Q460 join failing open on
    # exactly the rows least likely to be noticed.
    event_id_by_outcome: dict[int, int] = {
        outcome_id: event_id_by_market[market_id]
        for outcome_id, market_id in market_by_outcome.items()
        if market_id in event_id_by_market
    }
    non_blend_outcome_ids = {
        oid for oid, mid in market_by_outcome.items()
        if mid in non_blend_market_ids
    }
    blend_refresher = LiveBlendRefresher(
        "polymarket", min_refresh_interval_s=blend_floor,
        session_factory=get_task_session,  # #2471
        observation_read_factory=sessions.observation_read,
        chart_custody=OwedChartCustody(),  # #11181: no owed chart point is lost
    )
    # #11138: quotes whose price-row write a lock holds; the stamp reads them
    # in place of the older stored row. Keyed like `price_buffer`, released
    # when the write lands. Reached through the refresher: no new name.
    blend_refresher.held_quotes = HeldRowQuotes()
    await blend_refresher.held_quotes.sample_database_clock(get_task_session)

    # #10090: withdrawals a previous run committed whose source removal it
    # never settled. A failed read is retried by the first withdrawal flush.
    blend_refresher.withdrawal_debt = PMWithdrawalDebt()
    await blend_refresher.withdrawal_debt.load(get_task_session)
    # #10090: when this arm is the named preview source, claim its display
    # epoch before any frame (`LiveBlendRefresher.claim_preview_display`).
    if getattr(blend_refresher, 'preview', False):
        await blend_refresher.claim_preview_display()
    # #837 receipt — every accepted input is stamped (seq, receive instant) as
    # it is buffered, so a held price can be followed from the socket to the
    # stamp that carried it. `input_marks` is keyed like `price_buffer` (one
    # entry per subscribed outcome) and holds the mark of the buffered value.
    tail_receipts = TailReceipts("polymarket")
    blend_refresher.receipts = tail_receipts
    # #10090 decision J: `confirmed_at` for this venue's events. A buffered
    # withdrawal whose book prices a published leg out is a pending change
    # (the rule `flush_withdrawals` applies to the stored price).
    from app.utils.confirmed_at import ConfirmedAt
    from app.utils.kalshi_empty_book import book_refutes_price as _refutes

    def _withdrawal_refutes(outcome_id, price):
        book = withdraw_buffer.get(outcome_id)
        return book is not None and _refutes(book[0], book[1], price)

    tail_receipts.confirmed = ConfirmedAt(
        "polymarket", client=getattr(blend_refresher, "_client", None),
        refutes=_withdrawal_refutes,
    )
    # #10090 stage trace: OFF unless 1-4 events (a fold's members), their
    # explicit outcomes and an absolute expiry <=600 s away are configured
    # (`app/utils/pm_stage_trace.py`).
    # Evidence only; it never changes a price, a schedule or a retry.
    tail_receipts.exact_trace = None
    with contextlib.suppress(Exception):
        from app.utils.pm_stage_trace import PMStageTrace

        tail_receipts.exact_trace = PMStageTrace.from_env(
            os.environ, run=tail_receipts.run, event_of=event_id_by_outcome,
        )
    # #10090 amendment P: an armed trace bridges this pid's clock to the DB's.
    with contextlib.suppress(Exception):
        from app.utils.clock_bridge import attach

        attach(tail_receipts.exact_trace, "polymarket")
    # #9462 review: stamps the previous run still owed when it recycled. Its
    # prices are already stored; the first flush below stamps them.
    stats["blend_pending_adopted"] = adopt_handed_off(blend_refresher)
    stats["history_pending_adopted"] = len(getattr(blend_refresher, "_history", ()))
    input_marks: dict = {}
    # DNPL canary speaking outcomes only. Same-price successors retain their
    # token; a move/withdrawal/routing change ends continuity, including A-B-A.
    observation_continuity: dict[int, tuple[object, float]] = {}

    # #9484: filled IN PLACE by `admit_open_contracts`, which the handlers and
    # the flush read through these same objects. Separate from the game maps so
    # nothing the #9418 watcher or the settlement handler reads can see them.
    open_asset_to_outcome: dict[str, int] = {}
    open_asset_to_market: dict[str, int] = {}
    # #9736: token → [(outcome_id, market_id)] of the other markets' legs that
    # name a token another leg owns. Each tick lands on the owner AND these.
    open_asset_mirrors: dict[str, list[tuple[int, int]]] = {}
    # #9733 follow-on: leg → the other leg of its binary (`complement_pairs`).
    open_complement_of: dict[int, int] = {}
    open_outcome_ids: set[int] = set()
    open_sockets: list = []
    open_run_task = None
    routing_generation = 0
    # #9913: token → (latest, previous) distinct top of book, wide or not, so
    # a trade can be read against the book it hit. One entry per subscribed
    # token; rebuilt from the subscribe snapshot on every recycle.
    books_by_asset: dict[str, tuple] = {}
    # #9934: leg → (bid, ask) of the latest wide book that speaks for it. The
    # flush asks whether the held price survives it; a tight book for the leg
    # clears the entry, since its midpoint is about to replace the price.
    withdraw_buffer: dict[int, tuple] = {}

    async def write_chunk(
        chunk: dict[int, float], *, final=False, start_market_publish=None,
    ) -> _PMPriceWriteResult | bool | None:
        """One flush transaction: write, re-rank, commit, publish, un-buffer.

        #9484: the flush used to write its whole batch in ONE transaction, so a
        standalone flood would have held every linked quote behind it and one
        failure would have retried all of it. Each chunk now commits and
        publishes on its own; a failed chunk keeps only its own rows buffered.
        """
        # Q491 repair 2 (CERT-659 BLOCK) — THE BUFFER IS DELIBERATELY *NOT*
        # CLEARED HERE. Twin of the Kalshi socket: draining first and putting
        # the batch back on failure only covers the failures you thought to
        # catch, and `except Exception` never sees `CancelledError` (a
        # BaseException), so a recycle cancelling `flush_loop` between the drain
        # and the write lost the batch with `errors=0, requeued=0` — invisible.
        # Entries now leave only after the write lands, so nothing needs to be
        # "put back", because it was never taken away.
        from app.tasks.live_blend_refresh import _mono
        from app.tasks.polymarket_ws import (
            _PMPriceWriteResult, PM_QUOTE_LIVENESS_SECONDS,
            DNPL_PRICE_STATEMENT_TIMEOUT_MS, ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL,
            is_price_statement_timeout,
        )
        from app.utils.repair_lock_budget import SET_STATEMENT_TIMEOUT_SQL

        # #10090 stage trace (OFF by default): times only the chunk the game
        # flush registered for its selected outcomes; never raises. Reached
        # through the refresher this writer already publishes with (its
        # `receipts` IS `tail_receipts`), so the writer gains no new name.
        stage_trace = getattr(
            getattr(blend_refresher, "receipts", None), "exact_trace", None
        )
        # None means a lock-held whole chunk, not a global cadence failure.
        # Newer ticks cannot bypass a non-price failure's existing cooldown.
        if not final and any(lock_retry_until.get(oid, 0) > _mono() for oid in chunk):
            if stage_trace is not None:
                stage_trace.write_stage(chunk, "COOLDOWN_SKIP")
            return None
        # #10090: a row a lock already refused stays in `lock_retry_until`
        # until a write lands, and it is the one most likely still held.
        # Waiting the full lock budget on it again bought nothing: production's
        # held 2- and 6-row cohorts failed about once a second, each spending
        # 500 ms that every later chunk and the next flush waited out in turn.
        # Probe it NOWAIT instead. The first price attempt has the short
        # statement budget; rerank keeps the chunk budget, final drain waits.
        probe = not final and any(oid in lock_retry_until for oid in chunk)
        # #10090 (Root attempt71): only a whole game chunk — every leg names
        # its event, none is a prop or an open-catalog leg — takes the game
        # loop's own first wait; the side loops never write such a chunk.
        game_chunk = bool(chunk) and all(
            event_id_by_outcome.get(oid) is not None
            and oid not in non_blend_outcome_ids
            and oid not in open_outcome_ids
            for oid in chunk
        )
        price_lock_timeout_ms = (
            catalog_boundary.game_price_lock_timeout_ms
            if game_chunk else PRICE_STATEMENT_LOCK_TIMEOUT_MS
        )
        bound_price_statement = (
            not final and game_chunk and getattr(blend_refresher, "preview", False)
            and bool(getattr(blend_refresher, "preview_events", ()))
        )
        # Includes unrelated game B: bounding B is what lets a later DNPL A
        # reach the same serial writer. Side loops and disabled/final stay as-is.
        previous_statement_timeout = None
        rolled_back_statement_timeout = None
        price_statement_timeout_seen = False
        # A hold that outlasts a try this short is ordinary, not news: its
        # first timeout is counted like a probe's repeat, never logged as a
        # flush error (one Sentry event per 1–50 ms hold otherwise).
        short_first_wait = price_lock_timeout_ms < PRICE_STATEMENT_LOCK_TIMEOUT_MS
        probe_refused = False
        price_lock_timed_out = False
        clock_ticket = None
        clock_owner = None
        write_clock = None
        try:
            async with get_task_session() as session:
                if stage_trace is not None:
                    stage_trace.write_stage(chunk, "SESSION")
                if not final:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(price_lock_timeout_ms)},
                    )
                # #10664: the chunk's price writes in ONE statement — the same
                # set clause, row-lock order and returned-row coverage as the
                # per-row UPDATEs it replaces (`chunk_price_update_stmt`).
                now = _mono()
                # #10090: a leg the #11138 overlay holds is forced. Its events
                # row may carry the held quote, not the stored price, so an
                # input returning to the stored price is not "unchanged": the
                # filter took no lock and returned nothing, the held quote was
                # released and no stamp was owed, leaving the page on the held
                # value (Root attempt67: 1 of 36 reversals, 24.7 s). Forced, a
                # still-held row refuses and the overlay holds the new quote; a
                # landed write returns the row and its event is stamped. Twin
                # of the Kalshi socket's held-leg `forced_ids` (attempt30).
                held_price_quotes = getattr(blend_refresher, "held_quotes", None)
                forced = {
                    oid for oid in chunk
                    if final or (held_price_quotes is not None and oid in held_price_quotes)
                    or oid not in successful_price_write_at
                    or now - successful_price_write_at[oid] >= PM_QUOTE_LIVENESS_SECONDS
                }
                if bound_price_statement:
                    previous_statement_timeout = (await session.execute(
                        ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(DNPL_PRICE_STATEMENT_TIMEOUT_MS)},
                    )).scalar_one()
                clock_ticket = (
                    held_price_quotes.begin_write_clock()
                    if game_chunk and not final and held_price_quotes is not None else None
                )
                try:
                    if stage_trace is not None:
                        stage_trace.write_stage(chunk, "STATEMENT_START")
                    result = await session.execute(
                        chunk_price_update_stmt(chunk, force_ids=forced, nowait=probe)
                    )
                except Exception as exc:
                    # Only the probe's own statement, and only PostgreSQL's
                    # NOWAIT row refusal by its message — never elapsed time: a
                    # refusal delivered 60 ms late re-armed the cooldown and
                    # left the pair unwritten 2.18 s after its holder let go
                    # (Root, real PG). A lock_timeout cancellation (a table
                    # lock this statement queued on) is separately identified
                    # for next-cadence retry; other failures keep their cooldown.
                    probe_refused = probe and is_price_row_lock_refusal(exc)
                    price_lock_timed_out = is_lock_timeout(exc)
                    if previous_statement_timeout is not None and is_price_statement_timeout(exc):
                        price_statement_timeout_seen = True
                        # A server cancellation aborted this transaction. Only
                        # a successful explicit rollback AND successful context
                        # cleanup may hand its frozen cohort to the held path.
                        await session.rollback()
                        rolled_back_statement_timeout = exc
                    raise
                if previous_statement_timeout is not None:
                    await session.execute(
                        SET_STATEMENT_TIMEOUT_SQL, {"ms": previous_statement_timeout},
                    )
                # The shorter budget belongs only to the price-row attempt.
                # Rerank and other transaction work keep their existing budget.
                if not final:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(PRICE_CHUNK_LOCK_TIMEOUT_MS)},
                    )
                written_rows = sorted(result.all(), key=lambda r: r.ord)
                if clock_ticket is not None:
                    clocks = [getattr(row, "database_clock", None) for row in written_rows]
                    write_clock = max((value for value in clocks if value is not None), default=None)
                if stage_trace is not None:
                    stage_trace.write_stage(chunk, "STATEMENT_END")
                # #9484: only a row the UPDATE returned is evidence — a
                # buffered id whose row is gone signals nothing. And only
                # a row whose stored price moved: the same price again
                # still re-stamps `last_updated` (liveness), but a frame
                # for it sends every held page to re-read an unchanged row
                # (twin of the Kalshi socket's, ux #9526). Walked in chunk
                # order, so invalidations stage exactly as they did per row.
                for row in written_rows:
                    if not row.quote_moved:
                        stats["quotes_unchanged"] += 1
                        continue
                    queue_market_change(
                        session,
                        market_id=row.market_id,
                        source="polymarket",
                        outcome_observed_at={row.id: row.last_updated},
                    )

                # #6598 / CERT-3182, twin of the Kalshi socket's. Every price
                # above moved the value `rank` is derived from and this module
                # has never written that column, so a crossing mid-game left the
                # board numbered by whichever poll last saw it. One statement
                # for every market the chunk touched, in the same session as the
                # prices. `market_by_outcome` is the slate map already in memory
                # (plus the open contracts' legs) — no per-flush lookup on a
                # two-second cadence.
                reranked_markets = {
                    row.market_id for row in written_rows
                }
                if reranked_markets:
                    stats["ranks_rederived"] += (
                        await session.execute(
                            rerank_market_fields_stmt(sorted(reranked_markets))
                        )
                    ).rowcount
            stats["price_updates"] += len(written_rows)
            stats["open_contract_prices_written"] += sum(
                1 for row in written_rows if row.id in open_outcome_ids
            )
        except Exception as exc:
            if stage_trace is not None:
                stage_trace.write_stage(
                    chunk, "FAILED",
                    reason="PRICE_STATEMENT_TIMEOUT" if exc is rolled_back_statement_timeout
                    else "LOCK_PROBE_REFUSED" if probe_refused
                    else "LOCK_TIMEOUT" if is_lock_timeout(exc)
                    else type(exc).__name__,
                )
            if exc is rolled_back_statement_timeout:
                # Separate from a row-lock refusal: the price statement spent
                # its own runtime budget. Keep ordinary buffered retry/overlay
                # admission; a cleanup replacement error never enters here.
                stats["price_statement_timeouts"] = stats.get("price_statement_timeouts", 0) + 1
                lock_retry_until.update({oid: lock_retry_until.get(oid, 0) for oid in chunk})
                lock_retry_events.update(event_ids_for_outcomes(event_id_by_outcome, chunk))
                return None
            if price_statement_timeout_seen:
                # Rollback/cleanup replaced the UPDATE error. It must never
                # inherit held admission, even if cleanup itself says 55P03.
                stats["errors"] += 1
                stats["requeued"] += len(chunk)
                logger.exception("Polymarket WS: price timeout cleanup failed")
                return False
            # Q491 — THE SHIP. The chunk is still in `price_buffer`, so the next
            # flush retries it. Before Q491 the buffer was drained up front and
            # a failed write DISCARDED those prices outright: the socket only
            # refills an outcome when that market ticks again, and 86.7% of open
            # Polymarket markets never tick at all, so one transient error froze
            # a card at its old number indefinitely with no `last_updated`
            # either (#2024).
            #
            # Bounded by construction: the buffer is keyed by outcome_id over a
            # fixed subscription, so a long outage holds at most one entry per
            # subscribed outcome however many attempts are burned.
            # #10090 (lane1 R1): a lock timeout on a probe's price statement
            # is the same known hold seen again — a table lock it queued on, or
            # an unrecognised row refusal. With no cooldown it recurs every
            # flush, once per retried event, so it is counted, not logged: the
            # episode's first timeout (no probe yet) was the logged error — on
            # the 50 ms budget; a fast game chunk's 1 ms first try is counted.
            # Rerank and commit failures keep their error log on every attempt.
            counted_timeout = (
                (probe or (short_first_wait and not final)) and price_lock_timed_out
            )
            if probe_refused or counted_timeout:
                # #10090 recovery: a refused probe waited for nothing (a timed
                # out one at most 50 ms), so it re-arms no cooldown unless the
                # overlay holds the whole chunk (below). Re-arming the two seconds left a pair
                # whose holder let go 100 ms later unwritten for 2.2 s on real
                # PostgreSQL (parent: 0.62 s). The rows stay known-held and due,
                # so each flush probes them once, NOWAIT, at a round trip's
                # cost; the first after the holder lets go writes the pair.
                # Counted apart from `errors` and not logged per refusal: it
                # recurs every flush the holder keeps the row. A lock failure
                # outside the price statement (rerank or commit) keeps
                # the cooldown and error accounting.
                counter = (
                    "price_lock_probes_refused" if probe_refused
                    else "price_lock_timeouts"
                )
                stats[counter] = stats.get(counter, 0) + 1
                # #10090 (Root attempt68): the one exception. A refused chunk
                # whose every leg the #11138 overlay already holds is
                # re-probed at most every 250 ms, not every 25 ms game flush.
                # Its readers lose nothing: a cooling chunk still returns None,
                # so each newer quote is held and stamped as above. Only the
                # stored row waits, at most 250 ms past the holder's release.
                # A leg the overlay lacks, an open-catalog leg, a timeout and
                # the final drain keep the no-cooldown probe (36/36 changes
                # kept, attempted UPDATEs 8592 -> 5121 in the same replay).
                held_price_quotes = getattr(blend_refresher, "held_quotes", None)
                next_probe = (
                    _mono() + min(PRICE_FLUSH_SECONDS, 0.25)
                    if probe_refused
                    and held_price_quotes is not None
                    and all(oid in held_price_quotes for oid in chunk)
                    and not any(oid in open_outcome_ids for oid in chunk)
                    else None
                )
                lock_retry_until.update({
                    oid: next_probe if next_probe is not None else lock_retry_until.get(oid, 0)
                    for oid in chunk
                })
                lock_retry_events.update(
                    event_ids_for_outcomes(event_id_by_outcome, chunk)
                )
                return None
            stats["errors"] += 1
            stats["requeued"] += len(chunk)
            logger.exception(
                "Polymarket WS: flush error (%d retained for retry)", len(chunk)
            )
            if not final and is_lock_timeout(exc):
                # A price-statement lock timeout arms no cooldown: the rows
                # are probed NOWAIT from the next flush. Rerank and commit
                # lock timeouts keep the two-second backoff.
                retry_delay = 0.0 if price_lock_timed_out else PRICE_FLUSH_SECONDS
                until = _mono() + retry_delay
                lock_retry_until.update(dict.fromkeys(chunk, until))
                lock_retry_events.update(
                    event_ids_for_outcomes(event_id_by_outcome, chunk)
                )
                return None
            return False

        # Only a successful session exit proves this price write committed.
        # Adopt before publication/cleanup can yield; accepted inputs keep their
        # frozen bounds. A replaced owner cannot inherit this proof.
        if (clock_ticket is not None
                and held_price_quotes is getattr(blend_refresher, "held_quotes", None)
                and held_price_quotes.publish_write_clock(clock_ticket, write_clock)):
            clock_owner = held_price_quotes

        if stage_trace is not None:
            stage_trace.write_stage(chunk, "COMMITTED", rows=written_rows)
        for oid in chunk:
            lock_retry_until.pop(oid, None)
        successful_price_write_at.update(dict.fromkeys(
            (row.id for row in written_rows), _mono(),
        ))
        note_committed = getattr(blend_refresher, "note_committed_rows", None)
        if written_rows and not final and callable(note_committed):
            # Before any await: the committed rows' own preview may go out
            # ahead of the stamp's read (`note_committed_rows`).
            note_committed(written_rows)
        # Register publication immediately after COMMIT, before buffer cleanup
        # can be interrupted. The game flush owns and joins its one sender so
        # event stamping can proceed while this separate notification awaits
        # Redis. Standalone writes retain their inline publication contract.
        if start_market_publish is None:
            await blend_refresher.publish_market_changes(session)
        else:
            start_market_publish(session)

        # Q491 repair 2 — the write landed, so and only so do these entries
        # leave the buffer. The `== prob` test is what used to be `setdefault`:
        # `handle_price` may have buffered a FRESHER price for the same outcome
        # while this write was in flight, and that newer value is the truth, so
        # it must survive to the next flush rather than be dropped as "already
        # written". Same contract, enforced at removal instead of at re-queue.
        async with buffer_lock:
            for outcome_id, prob in chunk.items():
                if price_buffer.get(outcome_id) == prob:
                    del price_buffer[outcome_id]
            # #11138: the row now holds a price at least this new.
            held_quotes = getattr(blend_refresher, "held_quotes", None)
            if held_quotes is not None:
                held_quotes.release(chunk)
        # A zero-return statement still acknowledged the unchanged inputs.
        # Clear only matching buffered values, but never stamp those inputs as
        # a new database observation or rerank their unchanged markets.
        return _PMPriceWriteResult((row.id for row in written_rows), clock_owner=clock_owner)

    async def flush_withdrawals(
        *,
        only_events: Optional[set[int]] = None,
        exclude_events: frozenset[int] | set[int] = frozenset(),
        standalone: Optional[bool] = None,
        props: Optional[bool] = None,
        final: bool = False,
        before_write=None,
        background_publish=False,
    ) -> Optional[list[int]]:
        """#9934: withdraw the held prices the latest wide books priced out.

        Same bookkeeping as ``write_chunk``: an entry leaves the buffer only
        after its transaction lands, and only if no newer book replaced it
        meanwhile. Returns withdrawn ids, or None on non-lock failure. A held
        withdrawal returns no ids and keeps its book/cohort owed for retry.
        #10651: a finished game's work can run before unrelated price chunks.
        The tail excludes attempted events, so even a failure is tried once.
        #10090: ``standalone`` True/False takes only/no standalone legs, so
        each loop withdraws after its own prices; None (final drain) takes all.
        ``props`` True/False likewise takes only/no non-speaking props
        (`flush_props`), so a prop's withdrawal follows its price in one loop.
        ``before_write(books)`` sees the exact snapshot before its transaction.
        """
        # #10090 `preview_from_commit`: a withdrawal (or its source removal)
        # changes rows outside the price write; committed or maybe so, no
        # cached read graph keeps them.
        from app.tasks.live_blend_refresh import forget_preview_outcomes
        from app.tasks.live_blend_refresh import _mono
        from app.tasks.polymarket_ws import (
            PMWithdrawalMarketPublisher, PMWithdrawalOwnershipDeferred,
        )
        from app.utils.kalshi_empty_book import book_refutes_price

        # #10090: committed explicit withdrawals whose source removal is still
        # owed, durable across a restart (`PMWithdrawalDebt`). Reached through
        # the refresher: no new name.
        market_owner = getattr(blend_refresher, "withdrawal_market_publisher", None)
        if market_owner is None:
            market_owner = PMWithdrawalMarketPublisher()
            blend_refresher.withdrawal_market_publisher = market_owner
        if final:
            market_owner.start(blend_refresher)
            await market_owner.join()
        withdrawal_debt = getattr(blend_refresher, "withdrawal_debt", None)
        if withdrawal_debt is not None:
            await withdrawal_debt.load(get_task_session)
            await withdrawal_debt.publish_pending(
                blend_refresher, get_task_session, background=background_publish, final=final,
            )
        async with buffer_lock:
            debt_events = withdrawal_debt.legs() if withdrawal_debt is not None else {}
            held_events = (
                {
                    event_id_by_outcome.get(oid, debt_events.get(oid))
                    for oid, until in withdrawal_retry_until.items()
                    if (oid in withdraw_buffer or oid in debt_events) and until > _mono()
                }
                if not final else set()
            )
            alone = (
                standalone_open_outcome_ids(
                    withdraw_buffer, open_outcome_ids, event_id_by_outcome,
                    open_complement_of,
                )
                if standalone is not None
                else set()
            )
            books = {
                oid: book
                for oid, book in withdraw_buffer.items()
                if (standalone is None or (oid in alone) == standalone)
                and (props is None or (oid in non_blend_outcome_ids) == props)
                and (only_events is None or event_id_by_outcome.get(oid) in only_events)
                and event_id_by_outcome.get(oid) not in exclude_events
                and event_id_by_outcome.get(oid) not in held_events
            }
            # Owed removals take the same loop and event gates as books. A leg
            # whose newer quote is still buffered is judged after that write.
            debts = [
                debt
                for debt in (withdrawal_debt.owed.values() if debt_events else ())
                if debt.id not in price_buffer
                and (standalone is None or (debt.id in alone) == standalone)
                and (props is None or (debt.id in non_blend_outcome_ids) == props)
                and (only_events is None or debt.event_id in only_events)
                and debt.event_id not in exclude_events
                and debt.event_id not in held_events
            ]
            refuted_buffer = {
                oid: (price_buffer[oid], input_marks.get(oid))
                for oid, (bid, ask) in books.items()
                if oid in price_buffer
                and book_refutes_price(bid, ask, price_buffer[oid])
            }
        if not books and not debts:
            return []
        if before_write is not None:
            # It judges legs by id only; an owed removal is ordered like a book.
            kept = await before_write(
                {**{debt.id: None for debt in debts}, **books} if debts else books
            )
            if kept is not None:
                # #10090: books on an event whose stamp is still queued or
                # running stay buffered for a later flush (`join_stamp_reading`).
                books = {oid: book for oid, book in books.items() if oid in kept}
                debts = [debt for debt in debts if debt.id in kept]
                if not books and not debts:
                    return []
        rows = []
        strays = []
        if books:
            from sqlalchemy import text

            withdrawal_xid = None
            withdrawal_commit_started = False
            try:
                async with get_task_session() as session:
                    if not final:
                        await session.execute(
                            SET_LOCK_TIMEOUT_SQL,
                            {"ms": lock_timeout_value(PRICE_CHUNK_LOCK_TIMEOUT_MS)},
                        )
                    if withdrawal_debt is not None:
                        await withdrawal_debt.guard_owner(session)
                        withdrawal_xid = (await session.execute(
                            text("SELECT pg_current_xact_id()::text")
                        )).scalar_one()
                    rows = await withdraw_book_refuted_prices(session, books)
                    for row in rows:
                        if row.last_updated is None:
                            continue  # no observation stamp to push; REST serves it
                        queue_market_change(
                            session,
                            market_id=row.market_id,
                            source="polymarket",
                            outcome_observed_at={row.id: row.last_updated},
                        )
                    # #6598: a withdrawn leg leaves the field `rank` orders.
                    markets = sorted({row.market_id for row in rows})
                    if markets:
                        stats["ranks_rederived"] += (
                            await session.execute(rerank_market_fields_stmt(markets))
                        ).rowcount
                    if withdrawal_debt is not None:
                        # The withdrawal commits only with its owed removal.
                        recorded = await withdrawal_debt.record(session, rows)
                        withdrawn_now = {row.id for row in rows}
                        strays = await withdrawal_debt.strays(session, {
                            oid for oid in books
                            if oid not in withdrawn_now and oid not in debt_events
                            and oid not in non_blend_outcome_ids
                            and event_id_by_outcome.get(oid) is not None
                        })
                    withdrawal_commit_started = True
            except BaseException as exc:
                forget_preview_outcomes(blend_refresher, books)
                # The commit may have landed unacknowledged (a dropped
                # connection, or cancellation during its await): the next
                # flush re-reads every durable row memory does not hold.
                if withdrawal_debt is not None:
                    withdrawal_debt.require_reload(
                        uncertain=withdrawal_commit_started and not is_lock_timeout(exc),
                        xid=withdrawal_xid,
                    )
                if not isinstance(exc, Exception):
                    raise
                if isinstance(exc, PMWithdrawalOwnershipDeferred):
                    until = _mono() + min(PRICE_FLUSH_SECONDS, 0.25)
                    withdrawal_retry_until.update(dict.fromkeys(books, until))
                    return []
                stats["errors"] += 1
                logger.exception(
                    "Polymarket WS: withdrawal error (%d retained for retry)", len(books)
                )
                if not final and is_lock_timeout(exc):
                    # Keep the complete failed transaction; newer books on another
                    # leg of its event must not bypass this eligibility cooldown.
                    until = _mono() + PRICE_FLUSH_SECONDS
                    withdrawal_retry_until.update(dict.fromkeys(books, until))
                    return []
                return None
            forget_preview_outcomes(blend_refresher, books)
            if withdrawal_debt is not None:
                withdrawal_debt.adopt(recorded)
                # A leg whose newer quote arrived meanwhile waits for that write.
                debts.extend(debt for debt in recorded if debt.id not in price_buffer)
            await market_owner.offer(
                session, blend_refresher, background=background_publish,
            )
        settled = []
        invalidations = []
        if debts or strays:
            from app.tasks.polymarket_ws import withdraw_attributed_event_sources

            from sqlalchemy import text

            removal_xid = None
            removal_commit_started = False
            try:
                async with get_task_session() as removal_session:
                    if not final:
                        await removal_session.execute(
                            SET_LOCK_TIMEOUT_SQL,
                            {"ms": lock_timeout_value(PRICE_CHUNK_LOCK_TIMEOUT_MS)},
                        )
                    await withdrawal_debt.guard_owner(removal_session)
                    removal_xid = (await removal_session.execute(
                        text("SELECT pg_current_xact_id()::text")
                    )).scalar_one()
                    # The rows settle with the removal, or neither commits.
                    settled = await withdrawal_debt.settle(removal_session, debts + strays)
                    invalidations = await withdraw_attributed_event_sources(
                        removal_session, settled,
                    )
                    pending_publications = await withdrawal_debt.record_publications(
                        removal_session, invalidations,
                    )
                    removal_commit_started = True
            except BaseException as exc:
                forget_preview_outcomes(blend_refresher, {debt.id for debt in debts + strays})
                # Commit/close may have completed without acknowledgement.
                # Reload the durable publication on the next flush or restart.
                withdrawal_debt.require_reload(
                    uncertain=removal_commit_started and not is_lock_timeout(exc),
                    xid=removal_xid,
                )
                if not isinstance(exc, Exception):
                    raise
                if isinstance(exc, PMWithdrawalOwnershipDeferred):
                    until = _mono() + min(PRICE_FLUSH_SECONDS, 0.25)
                    withdrawal_retry_until.update(
                        dict.fromkeys({debt.id for debt in debts + strays}, until)
                    )
                    return []
                # The withdrawal is committed and its debt still owed: in
                # memory, and durably in its row.
                # A failed acknowledgement can follow a successful commit.
                # Confirm via custody before paying the full failed-flush backoff.
                await withdrawal_debt.load(get_task_session)
                await withdrawal_debt.publish_pending(
                    blend_refresher, get_task_session, background=background_publish, final=final,
                )
                stats["errors"] += 1
                logger.exception("Polymarket WS: source withdrawal retained for retry")
                if not final and is_lock_timeout(exc):
                    until = _mono() + min(PRICE_FLUSH_SECONDS, 0.25)
                    withdrawal_retry_until.update(
                        dict.fromkeys({debt.id for debt in debts + strays}, until)
                    )
                    return []
                return None
            forget_preview_outcomes(blend_refresher, {debt.id for debt in debts + strays})
            # A resolver/CAS refusal settles too: a valid alternative, a newer
            # quote or a terminal result owns the source now.
            withdrawal_debt.publications.update(pending_publications)
            withdrawal_debt.settled(debts + strays)
            for debt in debts:
                withdrawal_retry_until.pop(debt.id, None)
        for oid in books:
            withdrawal_retry_until.pop(oid, None)
        if invalidations:
            from app.tasks.polymarket_ws import _publish_committed_withdrawals

            if withdrawal_debt is not None:
                await withdrawal_debt.publish_pending(
                    blend_refresher, get_task_session, background=background_publish, final=final,
                )
            else:
                await _publish_committed_withdrawals(blend_refresher, invalidations)
        async with buffer_lock:
            for oid, book in books.items():
                if withdraw_buffer.get(oid) == book:
                    # Retire only the refuted input captured with this book.
                    # Newer inputs, even at the same price, still own their write.
                    refuted = refuted_buffer.get(oid)
                    if (refuted is not None
                            and price_buffer.get(oid) == refuted[0]
                            and input_marks.get(oid) is refuted[1]):
                        price_buffer.pop(oid, None)
                    del withdraw_buffer[oid]
        stats["held_prices_withdrawn"] += len(rows)
        # R-A: a leg whose removal settled on this pass is returned even when
        # an earlier pass committed its withdrawal, so its stamp is never lost.
        return list(dict.fromkeys(
            [row.id for row in rows] + [debt.id for debt in settled]
        ))

    async def _flush_prices(flush_started=None, final=False):
        """One flush. Non-lock failures return False for the cadence retry;
        lock-held whole chunks retain their own eligibility cooldown. #10090
        ``flush_started`` is this flush's start, for the refresher's floor."""
        import asyncio  # the pipelined stamp below; executed rigs bring no globals
        from app.tasks.polymarket_ws import PMWithdrawalMarketPublisher
        from app.tasks.live_blend_refresh import _mono
        from app.tasks.polymarket_ws import (
            _PMHeadlineEvents, _pm_lock_isolated_chunks, _pm_pure_bridged_legs,
        )

        stamp_owner = catalog_boundary.stamp_owner(blend_refresher)
        # Reap completion before deciding whether the next batch can overlap.
        if stamp_owner.task is not None and stamp_owner.task.done():
            await stamp_owner.join()

        headline_event_ids = _PMHeadlineEvents(
            event_id_by_outcome, () if final else non_blend_outcome_ids,
        )

        work_noted = False

        def note_flush_work():
            nonlocal work_noted
            if not work_noted:
                work_noted = True
                catalog_boundary.flush_work += 1

        def owed_beside(unfinished_events, withdrawing_events=()):
            # #10090: what a debt drain beside these deferred events can take;
            # None while the refresher cannot say (membership unknown).
            reader = getattr(blend_refresher, "owed_beside", None)
            if reader is not None:
                return set(reader(unfinished_events, withdrawing_events))
            pending_reader = getattr(blend_refresher, "pending_event_ids", None)
            return (
                None if pending_reader is None
                else set(pending_reader()).difference(unfinished_events)
            )

        async def refresh_owed(unfinished_events, withdrawing_events=()):
            # #10090: the quiet ending's owed stamps. Awaited here, one held
            # event's debt (a stamp waiting on its row lock) held this flush's
            # return, so the cadence could start no flush and every unrelated
            # fresh quote waited behind it (Root, real PG: 0.81 s vs 0.13 s).
            # A timed flush instead hands the debt to the one stamp owner and
            # returns, exactly as a fresh chunk does: later flushes write and
            # `admit_fresh` beside it, and the held event stays fenced. The
            # final drain and untimed calls still await it (no later flush
            # would finish it), as does a call with nothing owed (free).
            owed_events = owed_beside(unfinished_events, withdrawing_events)
            # #10090 `owed_past_withdrawal`: only when there is one, so a
            # caller without the argument is called exactly as before.
            extra = {"withdrawing_event_ids": withdrawing_events} if withdrawing_events else {}
            if final or flush_started is None or owed_events == set():
                await blend_refresher.refresh_pending(
                    flush_started=flush_started, defer_event_ids=unfinished_events,
                    **extra,
                )
                return
            # Capture BEFORE the call consumes the debt, as the fresh chunk's
            # owner start does. Existing debt, so nothing is fresh.
            stamp_owner.events = owed_events
            stamp_owner.fresh = set()
            stamp_owner.task = asyncio.create_task(blend_refresher.refresh_pending(
                flush_started=flush_started, defer_event_ids=unfinished_events,
                **extra,
            ))
            try:
                # One turn: the call takes its debt and asks for a connection.
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                # Outside the chunk loop's handler: join the owner we started.
                await stamp_owner.join(cancel=True)
                raise

        async def join_stamp_reading(books):
            # #10090: a withdrawal follows the running stamp unless every leg
            # in it is one no blend reads (a venue-refuted prop) and the
            # stamp's membership is known. Judged on the transaction's own
            # snapshot, so a book arriving after it belongs to a later pass.
            # Returns the books to withdraw now (None: all of them).
            if stamp_owner.task is None:
                note_flush_work()
                return None
            speaking = event_ids_for_outcomes(headline_event_ids, books)
            if stamp_owner.events is not None and not speaking:
                note_flush_work()
                return None
            held = (
                None
                if final or flush_started is None or stamp_owner.task.done()
                else stamp_owner.held_events()
            )
            if held is None:
                note_flush_work()
                await stamp_owner.join()
                return None
            # #10090, as the price fence: joining here waited for the WHOLE
            # refresh whenever any game's wide book was buffered, so every
            # flush with a withdrawal held every independent game behind the
            # slowest stamp in the call. Only a book on an event whose stamp
            # is still queued or running waits now, buffered for a later
            # flush; the rest withdraw, and their stamp is ordered after the
            # returned one (admitted again, or the joined path below).
            fenced = held.intersection(speaking)
            if not fenced:
                note_flush_work()
                return books
            stamp_owner.note_fenced(fenced)
            kept = {
                oid: book for oid, book in books.items()
                if headline_event_ids.get(oid) not in fenced
            }
            stats["stamp_fenced"] += len(books) - len(kept)
            if kept:
                note_flush_work()
            return kept

        async with buffer_lock:
            batch = dict(price_buffer)
            if not final:
                # #10090: standalone legs are `flush_standalone`'s and linked
                # props `flush_props`'s; the final drain has no such loops
                # after it, so it takes them too. A prop chunk written here
                # held this flush's return, so the cadence started no flush
                # and a fresh game quote stayed buffered after its own stamp
                # released (Root's held-tail rig: 0.60 s held, 0.25 s unheld).
                # Stage trace 43011 waited 4.67 s at that boundary; what held
                # its flush there is not known.
                for oid in standalone_open_outcome_ids(
                    batch, open_outcome_ids, event_id_by_outcome,
                    open_complement_of,
                ):
                    del batch[oid]
                for oid in [oid for oid in batch if oid in non_blend_outcome_ids]:
                    del batch[oid]
            batch_marks = {oid: input_marks[oid] for oid in batch if oid in input_marks}
            stage_trace = getattr(tail_receipts, "exact_trace", None)
            if stage_trace is not None:
                stage_trace.flush_begin(flush_started, final, batch_marks, batch)
            # #10090 / #837: events a held-price withdrawal may still touch
            # this flush. Their refresh waits for that transaction when the
            # withdrawn leg is one the blend reads (`speaking_withdrawals`).
            withdraw_cohort_ids = set(withdraw_buffer)
            withdraw_events = event_ids_for_outcomes(
                event_id_by_outcome, withdraw_cohort_ids,
            )
            side_books = standalone_open_outcome_ids(
                withdraw_cohort_ids, open_outcome_ids, event_id_by_outcome,
                open_complement_of,
            )
            if not final:
                side_books |= withdraw_cohort_ids & non_blend_outcome_ids
            if (withdraw_cohort_ids - side_books).intersection(
                withdrawal_retry_until
            ):
                note_flush_work()
        unfinished_price_ids: set[int] = set()
        # Committed this flush, refresh not yet called.
        owed: list[int] = []
        wrote_all = True
        attempted_withdraw_events: set[int] = set()
        failed_price_events: set[int] = set()
        lock_deferred_events: set[int] = set()
        # #10090: events whose stamp the running refresh still held when their
        # chunk came up; their prices stay buffered for a later flush.
        fenced_events: set[int] = set()
        # #10090: bridged cohorts the bridged writer committed since the last
        # flush owe their stamp exactly as a chunk this flush committed does,
        # with the committed input marks (over any newer unwritten one). Taken
        # here, they are this flush's alone, so they are recorded as debt
        # FIRST, before any await: a flush cancelled before stamping them
        # leaves them owed, never lost. Stamping them below (fresh, as
        # before) settles that debt with them.
        taken = catalog_boundary.bridges.take_completed()
        adopt_pending = getattr(blend_refresher, "adopt_pending", None)
        for done_ids, done_marks, _ in taken:
            note_flush_work()
            if adopt_pending is not None:
                adopt_pending(event_ids_for_outcomes(headline_event_ids, done_ids))
            for oid in done_ids:
                if oid not in owed:
                    owed.append(oid)
                if oid in done_marks:
                    batch_marks[oid] = done_marks[oid]
        # #10090: pure bridged events' buffered legs. This flush never writes
        # them (the partition below hands them to the bridged writer), so
        # they never defer a committed cohort's stamp here.
        bridged: dict[int, list[int]] = {}
        if batch and not final and flush_started is not None:
            bridged = _pm_pure_bridged_legs(
                batch, open_outcome_ids, event_id_by_outcome, open_complement_of,
                non_blend_outcome_ids,
            )
        if owed and not final and flush_started is not None:
            # #10090: a timed flush starts the committed bridged cohorts' stamp
            # through the one stamp owner NOW — admitted to the running call,
            # or as its task — exactly as a chunk's ready cohort is. Left to
            # the tail, a flush with no game price of its own awaited that
            # stamp inline, so one held bridged event's stamp held every
            # unrelated game's next quote. Deferred: events this flush may
            # still write or withdraw (their stamp follows that), and any the
            # bridged writer still owns. A refused event stays the debt
            # recorded above; nothing is joined.
            #
            # A newer price for a pure bridged event is NOT this flush's write:
            # the stamp goes first, and the partition below keeps that price
            # buffered while the stamp holds the event. Deferring it here
            # handed the newer write to the bridged writer instead, so on a
            # continuously ticking event every committed cohort's stamp was
            # deferred behind the next one (Root: seven cohorts committed,
            # zero event frames until the venue went quiet). A stamp refused
            # here (a call that no longer admits) stays debt; the newer pair
            # then goes ahead and its own completion takes the next turn.
            async with buffer_lock:
                defer = (
                    event_ids_for_outcomes(
                        headline_event_ids,
                        [oid for oid in batch if headline_event_ids.get(oid) not in bridged],
                    )
                    | event_ids_for_outcomes(headline_event_ids, withdraw_buffer)
                    | catalog_boundary.bridges.unstamped
                )
            ready = [
                oid for oid in owed
                if headline_event_ids.get(oid) is not None
                and headline_event_ids.get(oid) not in defer
            ]
            start_events = event_ids_for_outcomes(headline_event_ids, ready)
            ready_marks = [
                batch_marks[oid] for oid in ready
                if oid in batch_marks and oid not in headline_event_ids.non_speakers
            ]
            if start_events and stamp_owner.task is not None and not stamp_owner.task.done():
                admitted = blend_refresher.admit_fresh(
                    start_events, flush_started=flush_started, marks=ready_marks,
                    defer_event_ids=defer,
                )
                stamp_owner.fresh.update(admitted)
                if stamp_owner.events is not None:
                    stamp_owner.events.update(admitted)
            elif start_events:
                tail_receipts.stage(ready_marks)
                pending_reader = getattr(blend_refresher, "pending_event_ids", None)
                stamp_owner.events = (
                    None if pending_reader is None
                    else (start_events | set(pending_reader())).difference(defer)
                )
                stamp_owner.fresh = set(start_events)
                stamp_owner.task = asyncio.create_task(blend_refresher.refresh(
                    start_events, flush_started=flush_started, defer_event_ids=defer,
                ))
                try:
                    # One turn: the call takes its receipts and opens its door,
                    # so the partition below sees these events as held.
                    await asyncio.sleep(0)
                except asyncio.CancelledError:
                    await stamp_owner.join(cancel=True)
                    raise
            # Every completion is now started, admitted or owed as debt (a
            # deferred one is stamped after the write or withdrawal that
            # deferred it, or from that debt): none rides this flush's tail.
            owed = []
        # #10090: pure bridged events whose cohort waits for the bridged
        # writer this flush (in flight, fenced, cooling down or queue full).
        # Their prices stay buffered and their withdrawals wait with them.
        bridge_waiting: set[int] = set()
        if bridged:
            # WHOLE-EVENT PARTITION: a pure bridged event's legs are never
            # this flush's write; they go to the one bridged writer, a
            # whole event per cohort, oldest first, or stay buffered.
            for legs in bridged.values():
                for oid in legs:
                    del batch[oid]
            bridges = catalog_boundary.bridges
            held: Optional[set[int]] = set()
            if stamp_owner.task is not None and not stamp_owner.task.done():
                held = stamp_owner.held_events()
            now = _mono()
            cohort: list[int] = []
            cohort_events: set[int] = set()
            # #10090 (Argon rank 4): events whose latest stamp read said live.
            # Their cohorts are offered first and never share a cohort with a
            # pre-game event, so the bridged writer takes the side connection's
            # first turn for them (`_PMBridgeWriter.offer`).
            live_events = getattr(blend_refresher, "_live_event_ids", None) or set()
            cohort_live = False

            def offer_cohort():
                for eid in cohort_events.intersection(lock_retry_events):
                    bridges.retry_offered[eid] = now
                bridges.offer(
                    cohort, cohort_events,
                    write=write_chunk, publish=blend_refresher.publish_market_changes,
                    side_writer=catalog_boundary.side_writer, buffer_lock=buffer_lock,
                    price_buffer=price_buffer, input_marks=input_marks,
                    live=cohort_live,
                )
                stats["bridged_handed_off"] = (
                    stats.get("bridged_handed_off", 0) + len(cohort)
                )

            # Retry isolation, as `_pm_lock_isolated_chunks` gives the game
            # flush: an event a lock rollback left retry-held is its own
            # cohort, after every healthy event, so its next NOWAIT refusal
            # rolls back no other event. Packed with a healthy event, each
            # refusal on the held one rolled the healthy one back with it
            # (Root: two flushes, both attempts (900, 901, 902, 903)).
            # Retried events take turns, least recently offered first, so
            # a few held ones cannot keep a later one out of the queue.
            bridges.retry_offered = {
                eid: at for eid, at in bridges.retry_offered.items()
                if eid in lock_retry_events
            }
            order = [eid for eid in bridged if eid not in lock_retry_events]
            order += sorted(
                (eid for eid in bridged if eid in lock_retry_events),
                key=lambda eid: bridges.retry_offered.get(eid, 0.0),
            )
            order = [eid for eid in order if eid in live_events] + [
                eid for eid in order if eid not in live_events
            ]
            for eid in order:
                legs = bridged[eid]
                if (
                    held is None or eid in held or eid in bridges.reserved
                    or catalog_boundary.standalone_fenced or catalog_boundary.changing
                    or any(lock_retry_until.get(oid, 0) > now for oid in legs)
                ):
                    bridge_waiting.add(eid)
                    continue
                if cohort and (
                    len(cohort) + len(legs) > FLUSH_CHUNK_ROWS
                    or eid in lock_retry_events
                    or not cohort_events.isdisjoint(lock_retry_events)
                    or (eid in live_events) != cohort_live
                ):
                    if bridges.accepting(live=cohort_live):
                        offer_cohort()
                    else:
                        bridge_waiting.update(cohort_events)
                    cohort, cohort_events = [], set()
                cohort_live = eid in live_events
                cohort.extend(legs)
                cohort_events.add(eid)
            if cohort:
                if bridges.accepting(live=cohort_live):
                    offer_cohort()
                else:
                    bridge_waiting.update(cohort_events)
            if held and bridge_waiting:
                stamp_owner.note_fenced(bridge_waiting.intersection(held))
            stats["bridge_waiting"] = (
                stats.get("bridge_waiting", 0) + len(bridge_waiting)
            )
            note_flush_work()
        if batch:
            # #9484: every linked row, then a bounded number of open-contract
            # chunks, oldest-dirty first (the buffer's insertion order). Open
            # rows past the bound stay buffered and lead the next flush — none
            # dropped. The FINAL drain has no successor flush, so it takes
            # every row. CERT-3868: the two legs of a binary commit in one
            # transaction or wait together — never one side read beside the
            # other's old price.
            chunks = plan_flush_chunks(
                (oid for oid in batch if oid not in headline_event_ids.non_speakers),
                open_outcome_ids,
                FLUSH_CHUNK_ROWS,
                None if final else OPEN_FLUSH_CHUNKS_PER_FLUSH,
                open_complement_of,
            )
            if not final:
                # A typed rollback may have coupled unrelated events in one
                # ordinary chunk. Retry only its admitted event/question units;
                # fresh siblings then retain their own cooldown eligibility.
                isolated_events = set(lock_retry_events)
                changed_events = set()
                if getattr(blend_refresher, "preview_events", ()):
                    async with buffer_lock:
                        held_events = (
                            stamp_owner.held_events()
                            if stamp_owner.task is not None and not stamp_owner.task.done()
                            else set()
                        )
                        if held_events is not None:
                            pending_reader = getattr(blend_refresher, "pending_event_ids", None)
                            blocked = (
                                held_events | lock_retry_events
                                | catalog_boundary.bridges.reserved
                                | catalog_boundary.bridges.unstamped
                                | event_ids_for_outcomes(event_id_by_outcome, withdraw_buffer)
                                | (set(pending_reader()) if callable(pending_reader) else set())
                            )
                            held_quotes = getattr(blend_refresher, "held_quotes", None)
                            event_legs = {}
                            for oid, value in price_buffer.items():
                                eid = headline_event_ids.get(oid)
                                if eid in blend_refresher.preview_events and eid not in blocked:
                                    event_legs.setdefault(eid, []).append((oid, value))
                            for eid, legs in event_legs.items():
                                if all(
                                    oid not in open_outcome_ids
                                    and observation_continuity.get(oid) is not None
                                    and catalog_boundary.observation_ack.get(oid) is not None
                                    and observation_continuity[oid][1] == round(float(value), 6)
                                    and (held_quotes is None or oid not in held_quotes)
                                    for oid, value in legs
                                ):
                                    if all(catalog_boundary.observation_ack[oid] == observation_continuity[oid]
                                           for oid, _ in legs):
                                        isolated_events.add(eid)
                                    elif any(catalog_boundary.observation_ack[oid][1] != observation_continuity[oid][1]
                                             for oid, _ in legs):
                                        changed_events.add(eid)
                # A known unchanged cohort need not share an unrelated SQL
                # wait. This is a scheduling hint only: every admitted row still
                # reaches write_chunk, including heartbeat/held-return forcing.
                # A changed preview cohort needs its ordinary price authority
                # first, so schedule it before unrelated waits. Its existing
                # ready/stamp path then publishes DNPL; no preview bypass.
                # Market/complement units remain indivisible across events.
                chunks = _pm_lock_isolated_chunks(
                    chunks, isolated_events, event_id_by_outcome,
                    market_by_outcome, open_complement_of, FLUSH_CHUNK_ROWS,
                    first_events=changed_events,
                )
            stats["open_contract_flush_deferred"] += len(batch) - sum(
                len(c) for c in chunks
            )
            if not chunks:
                note_flush_work()
            # Preserve the existing planned-chunk boundary. Capped-out tail
            # and newer inputs still belong to later flushes; this exclusion
            # covers unfinished/failed writes admitted to THIS flush only.
            unfinished_price_ids = {oid for chunk in chunks for oid in chunk}
            # #10090 / #837: an event is refreshed once per flush, right after
            # the last transaction of this flush that can touch it. The refresh
            # used to wait for EVERY chunk, so a committed binary pair sat
            # unstamped behind an unrelated chunk's UPDATE (controlled replay
            # on 6443a89023: the pair committed and published, its event
            # waited until the later chunk's blocked row lock was released).
            # Refreshing after the FIRST chunk that touches an event instead
            # would stamp it half-written and leave the rest to the 2s
            # throttle, so an event a later chunk still writes waits for that
            # chunk, and one with a pending withdrawal waits for it.
            last_chunk_of_event: dict[int, int] = {}
            # Withdrawals judge the final stored price, including non-speakers
            # (the final drain writes props here too). Their maturity must
            # therefore wait for every planned event price, even when WIN
            # readiness no longer waits for that prop's quote.
            last_price_chunk_of_event: dict[int, int] = {}
            for index, chunk_ids in enumerate(chunks):
                for oid in chunk_ids:
                    price_event_id = event_id_by_outcome.get(oid)
                    if price_event_id is not None:
                        last_price_chunk_of_event[price_event_id] = index
                    event_id = headline_event_ids.get(oid)
                    if event_id is not None:
                        last_chunk_of_event[event_id] = index
            # #10090 — PIPELINED STAMPS, twin of the Kalshi socket's. A chunk's
            # refresh used to finish before the next chunk's write could open,
            # so an event in a later chunk waited for every earlier chunk's
            # write AND stamp in turn. A safe independent chunk N+1's write
            # overlaps chunk N's stamp. Unchanged: writes stay strictly sequential, one in flight;
            # the refresher still runs ONE refresh at a time. A later complete
            # cohort may join that call on its existing fresh workers; a refused
            # cohort joins the previous call before its receipts are staged. A
            # chunk's stamp starts only after its own write committed;
            # its market notification may run alongside the event stamp.
            # Withdrawals still follow the stamp before them. The one owner
            # may outlive an ordinary batch or catalog boundary: it retains
            # plain frames only. Completed final/shutdown joins own its lifetime.
            market_owner = getattr(blend_refresher, "withdrawal_market_publisher", None)
            if market_owner is None:
                market_owner = PMWithdrawalMarketPublisher()
                blend_refresher.withdrawal_market_publisher = market_owner

            def start_market_publish(session):
                # Detach outer-commit-confirmed frames synchronously. One sender
                # owns coalesced invalidations without retaining this session.
                market_owner.enqueue(session, blend_refresher)

            async def market_publish_done(*, cancel=False):
                if not cancel:
                    market_owner.start(blend_refresher)
                    await market_owner.join()
                    return
                task = market_owner.task
                if task is None:
                    return
                if not task.cancelling():
                    task.cancel()
                interrupted = None
                while not task.done():
                    try:
                        await asyncio.wait({task})
                    except asyncio.CancelledError as exc:
                        interrupted = exc
                        if not task.cancelling():
                            task.cancel()
                if market_owner.task is task:
                    market_owner.task = None
                if not task.cancelled() and task.exception() is not None:
                    logger.error(
                        "Polymarket WS: committed market publication failed",
                        exc_info=task.exception(),
                    )
                if interrupted is not None:
                    raise interrupted

            stamp_done = stamp_owner.join

            try:
                for index, chunk_ids in enumerate(chunks):
                    traced = (
                        None if stage_trace is None
                        else stage_trace.chunk_begin(index, chunk_ids)
                    )
                    async with buffer_lock:
                        withdraw_cohort_ids.update(withdraw_buffer)
                        speaking_withdrawals = event_ids_for_outcomes(
                            headline_event_ids, withdraw_buffer,
                        )
                    if stamp_owner.task is not None:
                        unwritten_events = {
                            eid for eid, last in last_chunk_of_event.items()
                            if last >= index
                        }
                        held = (
                            None
                            if final or flush_started is None or stamp_owner.task.done()
                            else stamp_owner.held_events()
                        )
                        if held is None:
                            # refresh() also admits retry/deferred events. Their
                            # read must stay before the next write if any cohort
                            # or withdrawal of a leg it reads is still unfinished.
                            # Unknown debt retains the serial path rather than
                            # assuming safety.
                            if stamp_owner.events is None or not stamp_owner.events.isdisjoint(
                                unwritten_events | speaking_withdrawals
                            ):
                                if traced is not None:
                                    stage_trace.chunk_note(traced, "JOINED_RUNNING_STAMP")
                                await stamp_done()
                        else:
                            # #10090, twin of the Kalshi socket's: joining here
                            # waited for the WHOLE refresh — every stamp it took
                            # or admitted — and held this write, the rest of the
                            # flush and every later flush with it. One chunk
                            # carries the whole slate, so any game in the call
                            # ticking again (its stamp returned or not) stalled
                            # every independent game. Only an event whose stamp
                            # is still queued or running is fenced now: its whole
                            # cohort stays buffered (like a lock retry, counted
                            # `stamp_fenced`) and the first flush after its stamp
                            # returns writes it. Sticky for this flush, so no
                            # event is written half. An event whose stamp has
                            # returned is written and admitted again. Its
                            # withdrawals wait the same way
                            # (`join_stamp_reading`).
                            newly_fenced = held.intersection(
                                event_ids_for_outcomes(headline_event_ids, chunk_ids)
                            )
                            if newly_fenced:
                                fenced_events.update(newly_fenced)
                                stamp_owner.note_fenced(newly_fenced)
                            if traced is not None:
                                stage_trace.fence(traced, held, fenced_events)
                    if fenced_events:
                        kept = [
                            oid for oid in chunk_ids
                            if headline_event_ids.get(oid) not in fenced_events
                        ]
                        stats["stamp_fenced"] += len(chunk_ids) - len(kept)
                        chunk_ids = kept
                        if not chunk_ids:
                            if traced is not None:
                                stage_trace.chunk_write(traced, {}, {})
                            continue
                    if catalog_boundary.bridges.reserved:
                        # #10090: a cohort the bridged writer still owns stays
                        # buffered, as a fenced one does; it wakes us when done.
                        reserved = catalog_boundary.bridges.reserved
                        kept = [
                            oid for oid in chunk_ids
                            if event_id_by_outcome.get(oid) not in reserved
                            and event_id_by_outcome.get(open_complement_of.get(oid))
                            not in reserved
                        ]
                        stats["bridge_reserved"] = (
                            stats.get("bridge_reserved", 0) + len(chunk_ids) - len(kept)
                        )
                        chunk_ids = kept
                        if not chunk_ids:
                            if traced is not None:
                                stage_trace.chunk_write(traced, {}, {})
                            continue
                    note_flush_work()
                    # The plan freezes membership/caps, not a later chunk's
                    # prices. Adopt the newest values and their matching input
                    # marks together, after any preceding stamp has joined.
                    # Handlers update complementary legs under this same lock;
                    # newly buffered ids still belong to a successor flush.
                    held_quotes = getattr(blend_refresher, "held_quotes", None)
                    async with buffer_lock:
                        observation_generation = None
                        observation_tokens = {}
                        if getattr(blend_refresher, "preview_events", ()):
                            observation_generation = routing_generation
                            observation_tokens = {
                                oid: observation_continuity.get(oid) for oid in chunk_ids
                            }
                            catalog_boundary.observation_writing = {
                                eid for eid in event_ids_for_outcomes(headline_event_ids, chunk_ids)
                                if eid in blend_refresher.preview_events
                            }
                            for eid in catalog_boundary.observation_writing:
                                catalog_boundary.observation_write_epoch[eid] = (
                                    catalog_boundary.observation_write_epoch.get(eid, 0) + 1
                                )
                        current_chunk = {oid: price_buffer[oid] for oid in chunk_ids}
                        for oid in chunk_ids:
                            if oid in input_marks:
                                batch_marks[oid] = input_marks[oid]
                            else:
                                batch_marks.pop(oid, None)
                        # #11138: each input's frozen DB bound travels WITH this
                        # snapshot. A newer tick during the write and sample below moves
                        # only the live record, never this chunk's (lane1 B1).
                        chunk_bounds = (
                            {
                                oid: held_quotes.bound_for(batch_marks.get(oid))
                                for oid in chunk_ids
                            }
                            if held_quotes is not None else {}
                        )
                    if traced is not None:
                        stage_trace.chunk_write(traced, current_chunk, batch_marks)
                    wrote = await write_chunk(
                        current_chunk, final=final,
                        start_market_publish=start_market_publish,
                    )
                    if traced is not None:
                        stage_trace.chunk_end(traced, wrote)
                    # A proven returned clock already bounds future inputs.
                    # Otherwise start a completed cohort's display work before
                    # the optional sample. So does a lock-held chunk (None):
                    # a held quote already carries its frozen input bound, and
                    # the sample is only for FUTURE inputs; it still finishes
                    # in this chunk (#11525). Failed writes keep their order.
                    write_clock_ready = (
                        held_quotes is not None
                        and getattr(wrote, "clock_owner", None) is held_quotes
                        and getattr(blend_refresher, "held_quotes", None) is held_quotes
                    )
                    clock_needed = held_quotes is not None and not final and not write_clock_ready
                    clock_after_delivery = clock_needed and (bool(wrote) or wrote is None)
                    if clock_needed and not clock_after_delivery:
                        await held_quotes.sample_database_clock(get_task_session)
                    # Only a completed unchanged acknowledgement establishes
                    # continuity. A price/heartbeat write still owes its stamp;
                    # failed/held writes never authorize observation bypass.
                    if (not final and observation_tokens
                            and getattr(wrote, "written_ids", None) is not None):
                        written_events = event_ids_for_outcomes(headline_event_ids, wrote.written_ids)
                        async with buffer_lock:
                            for oid, value in current_chunk.items():
                                eid = headline_event_ids.get(oid)
                                token = observation_tokens.get(oid)
                                if (eid in getattr(blend_refresher, "preview_events", ())
                                        and eid not in written_events and token is not None
                                        and token == observation_continuity.get(oid)
                                        and routing_generation == observation_generation):
                                    catalog_boundary.observation_ack[oid] = token
                                    entry = (eid, value, chunk_bounds.get(oid), batch_marks.get(oid),
                                             token, observation_generation)
                                    catalog_boundary.observation_pending.setdefault(oid, entry)
                                    catalog_boundary.observation_wake.set()
                    # #11138: None is a price row a lock holds (refused, timed
                    # out or cooling down). Each event whose speaking legs here
                    # all carry their received quote is stamped from
                    # `held_quotes` now rather than after the holder lets go;
                    # its rows stay buffered and retried exactly as before.
                    # Only a changed quote is owed again, so a long hold costs
                    # no stamp per flush.
                    held_ready: list[int] = []
                    if wrote is None and not final and held_quotes is not None:
                        async with buffer_lock:
                            legs_of: dict[int, list[int]] = {}
                            for oid in current_chunk:
                                event_id = headline_event_ids.get(oid)
                                if event_id is not None:
                                    legs_of.setdefault(event_id, []).append(oid)
                            quotes = {}
                            for oids in legs_of.values():
                                marks = [batch_marks.get(oid) for oid in oids]
                                if all(
                                    getattr(mark, "probability", None) == current_chunk[oid]
                                    and chunk_bounds.get(oid) is not None
                                    and oid not in withdraw_buffer
                                    for oid, mark in zip(oids, marks)
                                ):
                                    quotes.update(
                                        (oid, (current_chunk[oid], chunk_bounds[oid]))
                                        for oid in oids
                                    )
                        # #10090: an event with a leg whose stored row is
                        # already at or after its bound is not held: its stamp
                        # could only republish the stored row, and the event
                        # fence would keep this write out until it returned.
                        # Like a quote with no bound, its row is retried at the
                        # next flush and stamped once written. Unknown keeps
                        # the hold. Read outside the buffer lock.
                        ambiguous = (
                            await held_quotes.stored_at_or_after(get_task_session, quotes)
                            if quotes else set()
                        )
                        async with buffer_lock:
                            for oids in legs_of.values():
                                if quotes.keys().isdisjoint(oids):
                                    continue
                                refused = bool(ambiguous) and not ambiguous.isdisjoint(oids)
                                if refused:
                                    # An older held quote must not outlive the newer input.
                                    held_quotes.release(oids)
                                # Whole event or none: a withdrawal that arrived
                                # during the read drops every leg, as above.
                                if refused or any(oid in withdraw_buffer for oid in oids):
                                    for oid in oids:
                                        quotes.pop(oid, None)
                            moved = event_ids_for_outcomes(
                                headline_event_ids, held_quotes.hold(quotes),
                            )
                        held_ready = [
                            oid for oid in quotes
                            if headline_event_ids.get(oid) in moved
                        ]
                    # A wide book can arrive during the earlier write or this
                    # one. It must mature/hold this event before its fresh stamp.
                    async with buffer_lock:
                        withdraw_cohort_ids.update(withdraw_buffer)
                        withdraw_events = event_ids_for_outcomes(
                            event_id_by_outcome, withdraw_buffer,
                        )
                        # #10090: the STAMP waits only for a withdrawal on a leg
                        # the blend reads. A venue-refuted (non-speaking) leg
                        # cannot move the reading, and a busy game's props are
                        # rarely without a fresh wide book (the v5647 specimen's
                        # game drew 5,589 refused venue messages in one minute).
                        # Held on every leg, a committed WIN price stayed owed
                        # while each flush's withdrawal drew another book (local
                        # replay: 8 flushes, never stamped). Withdrawal maturity
                        # still waits on every leg (`withdraw_events`).
                        speaking_withdrawals = event_ids_for_outcomes(
                            headline_event_ids, withdraw_buffer,
                        )
                    if wrote:
                        unfinished_price_ids.difference_update(chunk_ids)
                        owed.extend(getattr(wrote, "written_ids", chunk_ids))
                    else:
                        if wrote is False:
                            wrote_all = False
                        else:
                            lock_deferred_events.update(
                                event_ids_for_outcomes(event_id_by_outcome, chunk_ids)
                            )
                        failed_price_events.update(
                            event_ids_for_outcomes(event_id_by_outcome, chunk_ids)
                        )
                    if held_ready:
                        # Withdrawals still wait for the row (failed above).
                        unfinished_price_ids.difference_update(held_ready)
                        owed.extend(oid for oid in held_ready if oid not in owed)
                    # #10651: finish this event's withdrawals once all of its
                    # planned price writes have completed successfully. An
                    # unrelated later chunk must not delay its coherent blend
                    # publication.
                    mature = {
                        eid
                        for eid in withdraw_events - attempted_withdraw_events
                        if last_price_chunk_of_event.get(eid, len(chunks)) <= index
                        and eid not in failed_price_events
                        and eid not in fenced_events
                        and eid not in catalog_boundary.bridges.reserved
                        and eid not in bridge_waiting
                    }
                    if mature:
                        # Withdrawals retain their existing order after a
                        # preceding stamp that reads them, including implicit
                        # debt it admitted (`join_stamp_reading`).
                        attempted_withdraw_events.update(mature)
                        early_withdrawn = await flush_withdrawals(
                            only_events=mature, final=final,
                            background_publish=flush_started is not None and not final,
                            props=None if final else False,
                            before_write=join_stamp_reading,
                        )
                        if early_withdrawn is None:
                            wrote_all = False  # retain the ordinary tail fallback
                        else:
                            owed.extend(
                                oid for oid in early_withdrawn if oid not in owed
                            )
                            withdraw_events.difference_update(mature)
                            speaking_withdrawals.difference_update(mature)
                            async with buffer_lock:
                                withdraw_cohort_ids.update(withdraw_buffer)
                                still = withdraw_cohort_ids.intersection(withdraw_buffer)
                                withdraw_events.update(
                                    event_ids_for_outcomes(event_id_by_outcome, still)
                                )
                                speaking_withdrawals.update(
                                    event_ids_for_outcomes(headline_event_ids, still)
                                )
                    ready: list[int] = []
                    held: list[int] = []
                    for oid in owed:
                        event_id = headline_event_ids.get(oid)
                        done = event_id is None or (
                            last_chunk_of_event.get(event_id, index) <= index
                            and event_id not in speaking_withdrawals
                        )
                        (ready if done else held).append(oid)
                    owed = held
                    if ready:
                        # Q460 — THE SHIP: carry the committed prices through to
                        # `Event.win_probability_sources`, the JSONB the card
                        # renders. #837 receipt: the revisions these writes
                        # committed ride into this refresh, and only this one.
                        refresh_events = event_ids_for_outcomes(
                            headline_event_ids, ready,
                        )
                        writing_events = (
                            event_ids_for_outcomes(headline_event_ids, unfinished_price_ids)
                            | catalog_boundary.bridges.unstamped
                        )
                        unfinished_events = writing_events | speaking_withdrawals
                        # #10090 `owed_past_withdrawal`: deferred only by a
                        # buffered withdrawal no write has started.
                        withdrawing = speaking_withdrawals - writing_events
                        extra = {"withdrawing_event_ids": withdrawing} if withdrawing else {}
                        if stamp_owner.task is not None and not stamp_owner.task.done():
                            # A committed whole cohort in this or a later flush may use
                            # the running owner's free worker. Its marks travel
                            # directly; never overwrite that call's staging slot.
                            admitted = blend_refresher.admit_fresh(
                                refresh_events, flush_started=flush_started,
                                marks=[batch_marks[oid] for oid in ready
                                       if oid in batch_marks
                                       and oid not in headline_event_ids.non_speakers],
                                defer_event_ids=unfinished_events,
                                **extra,
                            )
                            stamp_owner.fresh.update(admitted)
                            if stamp_owner.events is not None:
                                stamp_owner.events.update(admitted)
                            # A leg no stamp reads (a prop's price or
                            # withdrawal) owes no call beside the running one;
                            # quiet debt is the tail's.
                            ready = [oid for oid in ready
                                     if headline_event_ids.get(oid) not in admitted
                                     and headline_event_ids.get(oid) is not None]
                            refresh_events.difference_update(admitted)
                            if not ready:
                                if clock_after_delivery:
                                    await held_quotes.sample_database_clock(get_task_session)
                                continue
                            admitting = getattr(blend_refresher, "admitting", None)
                            keep_owed = getattr(blend_refresher, "keep_owed", None)
                            if admitting is not None and keep_owed is not None and admitting():
                                # #10090: refused while the call still admits —
                                # the same event's stamp is queued or running, or
                                # this flush is still writing its cohort. Joining
                                # waited out the WHOLE call for a stamp only its
                                # own return allows. Kept owed instead; a later
                                # flush's admission stamps it (`window.debt`).
                                keep_owed(
                                    refresh_events,
                                    marks=[batch_marks[oid] for oid in ready
                                           if oid in batch_marks
                                           and oid not in headline_event_ids.non_speakers],
                                )
                                if clock_after_delivery:
                                    await held_quotes.sample_database_clock(get_task_session)
                                continue
                        # Refused by a call that no longer admits (it is ending):
                        # the previous joined path. No second mutable refresher
                        # call runs beside it. Preserve clock recovery before
                        # an older stamp that must be joined can hold this cohort.
                        if (clock_after_delivery and stamp_owner.task is not None
                                and not stamp_owner.task.done()):
                            await held_quotes.sample_database_clock(get_task_session)
                            clock_after_delivery = False
                        await stamp_done()
                        tail_receipts.stage(
                            [batch_marks[oid] for oid in ready if oid in batch_marks
                             and oid not in headline_event_ids.non_speakers]
                        )
                        # Capture BEFORE refresh consumes due debt and starts
                        # awaiting its database read; querying it later can miss
                        # the very in-flight cohort that needs the exclusion.
                        owed_now = owed_beside(unfinished_events, withdrawing)
                        stamp_owner.events = (
                            None if owed_now is None
                            else (refresh_events - unfinished_events) | owed_now
                        )
                        stamp_owner.fresh = set(refresh_events)
                        stamp_owner.task = asyncio.create_task(blend_refresher.refresh(
                            refresh_events, flush_started=flush_started,
                            defer_event_ids=unfinished_events,
                            **extra,
                        ))
                        # One turn of the loop: the refresh takes this chunk's
                        # staged receipts and asks for its connection before
                        # the next write.
                        await asyncio.sleep(0)
                    if clock_after_delivery:
                        await held_quotes.sample_database_clock(get_task_session)
            except asyncio.CancelledError:
                # A recycle mid-batch cancels the persistent owner and joins
                # it before this interrupted batch ends. The refresher's cancellation path keeps
                # a stamp cancelled before its COMMIT owed for the hand-off.
                try:
                    await stamp_done(cancel=True)
                finally:
                    await market_publish_done(cancel=True)
                raise
            finally:
                try:
                    # Ordinary batches leave the sole owner running so the
                    # next unrelated batch can COMMIT and join its free slot.
                    # The final drain MUST join stamps it itself starts.
                    if final or flush_started is None:
                        await stamp_done()
                finally:
                    if final or flush_started is None:
                        await market_publish_done()
        # Keep isolation beyond cooldown expiry until every failed price row
        # has committed. A newer quote on a successful row may batch normally.
        lock_retry_events.intersection_update(
            event_ids_for_outcomes(event_id_by_outcome, lock_retry_until)
        )
        # #9934: after the prices, so a held number is judged as it now stands.
        # Events already attempted above wait for the next flush if their
        # withdrawal failed or a newer book arrived during the transaction.
        # All other withdrawals retain their ordinary after-price ordering.
        withdrawn = await flush_withdrawals(
            # A withdrawal on the held cohort would immediately reacquire its
            # blocked outcome locks and bypass the price eligibility cooldown.
            # A fenced event's prices are still buffered: its withdrawal waits too.
            exclude_events=(
                attempted_withdraw_events | lock_deferred_events | fenced_events
                | catalog_boundary.bridges.reserved | bridge_waiting
            ),
            standalone=None if final else False,
            props=None if final else False,
            final=final,
            background_publish=flush_started is not None and not final,
            before_write=join_stamp_reading,
        )
        if withdrawn is None:
            wrote_all = False
            withdrawn = []
        # Only a withdrawn leg the blend reads owes a stamp; a prop-only
        # withdrawal takes the quiet path and never joins a running owner.
        withdrawn_events = event_ids_for_outcomes(headline_event_ids, withdrawn)
        async with buffer_lock:
            withdraw_cohort_ids.update(withdraw_buffer)
            writing_events = (
                event_ids_for_outcomes(headline_event_ids, unfinished_price_ids)
                | catalog_boundary.bridges.unstamped
            )
            buffered_withdrawals = event_ids_for_outcomes(
                headline_event_ids,
                withdraw_cohort_ids.intersection(withdraw_buffer),
            )
            unfinished_events = writing_events | buffered_withdrawals
        # #10090 `owed_past_withdrawal`: deferred only by a buffered withdrawal
        # this flush has not started writing (its withdrawal pass is over).
        withdrawing = buffered_withdrawals - writing_events
        extra = {"withdrawing_event_ids": withdrawing} if withdrawing else {}
        if not batch and not withdrawn_events and not owed:
            # #837 tail — a flush with no new prices still owes the stamps a row
            # lock deferred: those prices are already stored, so waiting for the
            # next venue tick would strand them on a quiet market. Free when
            # nothing is queued (no session is opened).
            owed_now = owed_beside(unfinished_events, withdrawing)
            if owed_now:
                note_flush_work()
            if stamp_owner.task is not None:
                # Do not overlap a second refresh with the active owner. If
                # nothing else is owed, this quiet batch has no work to join.
                if owed_now is not None and not owed_now:
                    return wrote_all
                if not final and flush_started is not None and not stamp_owner.task.done():
                    # #10090: joining the running call here held this flush, and
                    # every later one, behind the slowest stamp in it. While it
                    # admits, its door takes the oldest due debt (`window.debt`);
                    # otherwise the first flush after it returns stamps the debt.
                    admit = getattr(blend_refresher, "admit_fresh", None)
                    if admit is not None:
                        admit((), flush_started=flush_started,
                              defer_event_ids=unfinished_events, **extra)
                    return wrote_all
                await stamp_owner.join()
            await refresh_owed(unfinished_events, withdrawing)
            return wrote_all
        if not owed and not withdrawn_events:
            # A cohort excluded from an earlier chunk's stamp may now be
            # complete even when it contributed no additional ready inputs.
            owed_now = owed_beside(unfinished_events, withdrawing)
            if owed_now:
                note_flush_work()
            if stamp_owner.task is not None:
                # Do not overlap a second refresh with the active owner. If
                # nothing else is owed, this quiet batch has no work to join.
                if owed_now is not None and not owed_now:
                    return wrote_all
                if not final and flush_started is not None and not stamp_owner.task.done():
                    # #10090: joining the running call here held this flush, and
                    # every later one, behind the slowest stamp in it. While it
                    # admits, its door takes the oldest due debt (`window.debt`);
                    # otherwise the first flush after it returns stamps the debt.
                    admit = getattr(blend_refresher, "admit_fresh", None)
                    if admit is not None:
                        admit((), flush_started=flush_started,
                              defer_event_ids=unfinished_events, **extra)
                    return wrote_all
                await stamp_owner.join()
            await refresh_owed(unfinished_events, withdrawing)
            return wrote_all
        # The prices held for a withdrawal, and the withdrawal itself: one
        # refresh, never a second for an event the chunks already refreshed.
        tail_events = event_ids_for_outcomes(headline_event_ids, owed) | withdrawn_events
        if (
            not final and flush_started is not None
            and stamp_owner.task is not None and not stamp_owner.task.done()
        ):
            # #10090: a committed tail cohort takes a free worker of the running
            # call, exactly as a chunk's ready cohort does, instead of joining
            # the WHOLE call and then stamping inline. A held or refused event
            # keeps the joined path below.
            admitted = blend_refresher.admit_fresh(
                tail_events, flush_started=flush_started,
                marks=[batch_marks[oid] for oid in owed if oid in batch_marks
                       and oid not in headline_event_ids.non_speakers],
                defer_event_ids=unfinished_events,
                **extra,
            )
            stamp_owner.fresh.update(admitted)
            if stamp_owner.events is not None:
                stamp_owner.events.update(admitted)
            owed = [oid for oid in owed if headline_event_ids.get(oid) not in admitted]
            tail_events.difference_update(admitted)
            if not tail_events:
                return wrote_all
            admitting = getattr(blend_refresher, "admitting", None)
            if tail_events <= unfinished_events or (admitting is not None and admitting()):
                # #10090: every refused event is still being written by this
                # flush (a newer book or price arrived for it), so the joined
                # `refresh` below could only defer it — or the call still
                # admits, so a later flush's admission stamps it once its own
                # stamp has returned. Joining waited out the WHOLE running call
                # for no earlier stamp — behind a held stamp, 1.4 s in which no
                # later flush ran. Same debt, no join.
                keep_owed = getattr(blend_refresher, "keep_owed", None)
                if keep_owed is not None:
                    keep_owed(
                        tail_events,
                        marks=[batch_marks[oid] for oid in owed if oid in batch_marks
                               and oid not in headline_event_ids.non_speakers],
                    )
                    return wrote_all
        await stamp_owner.join()
        if owed:
            tail_receipts.stage(
                [batch_marks[oid] for oid in owed if oid in batch_marks
                 and oid not in headline_event_ids.non_speakers]
            )
        await blend_refresher.refresh(
            tail_events,
            flush_started=flush_started,
            defer_event_ids=unfinished_events,
            **extra,
        )
        return wrote_all

    async def _flush_standalone(flush_started=None):
        """#10090: write the standalone open legs, then their withdrawals.

        Their own loop, so a standalone chunk's UPDATE no longer holds the next
        game flush (the game loop starts a flush only when the last returns).
        These legs have no event, so nothing here refreshes a blend or stages a
        receipt. Same chunk plan, cap and buffer bookkeeping as the game flush;
        the two loops write disjoint rows. ``flush_started`` is unused.
        """
        async with buffer_lock:
            alone = standalone_open_outcome_ids(
                price_buffer, open_outcome_ids, event_id_by_outcome,
                open_complement_of,
            )
            batch = {oid: p for oid, p in price_buffer.items() if oid in alone}
        wrote_all = True
        if batch:
            chunks = plan_flush_chunks(
                batch,
                open_outcome_ids,
                FLUSH_CHUNK_ROWS,
                OPEN_FLUSH_CHUNKS_PER_FLUSH,
                open_complement_of,
            )
            stats["open_contract_flush_deferred"] += len(batch) - sum(
                len(c) for c in chunks
            )
            for chunk_ids in chunks:
                async with catalog_boundary.side_writer:
                    wrote = await write_chunk({oid: batch[oid] for oid in chunk_ids})
                if wrote is False:
                    wrote_all = False
        async with catalog_boundary.side_writer:
            withdrawn = await flush_withdrawals(standalone=True, background_publish=True)
        if withdrawn is None:
            wrote_all = False
        return wrote_all

    async def _flush_props(flush_started=None):
        """#10090: write the linked props no blend reads, then their withdrawals.

        Their own loop, as the standalone legs': the game flush appended these
        chunks after every game's, and the cadence starts no flush until the
        last returns, so one slow prop transaction held the next game quote
        though that game's own stamp had released (Root's held-tail rig:
        0.60 s held, 0.25 s unheld; stage trace 43011 waited 4.67 s at that
        boundary, its occupant unknown). A prop's price owes no
        stamp, so nothing here refreshes a blend or stages a receipt. The game
        flush's prop planning is unchanged: uncapped, complement pairs whole,
        a lock-refused cohort retried apart; each chunk adopts the newest
        buffered values. Withdrawals follow their own prices, never a stamp,
        and skip an event whose prop write a lock just refused. Disjoint rows
        from the other loops; one side transaction at a time (`side_writer`).
        ``flush_started`` is unused.
        """
        from app.tasks.polymarket_ws import _pm_lock_isolated_chunks

        async with buffer_lock:
            alone = standalone_open_outcome_ids(
                price_buffer, open_outcome_ids, event_id_by_outcome,
                open_complement_of,
            )
            batch = [
                oid for oid in price_buffer
                if oid in non_blend_outcome_ids and oid not in alone
            ]
            if batch or set(withdraw_buffer) & non_blend_outcome_ids:
                catalog_boundary.prop_work += 1
        wrote_all = True
        lock_deferred_events: set[int] = set()
        if batch:
            chunks = _pm_lock_isolated_chunks(
                plan_flush_chunks(
                    batch, set(), FLUSH_CHUNK_ROWS, None, open_complement_of,
                ),
                lock_retry_events, event_id_by_outcome,
                market_by_outcome, open_complement_of, FLUSH_CHUNK_ROWS,
            )
            for chunk_ids in chunks:
                async with catalog_boundary.side_writer:
                    async with buffer_lock:
                        chunk = {
                            oid: price_buffer[oid]
                            for oid in chunk_ids if oid in price_buffer
                        }
                    wrote = await write_chunk(chunk) if chunk else True
                if wrote is False:
                    wrote_all = False
                elif wrote is None:
                    lock_deferred_events.update(
                        event_ids_for_outcomes(event_id_by_outcome, chunk)
                    )
        async with catalog_boundary.side_writer:
            withdrawn = await flush_withdrawals(
                standalone=False, props=True, exclude_events=lock_deferred_events,
                background_publish=True,
            )
        if withdrawn is None:
            wrote_all = False
        return wrote_all

    async def flush_observations():
        """Admit frozen unchanged inputs beside an unrelated price transaction."""
        boundary = catalog_boundary

        def owners():
            owner = boundary.stamp_owner(blend_refresher)
            held = (owner.held_events()
                    if owner.task is not None and not owner.task.done() else set())
            if held is None:
                return None
            pending_reader = getattr(blend_refresher, "pending_event_ids", None)
            pending = set(pending_reader()) if callable(pending_reader) else set()
            # PM buffers unchanged BBOs too. Only acknowledged uninterrupted
            # values may pass; another leg's queued change owns the whole event
            # even before its price chunk starts (including A-B-A).
            price_owned = {
                event_id_by_outcome.get(oid) for oid, value in price_buffer.items()
                if oid not in non_blend_outcome_ids
                and (observation_continuity.get(oid) is None
                     or boundary.observation_ack.get(oid) != observation_continuity[oid]
                     or observation_continuity[oid][1] != round(float(value), 6))
            }
            return (held | pending | price_owned | boundary.observation_writing
                    | boundary.bridges.reserved | boundary.bridges.unstamped
                    | event_ids_for_outcomes(event_id_by_outcome, withdraw_buffer))

        async with buffer_lock:
            busy = owners()
            if busy is None:
                return
            snapshot = {oid: entry for oid, entry in boundary.observation_pending.items()
                        if entry[0] not in busy}
            if not snapshot:
                return
            for oid in snapshot:
                boundary.observation_pending.pop(oid)
            window = getattr(blend_refresher, "_admission", None)
            releases = {entry[0]: window.released.get(entry[0], 0) if window else 0
                        for entry in snapshot.values()}
            epochs = {entry[0]: boundary.observation_write_epoch.get(entry[0], 0)
                      for entry in snapshot.values()}
        boundary.flush_work += 1
        groups = {}
        for oid, (eid, value, bound, mark, _token, _generation) in snapshot.items():
            groups.setdefault(eid, {})[oid] = (value, bound, mark)

        async def validate(event_ids):
            async with buffer_lock:
                busy = owners()
                if busy is None or getattr(blend_refresher, "_admission", None) is not window:
                    return set()
                return {
                    eid for eid in event_ids
                    if eid not in busy and eid in getattr(blend_refresher, "preview_events", ())
                    and boundary.observation_write_epoch.get(eid, 0) == epochs[eid]
                    and (window is None or window.released.get(eid, 0) == releases[eid])
                    and all(
                        event_id_by_outcome.get(oid) == eid
                        and oid not in non_blend_outcome_ids and oid not in open_outcome_ids
                        and generation == routing_generation
                        and token == observation_continuity.get(oid)
                        and token == boundary.observation_ack.get(oid)
                        and mark is not None and bound is not None
                        and getattr(mark, "probability", None) == value
                        and input_marks.get(oid) is not None
                        and round(float(input_marks[oid].probability), 6) == round(float(value), 6)
                        and getattr(input_marks[oid], "seq", -1) >= getattr(mark, "seq", 0)
                        for oid, (event, value, bound, mark, token, generation) in snapshot.items()
                        if event == eid
                    )
                }

        async def restore():
            async with buffer_lock:
                for oid, entry in snapshot.items():
                    boundary.observation_pending.setdefault(oid, entry)
                boundary.observation_wake.set()

        try:
            accepted = await blend_refresher.preview_accepted_observations(groups, validate)
        except asyncio.CancelledError:
            await restore()
            raise
        if accepted is False:
            await restore()
            return
        held = getattr(blend_refresher, "held_quotes", None)
        if held is not None and any(entry[2] == getattr(held, "_database_bound", None)
                                    for entry in snapshot.values()):
            # Advance bounds for FUTURE arrivals only. Never re-date retries.
            await held.sample_database_clock(get_task_session)

    async def flush_prices(flush_started=None, final=False):
        # The joined pump cannot outlive the catalog/routing scope or final drain.
        async with catalog_boundary.flushing(standalone=final):
            if (final or not getattr(blend_refresher, "preview_events", ())
                    or not callable(getattr(blend_refresher, "preview_accepted_observations", None))):
                return await _flush_prices(flush_started, final=final)
            from app.tasks.ws_observation_drain import ObservationDrain
            if catalog_boundary.observation_drain is None:
                catalog_boundary.observation_drain = ObservationDrain(
                    flush_observations, lambda: any(
                        entry[0] not in catalog_boundary.observation_writing
                        for entry in catalog_boundary.observation_pending.values()
                    ),
                    catalog_boundary.observation_wake, game_period,
                )
            async def work():
                try:
                    return await _flush_prices(flush_started, final=final)
                finally:
                    catalog_boundary.observation_writing.clear()
                    catalog_boundary.observation_wake.set()
            return await catalog_boundary.observation_drain.run_with(work)

    async def flush_standalone(flush_started=None):
        async with catalog_boundary.flushing(standalone=True):
            return await _flush_standalone(flush_started)

    async def flush_props(flush_started=None):
        # A side flush: the handover fences it first, as the standalone loop.
        async with catalog_boundary.flushing(standalone=True):
            return await _flush_props(flush_started)

    async def drain_prices():
        """The LAST flush of this consumer's life — retry, never requeue.

        Q491 repair (CERT-654 BLOCK), twin of the Kalshi socket's. `flush_prices`
        hands a failed batch back to `price_buffer` so the next periodic flush
        retries it. At recycle and at shutdown there IS no next flush, so that
        requeue is a silent drop — the certifier's exact-head probe read
        `writes=[]`, `errors=1`, `requeued=1`. Call `flush_prices` again instead,
        up to `FINAL_FLUSH_ATTEMPTS`, each attempt on a fresh session.
        """
        try:
            for attempt in range(FINAL_FLUSH_ATTEMPTS):
                # #9484: no successor flush, so no open-contract bound either.
                await flush_prices(final=True)
                async with buffer_lock:
                    if not price_buffer:
                        return
                if attempt + 1 < FINAL_FLUSH_ATTEMPTS:
                    stats["final_flush_retries"] += 1
        except asyncio.CancelledError:
            # Q491 repair 2: a hard cancel during the LAST drain. The
            # cancellation must keep travelling (CERT-491 — swallowing it makes
            # the runner relaunch a consumer the process is stopping), but the
            # prices it strands must be REPORTED on the way out rather than
            # vanishing at the silent `errors=0, requeued=0` CERT-659 measured.
            stranded = len(price_buffer)
            if stranded:
                stats["final_flush_dropped"] += stranded
                logger.error(
                    "Polymarket WS: %d price updates STRANDED by cancellation "
                    "during the final drain — these are lost, not deferred",
                    stranded,
                )
            raise
        async with buffer_lock:
            stranded = len(price_buffer)
        if stranded:
            # Loud: this is the one place a price genuinely cannot be retried
            # again, so it must never be inferable only from a silence.
            stats["final_flush_dropped"] += stranded
            logger.error(
                "Polymarket WS: %d price updates STRANDED after %d final-flush "
                "attempts — these are lost, not deferred",
                stranded, FINAL_FLUSH_ATTEMPTS,
            )

    async def join_flushes_then_drain():
        """#10090: producers and every cancelled flush loop finish, then the
        persistent event-stamp owner joins, before the final drain reads the
        buffer. Stamps launched by that drain join before handoff too.

        A cancelled write can still be rolling back, committing or publishing;
        draining beside it would capture the same buffer and write it again,
        and put two refreshes in the refresher. Live's c686 join (Kalshi):
        joined to COMPLETION, never to a timeout, with an error line each bound
        a loop overruns; `loops_stop` and the flushes' own DB bounds end them.
        A second cancellation landing on the join is recorded, not obeyed
        early: the join and the drain both still run, then it propagates.
        """
        flushes = {flush_task, standalone_task, prop_task, admission_task, game_run_task}
        flushes.update(resolution_tasks)
        if open_run_task is not None:
            flushes.add(open_run_task)
        interrupted = None
        while not all(task.done() for task in flushes):
            try:
                await asyncio.wait(flushes, timeout=LOOP_REAP_TIMEOUT_S)
            except asyncio.CancelledError as exc:
                interrupted = exc
                continue
            running = sorted(t.get_name() for t in flushes if not t.done())
            if running:
                logger.error(
                    "Polymarket WS: cancelled producer/flush %s still running after "
                    "%.0fs; the final drain waits for it",
                    ", ".join(running), LOOP_REAP_TIMEOUT_S,
                )
        try:
            try:
                # #10090: the bridged writer too, to completion (its write is
                # bounded by the lock budget). No game flush is left to start
                # another, and its committed cohorts become debt for the drain.
                await catalog_boundary.bridges.join()
            except asyncio.CancelledError as exc:
                interrupted = exc
            catalog_boundary.bridges.transfer(blend_refresher)
            try:
                await catalog_boundary.join_stamps()
            except asyncio.CancelledError as exc:
                # Joined to completion; repeated cancellation cannot skip the
                # final price drain after that owner has relinquished sessions.
                interrupted = exc
            await drain_prices()
        finally:
            try:
                await catalog_boundary.join_stamps()
            finally:
                try:
                    debt = getattr(blend_refresher, "withdrawal_debt", None)
                    if debt is not None:
                        await debt.join_publications(cancel=True)
                finally:
                    try:
                        market_owner = getattr(blend_refresher, "withdrawal_market_publisher", None)
                        if market_owner is not None:
                            await market_owner.join(cancel=True)
                    finally:
                        if interrupted is not None:
                            raise interrupted

    # #9418: one CLOB client for the consumer's resolutions, made on first use
    # and closed with the consumer; and the in-flight resolution tasks, held so
    # a running settle is not garbage-collected and can be cancelled at exit.
    resolution_tasks: set = set()
    _resolution_service: list = []

    def resolution_service():
        if not _resolution_service:
            from app.services.polymarket_api import PolymarketAPIService

            _resolution_service.append(PolymarketAPIService())
        return _resolution_service[0]

    async def handle_price(msg: dict):
        """Handle best_bid_ask event."""
        asset_id = msg.get("asset_id", "")
        input_generation = routing_generation
        # #9484: a game-slate token, else an open contract's (never both —
        # the open map excludes every token the game socket carries).
        market_id = asset_to_market.get(asset_id) or open_asset_to_market.get(
            asset_id
        )
        if not market_id and asset_id not in open_asset_mirrors:
            return
        _note_raw(asset_id)

        best_bid = msg.get("best_bid")
        best_ask = msg.get("best_ask")
        if best_bid is None or best_ask is None:
            return

        try:
            bid_f = float(best_bid)
            ask_f = float(best_ask)
        except (ValueError, TypeError):
            return

        # #9913: kept before the width test below, because a wide book is the
        # one `handle_trade` needs to see.
        latest = books_by_asset.get(asset_id, (None,))[0]
        if latest != (bid_f, ask_f):
            books_by_asset[asset_id] = ((bid_f, ask_f), latest)

        # #1578: never stream a midpoint from a book nobody will trade inside.
        # This path matters most of the five, because it is the only one that
        # UPDATEs an outcome directly rather than going through the upsert — a
        # wide quote arriving here would overwrite a good stored price with a
        # phantom. Returning early leaves the existing value untouched; the
        # real-trade stream (handle_trade, below) is what moves an illiquid
        # market's price, which is correct.
        #
        # #9934: but the book is still evidence about the price we HOLD. A
        # held number the wide book prices out is queued for withdrawal.
        legs = books_with_complements(
            _tick_targets(asset_id), bid_f, ask_f, open_complement_of
        )
        if _poly_book_is_untradeable(bid_f, ask_f):
            async with buffer_lock:
                if input_generation != routing_generation:
                    return
                for outcome_id, leg_bid, leg_ask in legs:
                    withdraw_buffer[outcome_id] = (leg_bid, leg_ask)
                    if getattr(blend_refresher, "preview_events", ()):
                        observation_continuity.pop(outcome_id, None)
                    # #10090 decision J: a book that prices a published leg
                    # out is a pending change; re-judge agreement now.
                    confirmed = getattr(tail_receipts, "confirmed", None)
                    if confirmed is not None:
                        with contextlib.suppress(Exception):
                            confirmed.note_withdrawal(
                                event_id_by_outcome.get(outcome_id), outcome_id)
                # #11138: a held quote never outlives a book that withdraws it.
                held_quotes = getattr(blend_refresher, "held_quotes", None)
                if held_quotes is not None:
                    held_quotes.release(oid for oid, _bid, _ask in legs)
                wake_outcomes = getattr(catalog_boundary, "wake_for_outcomes", None)
                if wake_outcomes is not None:
                    wake_outcomes(
                        (oid for oid, _bid, _ask in legs),
                        open_outcome_ids,
                        event_id_by_outcome,
                        non_blend_outcome_ids,
                    )
                elif any(
                    oid not in open_outcome_ids or event_id_by_outcome.get(oid) is not None
                    for oid, _bid, _ask in legs
                ):
                    catalog_boundary.flush_wake.set()
            return
        if legs:
            async with buffer_lock:
                if input_generation != routing_generation:
                    return
                for outcome_id, _bid, _ask in legs:
                    withdraw_buffer.pop(outcome_id, None)

        prob = (bid_f + ask_f) / 2
        if prob <= 0 or prob >= 1:
            return

        # Q489: the outcome this ASSET is the book for — not "the market's first
        # outcome". `prob` here is the midpoint of THIS token's own book, so on
        # the No token it is P(No), which belongs on the No leg and nowhere else.
        targets = _tick_targets(asset_id)
        if not targets:
            return

        async with buffer_lock:
            if input_generation != routing_generation:
                return
            priced = with_complements(targets, prob, open_complement_of)
            for outcome_id, leg_prob in priced:
                price_buffer[outcome_id] = leg_prob
                _mark_input(outcome_id, leg_prob, "price", msg)
            wake_outcomes = getattr(catalog_boundary, "wake_for_outcomes", None)
            if wake_outcomes is not None:
                wake_outcomes(
                    (oid for oid, _prob in priced),
                    open_outcome_ids,
                    event_id_by_outcome,
                    non_blend_outcome_ids,
                )
            elif any(
                oid not in open_outcome_ids or event_id_by_outcome.get(oid) is not None
                for oid, _prob in priced
            ):
                catalog_boundary.flush_wake.set()

    def _tick_targets(asset_id: str) -> list[int]:
        """Every leg a tick in this token prices: its owner, then its mirrors.

        #9736: a token two markets name (the NLDS board's Cubs leg and the
        standalone Cubs binary) is subscribed once; both legs are the same
        contract, so both take its price."""
        targets = []
        owner = asset_to_outcome.get(asset_id)
        if owner is None:
            owner = open_asset_to_outcome.get(asset_id)
        if owner is not None:
            targets.append(owner)
        targets.extend(
            oid for oid, _mid in open_asset_mirrors.get(asset_id, ())
            if oid != owner
        )
        return targets

    def _note_raw(asset_id):
        # #10090 — one venue message for each game this token prices, counted
        # before the price policy decides; never raises into the socket.
        try:
            for event_id in {
                event_id_by_outcome.get(oid) for oid in _tick_targets(asset_id)
            }:
                tail_receipts.note_raw(event_id)
        except Exception:
            return

    def _mark_input(outcome_id, prob, kind, msg):
        # Under `buffer_lock`, so seq order is buffer order. Never raises into
        # the socket: a receipt is evidence about the price, not the price.
        try:
            mark = tail_receipts.note_input(
                event_id_by_outcome.get(outcome_id), outcome_id, prob, kind,
                msg.get("timestamp"),
            )
        except Exception:
            return
        # #10090 decision J: a blend leg's input — a slate leg or a BRIDGED
        # open leg, mixed events included (lane1 R1) — judged for agreement
        # with what this source published. A bridged leg the map names no
        # event for travels with its binary partner's (`_pm_pure_bridged_legs`):
        # the blend reads both legs of the market. Bookkeeping only.
        confirmed = getattr(tail_receipts, "confirmed", None)
        if confirmed is not None and outcome_id not in non_blend_outcome_ids:
            with contextlib.suppress(Exception):
                if mark is not None:
                    confirmed.note_mark(mark)
                elif outcome_id in open_outcome_ids:
                    from app.tasks.live_blend_refresh import _wall

                    partner_event = event_id_by_outcome.get(open_complement_of.get(outcome_id))
                    if partner_event is not None:
                        confirmed.note_input(partner_event, outcome_id, prob, _wall())
        if mark is not None:
            if (event_id_by_outcome.get(outcome_id) in getattr(blend_refresher, "preview_events", ())
                    and outcome_id not in non_blend_outcome_ids and outcome_id not in open_outcome_ids):
                price = round(float(prob), 6)
                previous = observation_continuity.get(outcome_id)
                if previous is None or previous[1] != price:
                    observation_continuity[outcome_id] = (object(), price)
            elif getattr(blend_refresher, "preview_events", ()):
                observation_continuity.pop(outcome_id, None)
            input_marks[outcome_id] = mark
            held = getattr(blend_refresher, "held_quotes", None)
            if held is not None:
                held.note_input(mark)
            token = observation_continuity.get(outcome_id)
            if token is not None and catalog_boundary.observation_ack.get(outcome_id) == token:
                catalog_boundary.observation_pending[outcome_id] = (
                    event_id_by_outcome.get(outcome_id), prob,
                    held.bound_for(mark) if held is not None else None,
                    mark, token, routing_generation,
                )
                catalog_boundary.observation_wake.set()
            else:
                catalog_boundary.observation_pending.pop(outcome_id, None)
            stage_trace = getattr(tail_receipts, "exact_trace", None)
            if stage_trace is not None:
                stage_trace.input_accepted(mark)  # never raises

    async def handle_trade(msg: dict):
        """Handle last_trade_price event."""
        asset_id = msg.get("asset_id", "")
        input_generation = routing_generation
        # #9484: a game-slate token, else an open contract's (never both —
        # the open map excludes every token the game socket carries).
        market_id = asset_to_market.get(asset_id) or open_asset_to_market.get(
            asset_id
        )
        if not market_id and asset_id not in open_asset_mirrors:
            return
        _note_raw(asset_id)

        price = msg.get("price")
        if price is None:
            return
        try:
            prob = float(price)
        except (ValueError, TypeError):
            return
        if prob <= 0 or prob >= 1:
            return

        # Q489: same contract as `handle_price` — a `last_trade_price` is a trade
        # in THIS token, so it grades THIS token's leg.
        targets = _tick_targets(asset_id)
        if not targets:
            return

        # #9733: a leftover smaller than any order the venue accepts is not a
        # price. Counted, so a refusal is a number and not an absence.
        if not trade_sets_a_price(msg):
            stats["trades_below_min_order"] += 1
            return

        # #9913: nor is a trade that swept past the edge of a wide book. The
        # leg keeps the last price a book supported.
        if trade_prints_outside_wide_book(prob, books_by_asset.get(asset_id, ())):
            stats["trades_outside_wide_book"] += 1
            return

        async with buffer_lock:
            if input_generation != routing_generation:
                return
            priced = with_complements(targets, prob, open_complement_of)
            for outcome_id, leg_prob in priced:
                price_buffer[outcome_id] = leg_prob
                _mark_input(outcome_id, leg_prob, "trade", msg)
            wake_outcomes = getattr(catalog_boundary, "wake_for_outcomes", None)
            if wake_outcomes is not None:
                wake_outcomes(
                    (oid for oid, _prob in priced),
                    open_outcome_ids,
                    event_id_by_outcome,
                    non_blend_outcome_ids,
                )
            elif any(
                oid not in open_outcome_ids or event_id_by_outcome.get(oid) is not None
                for oid, _prob in priced
            ):
                catalog_boundary.flush_wake.set()
        stats["trade_updates"] += 1

    async def handle_resolved(msg: dict):
        """Handle market_resolved event.

        Sets status=resolved and is_winner, routed through the resolution-authority
        contract. Queue #261 Item 2: this path NEVER copies the last buffered
        trade into ``calibration_probability`` — a terminal price must not both
        define the winner AND grade the earlier/current forecast (self-grading
        leakage, C20/C21). The terminal price still reaches ``current_probability``
        through the ordinary buffered flush loop, and the published calibration
        forecast is left to the timestamped snapshot pipeline (opening/closing
        lines). An outcome already settled by an authoritative source (tier 3) is
        left untouched — a bare websocket push must not downgrade it.

        #9418: the winner is the leg owning the CLOB-confirmed winning TOKEN
        (:func:`ws_resolution_verdict`), never the push's label. The CLOB read is
        a network call, so it runs as its own task: the shard's reader is the
        caller here, and a slow venue must not hold up the price frames behind
        this one.
        """
        condition_id = msg.get("market", "")
        market_id = condition_to_market.get(condition_id)
        if not market_id:
            return
        task = asyncio.create_task(_settle_resolution(
            msg, condition_id, market_id,
            list(outcomes_by_market.get(market_id, [])), dict(asset_to_outcome),
        ))
        resolution_tasks.add(task)
        task.add_done_callback(resolution_tasks.discard)

    async def _ask_venue(winning_asset_id, condition_id: str, outcomes, token_owners):
        """One confirmation attempt: CLOB first, then Gamma when CLOB has not
        decided (#9418 after-check — CLOB lags the push by minutes, Gamma
        does not). Either read failing is an `unconfirmed` answer, not an error.
        """
        outcome_ids = [oid for oid, _ in outcomes]
        clob_market = None
        try:
            clob_market = await asyncio.wait_for(
                resolution_service().get_clob_market_by_condition(condition_id),
                timeout=RESOLUTION_CLOB_TIMEOUT_S,
            )
        except Exception:
            logger.warning(
                "Polymarket WS: CLOB read for %s failed", condition_id[:20],
                exc_info=True,
            )
        verdict = ws_resolution_verdict(
            winning_asset_id, clob_market, outcome_ids, token_owners
        )
        if verdict[0] != WS_RESOLUTION_UNCONFIRMED:
            return verdict
        try:
            gamma_market = await asyncio.wait_for(
                resolution_service().get_closed_gamma_market_raw(condition_id),
                timeout=RESOLUTION_CLOB_TIMEOUT_S,
            )
        except Exception:
            logger.warning(
                "Polymarket WS: Gamma read for %s failed", condition_id[:20],
                exc_info=True,
            )
            return verdict
        gamma_verdict = gamma_resolution_verdict(
            winning_asset_id, gamma_market, outcome_ids, token_owners
        )
        if gamma_verdict[0] != WS_RESOLUTION_UNCONFIRMED:
            stats["resolutions_via_gamma"] += 1
        return gamma_verdict

    async def _write_resolution(condition_id, market_id, outcomes, verdict, msg):
        try:
            async with get_task_session() as session:
                written = await _apply_ws_resolution(
                    session, market_id, outcomes, verdict
                )
                # #9484: the terminal invalidation carries the `settled_at`
                # this transaction stored, read back inside it — the market is
                # resolved exactly as REST will now serve it.
                settled_at = (
                    await session.execute(
                        select(FuturesMarket.settled_at).where(
                            FuturesMarket.id == market_id,
                            FuturesMarket.status == "resolved",
                        )
                    )
                ).scalar_one_or_none()
                if settled_at is not None:
                    queue_market_change(
                        session,
                        market_id=market_id,
                        source="polymarket",
                        outcome_observed_at={},
                        terminal=True,
                        updated_at=settled_at,
                    )
        finally:
            # #10090 `preview_from_commit`: committed or not, no cached read
            # graph keeps these legs' pre-resolution rows.
            from app.tasks.live_blend_refresh import forget_preview_outcomes

            forget_preview_outcomes(blend_refresher, (oid for oid, _ext in outcomes))
        await blend_refresher.publish_market_changes(session)
        logger.info(
            "Polymarket WS: %s resolved (verdict=%s, label=%s, %d/%d outcomes "
            "written, no calibration scalar captured)",
            condition_id[:20], verdict[0], msg.get("winning_outcome", ""),
            written, len(outcomes),
        )

    async def _settle_resolution(msg: dict, condition_id: str, market_id: int, outcomes, token_owners):
        """Resolve now; grade as soon as the venue confirms the token.

        The market is marked resolved on the FIRST answer whatever it is, so
        a settled market reads settled at once (the pre-existing behaviour).
        If that answer is `unconfirmed`, the venue is asked again on
        :data:`RESOLUTION_RECHECK_DELAYS_S` and the first decided verdict is
        written over it — `settled_at` is COALESCEd, so the second write keeps
        the first time. A recycle that cancels the wait loses only the grade,
        which the Gamma rail then supplies, exactly as before.
        """
        winning_asset_id = msg.get("winning_asset_id")
        async def ask():
            return await _ask_venue(winning_asset_id, condition_id, outcomes, token_owners)

        writes = []

        async def write(verdict):
            await _write_resolution(condition_id, market_id, outcomes, verdict, msg)
            # Counted at the write, not after the re-asks: a recycle cancels
            # the wait, and the resolution it already committed still counts.
            # `resolutions_<kind>` is the FIRST answer, as before #9418's
            # re-ask; a grade written on a re-ask is `resolutions_confirmed_late`.
            if not writes:
                stats["resolutions"] += 1
                stats[f"resolutions_{verdict[0]}"] += 1
            else:
                stats["resolutions_confirmed_late"] += 1
            writes.append(verdict[0])

        try:
            await settle_with_rechecks(ask, write)
        except Exception:
            stats["errors"] += 1
            logger.exception("Polymarket WS: resolution error")

    ws.on_price = handle_price
    ws.on_trade = handle_trade
    ws.on_resolved = handle_resolved

    # #10090: start to start, like the Kalshi socket's; see `run_flush_cadence`.
    # #10657: set before the loop is cancelled, so a cancellation lost inside
    # a flush still ends the loop at its next turn (`run_flush_cadence`).
    loops_stop = asyncio.Event()

    async def flush_loop():
        await run_flush_cadence(
            flush_prices, game_period, stop=loops_stop,
            failed_retry_interval_s=PRICE_FLUSH_SECONDS,
            wake=catalog_boundary.flush_wake,
            work_count=lambda: catalog_boundary.flush_work,
            wake_coalesce_s=PM_WAKE_COALESCE_SECONDS,
        )

    async def standalone_loop():
        await run_flush_cadence(
            flush_standalone, PRICE_FLUSH_SECONDS, stop=loops_stop,
        )

    async def prop_loop():
        # #10090: the game flush's cadence, retry and wake, for linked props.
        await run_flush_cadence(
            flush_props, flush_period, stop=loops_stop,
            failed_retry_interval_s=PRICE_FLUSH_SECONDS,
            wake=catalog_boundary.prop_wake,
            work_count=lambda: catalog_boundary.prop_work,
            wake_coalesce_s=PM_WAKE_COALESCE_SECONDS,
        )

    async def stats_loop():
        while True:
            await asyncio.sleep(60)
            # Q504-b: blend counters ride along, same reasoning as the Kalshi arm.
            blend = blend_refresher.stats
            # #837: the fan-out already counts, on the wire, how many distinct
            # assets each shard was actually served — but nothing read it, so
            # the one number that answers "is the venue serving the whole
            # subscription or a fraction of it" existed only in process memory
            # and no after-check could ever be paid from production. The
            # coverage WARNING beside it fires only when a shard serves
            # literally zero while a sibling streams; a shard served 3 of 500
            # is the same silent-fraction defect and is invisible to it. So the
            # ratio is stated every minute, whether or not anything is wrong.
            ws_stats = ws.stats
            owner = catalog_boundary.stamps
            stats["stamp_wait_s"] = owner.waited_s if owner is not None else 0.0
            _log_stats_line(stats, ws_stats, blend)
            open_connected = any(s.is_connected for s in open_sockets)
            if open_sockets:
                stats.update(catalog_boundary.bridges.take_timing())
                _log_open_contract_line(stats, open_sockets[0].stats)
            _report_liveness(
                "polymarket",
                (
                    "streaming"
                    if getattr(ws, "is_connected", False) or open_connected
                    else "disconnected"
                ),
                legs=len(asset_ids),
                msgs=ws_stats.get("messages", 0),
                served=ws_stats.get("assets_served", 0),
                stamped=blend["stamped"],
                no_reading=blend["no_reading"],
            )

    flush_task = asyncio.create_task(flush_loop(), name="polymarket-flush-loop")
    prop_task = asyncio.create_task(prop_loop(), name="polymarket-prop-flush-loop")
    standalone_task = asyncio.create_task(
        standalone_loop(), name="polymarket-standalone-flush-loop"
    )
    stats_task = asyncio.create_task(stats_loop(), name="polymarket-stats-loop")

    _report_liveness("polymarket", "subscribing", legs=len(asset_ids))

    # #9462 review: the markets this run can actually attribute a tick to. A
    # market the slate SELECTED but whose tokens the top-up could not find is
    # not among them, however many of its event's props are streaming.
    legged_market_ids = {
        asset_to_market[a] for a in asset_to_outcome if a in asset_to_market
    }

    # One callback/buffer/session owner spans routine catalog refreshes. Only
    # changed subscriptions reconnect; unchanged open-contract shards keep
    # their books and receive queues instead of rebuilding the whole fleet.
    async def refresh_catalog(slate, open_read, timing):
        nonlocal open_run_task, routing_generation
        admission, failed, bridge, bridge_failed = open_read
        stats["open_contract_admission_error"] = failed
        stats["open_contract_bridge_error"] = bridge_failed
        fresh_open_markets = (
            {}
            if admission is None
            else {
                oid: admission.asset_to_market[token]
                for token, oid in admission.asset_to_outcome.items()
            }
        )
        if admission is not None:
            fresh_open_markets.update(admission.mirrored_outcomes())
            for key, value in admission.counts.items():
                stats[f"open_contract_{key}"] = value
        async with catalog_boundary.updating(timing):
            timing.enter("lock")
            async with buffer_lock:
                timing.enter("map")
                routing_generation += 1
                observation_continuity.clear()
                catalog_boundary.observation_ack.clear()
                catalog_boundary.observation_pending.clear()
                catalog_boundary.observation_write_epoch.clear()
                # Keep accepted writes' ownership through their drain even if the
                # token has left the catalog. New inputs use ONLY the fresh maps.
                protected = set(price_buffer) | set(withdraw_buffer)
                current_outcomes = (
                    slate["market_by_outcome"].keys() | fresh_open_markets.keys()
                )
                old_debt = protected - current_outcomes
                for owners in (market_by_outcome, event_id_by_outcome):
                    for oid in owners.keys() - old_debt:
                        del owners[oid]
                # #10663: per-outcome bookkeeping keeps only the outcomes this
                # catalog owns or a buffered write still carries. Nothing else
                # retired an entry, so both grew by every outcome the process
                # ever priced. A re-admitted outcome has no last-write instant
                # and is written on its next price (never suppressed); its next
                # accepted input records a fresh mark before any flush reads it.
                retained = current_outcomes | protected
                for bookkeeping in (successful_price_write_at, input_marks):
                    for oid in bookkeeping.keys() - retained:
                        del bookkeeping[oid]
                asset_ids[:] = slate["asset_ids"]
                market_ids.clear()
                market_ids.update(slate["market_ids"])
                for name, target in (
                    ("asset_to_outcome", asset_to_outcome),
                    ("asset_to_market", asset_to_market),
                    ("condition_to_market", condition_to_market),
                    ("event_id_by_market", event_id_by_market),
                    ("outcomes_by_market", outcomes_by_market),
                ):
                    target.clear()
                    target.update(slate[name])
                market_by_outcome.update(slate["market_by_outcome"])
                market_by_outcome.update(fresh_open_markets)
                fresh_events = {
                    oid: event_id_by_market[mid]
                    for oid, mid in slate["market_by_outcome"].items()
                    if mid in event_id_by_market
                }
                event_id_by_outcome.update(bridge)
                event_id_by_outcome.update(fresh_events)
                non_blend_outcome_ids.intersection_update(old_debt)
                non_blend_outcome_ids.update(
                    oid
                    for oid, mid in slate["market_by_outcome"].items()
                    if mid in slate["non_blend_market_ids"]
                )
                open_outcome_ids.intersection_update(old_debt)
                open_outcome_ids.update(fresh_open_markets)
                for target, fresh in (
                    (
                        open_asset_to_market,
                        {} if admission is None else admission.asset_to_market,
                    ),
                    (
                        open_asset_to_outcome,
                        {} if admission is None else admission.asset_to_outcome,
                    ),
                    (
                        open_asset_mirrors,
                        {} if admission is None else admission.asset_mirrors,
                    ),
                ):
                    target.clear()
                    target.update(fresh)
                for oid in open_complement_of.keys() - old_debt:
                    del open_complement_of[oid]
                if admission is not None:
                    open_complement_of.update(admission.complement_of)
                live_assets = (
                    asset_to_outcome.keys()
                    | open_asset_to_outcome.keys()
                    | open_asset_mirrors.keys()
                )
                for token in books_by_asset.keys() - live_assets:
                    del books_by_asset[token]
                for held in (lock_retry_until, withdrawal_retry_until):
                    for oid in held.keys() - protected:
                        del held[oid]
                legged_market_ids.clear()
                legged_market_ids.update(
                    asset_to_market[a] for a in asset_to_outcome if a in asset_to_market
                )
            timing.enter("open")
            stats["assets_subscribed"] = len(asset_ids)
            stats["assets_mapped"] = len(asset_to_outcome)
            stats["assets_unmapped"] = len(slate["unmapped_assets"])
            stats["moneyline_legs_subscribed"] = len(slate["outcome_yes_token"])
            stats["open_contract_bridged_outcomes"] = len(bridge)
            stats["open_contract_bridged_events"] = len(set(bridge.values()))
            stats["open_contract_assets"] = len(open_asset_to_outcome)
            if not open_sockets:
                # #10090: the same client surface, received in a child process.
                open_client = PolymarketWebSocket
                if open_contract_receiver_process_enabled():
                    from app.services.polymarket_ws_process import (
                        PolymarketOpenReceiverProcess as open_client,
                    )
                open_ws = open_client(
                    max_concurrent_handshakes=OPEN_CONTRACT_MAX_CONCURRENT_HANDSHAKES,
                    max_queue=OPEN_CONTRACT_MAX_QUEUE,
                    price_book_snapshots=book_snapshot_prices_enabled(),
                )
                open_ws.on_price = handle_price
                open_ws.on_trade = handle_trade
                open_sockets.append(open_ws)
            open_ws = open_sockets[0]
            # Existing flag is re-read at the same catalog boundary as before.
            snapshot_prices = book_snapshot_prices_enabled()
            desired_open = sorted(open_asset_to_outcome)
            if open_run_task is None or open_run_task.done():
                if open_run_task is not None:
                    await asyncio.gather(open_run_task, return_exceptions=True)
                open_run_task = asyncio.create_task(
                    run_open_client(open_ws, desired_open, snapshot_prices),
                    name="polymarket-open-sockets",
                )
                # Start the owner before allowing an immediate second refresh.
                await asyncio.sleep(0)
            else:
                open_ws.update_asset_ids(
                    desired_open, price_book_snapshots=snapshot_prices
                )

    async def run_open_client(open_ws, desired_open, snapshot_prices):
        try:
            await open_ws.run_refreshable(
                desired_open,
                price_book_snapshots=snapshot_prices,
            )
        except Exception:
            stats["open_contract_admission_error"] = True
            logger.exception("Polymarket WS: open-contract client failed")

    async def read_catalog_open(slate):
        return await read_open_contracts(
            set(slate["asset_ids"]),
            slate["market_ids"],
            tokens_by_contract(
                slate["asset_to_outcome"],
                {
                    oid: ext
                    for pairs in slate["outcomes_by_market"].values()
                    for oid, ext in pairs
                },
            ),
        )

    async def admit_open_contracts():
        nonlocal game_slate
        if complete_startup_slate:
            try:
                started = time.monotonic()
                full_slate = await load_game_slate()
                # No open catalog has been admitted yet. Install the complete
                # game maps before subscribing their new tokens; never make a
                # recovered live token wait for the independent open read.
                await refresh_catalog(
                    full_slate, (None, False, {}, False),
                    _PMCatalogHandoverTiming(
                        "startup-games", slate_read_s=time.monotonic() - started,
                    ),
                )
                ws.update_asset_ids(
                    asset_ids.copy(), preserve_existing_shards=True,
                )
                game_slate = full_slate
            except Exception:
                logger.exception(
                    "Polymarket WS full startup slate failed; retaining stored live subscriptions"
                )
        open_read, open_read_s = preread, None
        if open_read is None:
            started = time.monotonic()
            open_read = await read_catalog_open(game_slate)
            open_read_s = time.monotonic() - started
        await refresh_catalog(
            game_slate,
            open_read,
            _PMCatalogHandoverTiming("initial", open_read_s=open_read_s),
        )

    admission_task = asyncio.create_task(admit_open_contracts())

    # #9418: the slate's live arm, re-read while the socket runs — the slate
    # query above with `_slate_event_window()` narrowed to its live arm, so it
    # can only name an event that turned live after the slate was read.
    # #9462 review: read per MARKET, beside the reading the card renders, so
    # an event counts as subscribed only when the leg that feeds its displayed
    # number is mapped here (`unadmitted_live_events`).
    async def load_unadmitted_live_event_ids():
        async with get_task_session() as session:
            result = await session.execute(
                select(
                    FuturesMarket.event_id,
                    FuturesMarket.id,
                    Event.win_probability_sources["polymarket"],
                )
                .select_from(FuturesOutcome)
                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.event_id.isnot(None),
                    Event.status == "live",
                    _slate_market_filter(),
                )
                .distinct()
            )
            return unadmitted_live_events(result.all(), legged_market_ids)

    def start_game_socket():
        # Reuse the open arm's per-shard owner for game quotes/resolutions.
        # Empty means no subscriptions here, never the legacy all-market run.
        return asyncio.create_task(
            ws.run_refreshable(asset_ids.copy()),
            name="polymarket-game-sockets",
        )

    game_run_task = start_game_socket()
    stop_task = asyncio.create_task(stop.wait()) if stop is not None else None
    watch_task = None
    exit_reason = "consumer_exit"
    try:
        while True:
            cycle_started_at = time.monotonic()
            watch_task = asyncio.create_task(
                watch_for_unadmitted_live_events(
                    load_unadmitted_live_event_ids,
                    event_id_by_market.values(),
                    arm="Polymarket",
                    started_at=run_started_at,
                ),
            )
            done, _ = await asyncio.wait(
                {game_run_task, watch_task}
                | ({stop_task} if stop_task is not None else set()),
                timeout=SUBSCRIPTION_REFRESH_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task is not None and stop_task in done:
                stats["status"] = "stopped"
                exit_reason = "shutdown"
                break
            if game_run_task in done:
                game_run_task.result()
                break
            admitted = None
            if watch_task in done:
                if watch_task.exception() is None:
                    admitted = watch_task.result()
                else:
                    logger.error(
                        "Polymarket WS admission watcher failed; keeping sockets to the timer",
                        exc_info=watch_task.exception(),
                    )
                    remaining = max(
                        0,
                        SUBSCRIPTION_REFRESH_SECONDS
                        - (time.monotonic() - cycle_started_at),
                    )
                    finished, _ = await asyncio.wait(
                        {game_run_task}
                        | ({stop_task} if stop_task is not None else set()),
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if stop_task is not None and stop_task in finished:
                        stats["status"] = "stopped"
                        exit_reason = "shutdown"
                        break
                    if finished:
                        game_run_task.result()
                        break
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
            watch_task = None
            # Loading does not close either client: quotes still reach these
            # same buffers while the database/top-up prepares the next slate.
            await admission_task
            # #10663: the startup slate/pre-read were copied into the live maps;
            # bound here they outlived every refresh as a second catalog.
            game_slate = preread = None
            if not open_asset_to_outcome and not open_asset_mirrors:
                # No open fleet to retain: preserve the game-only runner's
                # existing recycle/debt-handoff contract.
                stats["status"] = "resubscribe"
                if admitted:
                    stats["recycle_reason"] = "admission"
                    stats["admitted_event_ids"] = sorted(admitted)[:20]
                break
            # #10663: drop the previous refresh's source copies before the next
            # read builds one, so a read never overlaps two catalogs plus the maps.
            fresh_slate = fresh_open = None
            try:
                read_started = time.monotonic()
                fresh_slate = await load_game_slate()
                slate_read_s = time.monotonic() - read_started
                read_started = time.monotonic()
                fresh_open = await read_catalog_open(fresh_slate)
                open_read_s = time.monotonic() - read_started
                if fresh_open[1]:
                    stats["open_contract_admission_error"] = True
                    logger.warning(
                        "Polymarket WS open admission failed; retaining the current catalog"
                    )
                    run_started_at = time.monotonic()
                    continue
            except Exception:
                logger.exception(
                    "Polymarket WS catalog refresh failed; keeping subscriptions"
                )
                run_started_at = time.monotonic()
                continue
            # Install new callback ownership before subscribing new tokens.
            # The existing refreshable owner changes only affected shards, so
            # unrelated live games keep their connections, books and coverage.
            await refresh_catalog(
                fresh_slate,
                fresh_open,
                _PMCatalogHandoverTiming(
                    "admission" if admitted else "timer",
                    slate_read_s=slate_read_s,
                    open_read_s=open_read_s,
                ),
            )
            # Installed: the live maps own the catalog now.
            fresh_slate = fresh_open = None
            # #11218: the reads' freed working set goes back to the OS now,
            # instead of staying counted until the dyno's memory line.
            release_free_heap("polymarket")
            if game_run_task.done():
                # Loading/updating can yield while the retained client exits.
                # Propagate its failure (or end this run) just as the wait above.
                game_run_task.result()
                break
            ws.update_asset_ids(asset_ids.copy())
            run_started_at = time.monotonic()
            stats["catalog_refreshes"] = stats.get("catalog_refreshes", 0) + 1
            stats["recycle_reason"] = "admission" if admitted else "timer"
            if admitted:
                stats["admitted_event_ids"] = sorted(admitted)[:20]
            logger.info(
                "Polymarket WS refreshed game slate (%s); open catalog retained: %d assets",
                stats["recycle_reason"], len(open_asset_to_outcome),
            )
    except asyncio.CancelledError:
        # Real shutdown, not the planned recycle (CERT-491) — keep it travelling
        # so the runner stops instead of relaunching. Buffer still drains below.
        exit_reason = "shutdown"
        raise
    finally:
        loops_stop.set()
        flush_task.cancel()
        standalone_task.cancel()
        prop_task.cancel()
        stats_task.cancel()
        # #9418: an unfinished settle rolls back; the market stays for the
        # Gamma rail, which is where an `unconfirmed` verdict leaves it anyway.
        for task in list(resolution_tasks):
            task.cancel()
        # #9484: cancelled here, awaited only after the drain below, so a
        # second cancellation landing on that await can never skip the drain.
        admission_task.cancel()
        game_run_task.cancel()
        if watch_task is not None:
            watch_task.cancel()
        if stop_task is not None:
            stop_task.cancel()
        if open_run_task is not None:
            open_run_task.cancel()
        # Q491 repair (CERT-654 BLOCK): the last flush has no successor, so it
        # must RETRY rather than requeue into a buffer nobody will read again.
        # #10090 review: only after both cancelled flushes have finished.
        history_interrupted = None
        try:
            await join_flushes_then_drain()
        finally:
            # #9462 review: the drain returns once the price BUFFER is empty,
            # but a price it (or the last flush) committed inside the 2 s
            # throttle is still owed its blend stamp. The next run adopts it.
            try:
                drain_history = getattr(blend_refresher, "drain_history", None)
                if drain_history is not None:
                    await drain_history()
            except asyncio.CancelledError as exc:
                history_interrupted = exc
            finally:
                stats["history_pending_carried"] = len(getattr(blend_refresher, "_history", ()))
                stats["blend_pending_carried"] = hand_off_pending(blend_refresher)
            await asyncio.gather(
                admission_task, game_run_task,
                *([watch_task] if watch_task is not None else []),
                *([stop_task] if stop_task is not None else []),
                *([open_run_task] if open_run_task is not None else []),
                return_exceptions=True,
            )
            # #10657: a loop that lost its cancellation ends here, after the
            # drain, rather than outliving the run on its closed sessions.
            stats["loops_unreaped"] = await reap_stopped_loops(
                "polymarket", (flush_task, standalone_task, prop_task, stats_task),
            )
            # #9418: closed after the drain, never before it, so a cancellation
            # landing on this await cannot skip a flush.
            if _resolution_service:
                with contextlib.suppress(Exception):
                    await _resolution_service[0].close()
            # #837 receipt — the next run's refresher starts empty of chains,
            # so a held price still open here was never stamped by this run.
            # Said so; the stamp itself is carried above.
            with contextlib.suppress(Exception):
                tail_receipts.close_all(
                    "recycle_reset" if stats.get("status") == "resubscribe"
                    else exit_reason
                )
            if history_interrupted is not None:
                raise history_interrupted

    # #837: the per-shard breakdown, once per recycle rather than once a minute
    # — this is the shape that tells a starved subscription from a quiet one.
    # `run()`'s teardown clears the CONNECTED sets but deliberately not the
    # served ones, so the cycle's coverage is still readable here; `shards_
    # connected` is not, and is left out rather than logged as a misleading 0.
    exit_stats = ws.stats
    stats["assets_served"] = exit_stats.get("assets_served", 0)
    stats["served_by_shard"] = exit_stats.get("served_by_shard", {})
    stats["subscribed_by_shard"] = exit_stats.get("subscribed_by_shard", {})
    stats["unserved_by_shard"] = exit_stats.get("unserved_by_shard", {})
    # PER SHARD, because that is the resolution the excess was found at: the
    # minute line's fleet total would have read 394 over a 375 shard as a few
    # ids across eight shards and nothing would have stood out. `2:394/375`
    # stood out precisely because one shard crossed its own denominator.
    stats["on_wire_by_shard"] = exit_stats.get("on_wire_by_shard", {})
    _log_unserved_sample(ws)
    if open_sockets:
        open_exit = open_sockets[0].stats
        stats["open_contract_shards"] = open_exit.get("shards", 0)
        stats["open_contract_assets_served"] = open_exit.get("assets_served", 0)
        stats["open_contract_messages"] = open_exit.get("messages", 0)
    logger.info("Polymarket WS consumer exiting: %s", stats)
    return stats


async def _run_polymarket_ws_shadow_consumer():
    """#837 fast-follow (SHADOW): widened resolution-only grader that records
    its verdict to Redis (NEVER is_winner). Subscribes to ALL markets'
    resolution pushes (not the price firehose) so every Polymarket settlement
    is graded in real time — into the shadow store, for the automated
    source-agnostic comparison (`compare_shadow_verdicts`).

    Runs ONLY when the `bainluck:ws_shadow_enabled` flag is on (deploy-dark).
    The authoritative `_run_polymarket_ws_consumer` is untouched and keeps
    owning `is_winner`.
    """
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.services.ws_shadow import (
        is_ws_shadow_enabled,
        verdict_from_polymarket_resolved,
        record_shadow_verdict,
    )

    if not await is_ws_shadow_enabled():
        return {"status": "shadow_disabled"}

    ws = PolymarketWebSocket()
    stats = {"shadow_verdicts": 0, "errors": 0}

    async def handle_resolved_shadow(msg: dict):
        parsed = verdict_from_polymarket_resolved(msg)
        if not parsed:
            return
        # SHADOW ONLY — record BOTH outcome verdicts, keyed by each outcome's
        # external_id ({condition_id}_yes / {condition_id}_no). The comparison
        # joins FuturesOutcome.external_id == key exactly, source-agnostic.
        for ext_id, is_winner in parsed:
            try:
                await record_shadow_verdict(ext_id, is_winner)
                stats["shadow_verdicts"] += 1
            except Exception:
                stats["errors"] += 1

    ws.on_resolved = handle_resolved_shadow
    # resolution-only + all markets: NO asset_ids -> subscribe to all; the
    # service only dispatches market_resolved here (on_price/on_trade unset),
    # so this is the settlement trickle, NOT the price firehose.
    try:
        await ws.run()
    except asyncio.CancelledError:
        raise  # shutdown must stop the runner, not restart it (CERT-491)
    logger.info("Polymarket WS SHADOW consumer exiting: %s", stats)
    return stats
