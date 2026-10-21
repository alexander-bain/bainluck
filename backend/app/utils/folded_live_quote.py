"""Compact authoritative detail quote, shared across recipients of one update."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import json

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Event
from app.services.database import async_session_maker
from app.utils.aggregation import newest_source_reading_time
from app.utils.draw_priced_winner import printable_away
from app.utils.hero_probability import hero_sportsbook_count, resolve_hero
from app.utils.kalshi_occurrence_start import loaded_sport_key
from app.utils.lifecycle import served_event_status
from app.utils.price_evidence import load_price_evidence
from app.utils.probability_source_format import format_probability_sources
from app.utils.proven_duplicates import FoldedBlendView, folded_probability_state
from app.utils.folded_blend_preview import FoldedPreviewBase, QuoteWithPreviewBase
from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

logger = logging.getLogger(__name__)

PROJECTION_TIMEOUT_S = 1.0
MAX_PENDING = 8
# Recovery reads (`fresh=True`, only from `project_recovery_quote`) may hold at
# most one of the two load slots and half the pending entries, so a failing
# recovery cohort can never refuse or queue ordinary readers out of both.
# A recovery read refused only by that share waits, within its own request
# deadline, for a recovery entry to leave; admitted and waiting recovery reads
# together never exceed MAX_PENDING. A waiter holds no slot, entry or load.
RECOVERY_MAX_SLOTS = 1
RECOVERY_MAX_PENDING = 4
MAX_CACHED = 64
RECOVERY_RETRY_S = 0.25
RECOVERY_MAX_RETRY_S = 0.5
RECOVERY_PROBE_S = 0.2


async def load_folded_quote(event_id: int, origin_id: int, origin_rev: int):
    """Reuse detail's read-only fold and probability policy, without its page IO."""
    async with async_session_maker() as db:
        event = (await db.execute(
            select(Event).options(selectinload(Event.sport)).where(Event.id == event_id)
        )).scalar_one_or_none()
        if event is None:
            return None
        absorbed = await serve_fold_absorbed_rows(db, event)
        sources, owners, revision = await folded_probability_state(db, event, absorbed)
        if (revision is None or str(event_id) not in revision
                or revision.get(str(origin_id), -1) < origin_rev):
            return None
        view = FoldedBlendView(event, sources)
        hero = resolve_hero(view)
        sport = loaded_sport_key(event)
        observed_at = (
            newest_source_reading_time(view, require_complete=True)
            if hero is not None and hero.source == "blend" else None
        )
        public_sources = format_probability_sources(sources)
        pm = public_sources.get("polymarket")
        if isinstance(pm, dict):
            # Exactly the detail rail's durable price evidence, never venue IO.
            pm["price_evidence"] = await load_price_evidence(db, sources.get("polymarket"))
        away = None if hero is None else hero.away_probability
        if hero is not None and hero.source != "settled":
            away = printable_away(away, hero.home_probability, sport)
        quote = {
            "event_id": event_id,
            "hero_probability": None if hero is None else hero.home_probability,
            "hero_probability_away": away,
            "hero_probability_source": None if hero is None else hero.source,
            "hero_probability_observed_at": None if observed_at is None else observed_at.isoformat(),
            "blend_fold_revision": revision,
            "win_probability_sources": public_sources,
            "hero_sportsbook_count": (
                hero_sportsbook_count(view)
                if hero is not None and hero.source == "blend" else None
            ),
            "hero_settled_result": None if hero is None else hero.settled_result,
            "status": served_event_status(event.status, event.commence_time, datetime.now(timezone.utc)),
            "sport": sport,
        }
        # Shared legacy formatting accepts numeric shapes; transport authority
        # additionally needs valid JSON numbers, without changing detail policy.
        json.dumps(quote, allow_nan=False)
        return QuoteWithPreviewBase(
            quote, FoldedPreviewBase.capture(event, sources, owners, revision, sport),
        )


@dataclass
class _RecoveryRetry:
    failures: int
    after: float
    earliest: float
    opened_at: float | None = None
    spent: bool = False


@dataclass
class _Work:
    task: asyncio.Task
    waiters: int = 0
    deadline: float = float("inf")  # the creating request's; the load ends by it


class FoldedQuoteProjector:
    """Bounded per-process coalescing, with no subscription or ingestion policy."""

    def __init__(self):
        self._pending = {}
        self._cached = OrderedDict()
        self._preview_bases = OrderedDict()
        self._recovery_retry_after = OrderedDict()
        self._slots = asyncio.Semaphore(2)
        self._recovery_slots = asyncio.Semaphore(RECOVERY_MAX_SLOTS)
        self._recovery_released = asyncio.Event()
        self._recovery_waiting = 0
        self._first_load_at = None
        self._last_success_at = None
        self._last_load_started_at = float("-inf")

    def project_preview(self, event_id, frame, *, members, floors, elapsed_ms=0):
        base = self._preview_bases.get(event_id)
        if base is None:
            return None
        self._preview_bases.move_to_end(event_id)
        return base.project(frame, members=members, floors=floors, elapsed_ms=elapsed_ms)

    def forget_preview_base(self, event_id):
        self._preview_bases.pop(event_id, None)

    def _dark(self, now):
        since = self._last_success_at
        if since is None:
            since = self._first_load_at
        return since is not None and now - since >= RECOVERY_RETRY_S

    async def _load(self, event_id, origin_id, revision, fresh, deadline):
        quote = None
        load_started = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout_at(deadline):
                async with self._recovery_slots if fresh else nullcontext(), self._slots:
                    load_started = asyncio.get_running_loop().time()
                    quote = await load_folded_quote(event_id, origin_id, revision)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("folded quote unavailable for event %s", event_id, exc_info=True)
        now = asyncio.get_running_loop().time()
        # Record once per actual load, not once per coalesced reader.
        if quote is not None:
            base = getattr(quote, "preview_base", None)
            if base is not None:
                held_base = self._preview_bases.get(event_id)
                # A slow older read cannot replace a dominating base. Changed
                # membership requires a new stream's exact membership check.
                if (held_base is None or (
                        set(base.revision) == set(held_base.revision)
                        and all(base.revision[key] >= value
                                for key, value in held_base.revision.items()))):
                    self._preview_bases[event_id] = base
                    self._preview_bases.move_to_end(event_id)
                    while len(self._preview_bases) > MAX_CACHED:
                        self._preview_bases.popitem(last=False)
            if self._dark(now):
                for retry in self._recovery_retry_after.values():
                    if not retry.spent:
                        retry.after = retry.earliest
                        retry.opened_at = now
            self._last_success_at = now
            self._recovery_retry_after.pop(event_id, None)
        elif fresh:
            previous = self._recovery_retry_after.get(event_id)
            failures = min(4, (previous.failures if previous else 0) + 1)
            delay = min(RECOVERY_MAX_RETRY_S, RECOVERY_RETRY_S * 2 ** (failures - 1))
            spent = previous is not None and (previous.spent or (
                previous.opened_at is not None and load_started >= previous.opened_at))
            after = now + delay
            if (previous is not None and previous.opened_at is not None
                    and not spent and load_started < previous.opened_at):
                after = previous.after
            self._recovery_retry_after[event_id] = _RecoveryRetry(
                failures, after, now + RECOVERY_RETRY_S,
                previous.opened_at if previous else None, spent)
            self._recovery_retry_after.move_to_end(event_id)
            while len(self._recovery_retry_after) > MAX_CACHED:
                self._recovery_retry_after.popitem(last=False)
        return quote

    async def project(self, event_id: int, frame: dict, *, fresh: bool = False):
        origin_id, revision = frame.get("event_id"), frame.get("rev")
        if (type(origin_id) is not int or not isinstance(revision, dict)
                or set(revision) != {str(origin_id)}
                or type(revision[str(origin_id)]) is not int
                or revision[str(origin_id)] < 0):
            return None
        if any(frame.get(field) is not None and not isinstance(frame[field], str)
               for field in ("status", "updated_at")):
            return None
        key = (event_id, origin_id, revision[str(origin_id)],
               frame.get("status"), frame.get("updated_at"), fresh)
        # The request's deadline covers any wait for a recovery entry and the load.
        deadline = asyncio.get_running_loop().time() + PROJECTION_TIMEOUT_S
        while True:
            # Every admission rule is re-read after a wait, at its own time.
            now = asyncio.get_running_loop().time()
            retry = self._recovery_retry_after.get(event_id)
            if fresh and retry is not None and retry.after > now:
                # One process-wide probe can detect restoration while all event
                # backoffs are closed. Healthy traffic prevents this bypass.
                probe = (not retry.spent and now >= retry.earliest and self._dark(now) and not self._pending
                         and now - self._last_load_started_at >= RECOVERY_PROBE_S)
                if not probe:
                    return None
            if not fresh and key in self._cached:
                self._cached.move_to_end(key)
                return self._cached[key]
            work = self._pending.get(key)
            if work is not None and work.task.cancelling():
                return None  # departing last waiter still owns bounded cleanup
            if work is not None:
                break
            if len(self._pending) >= MAX_PENDING:
                return None
            # Pending counts queued, active and still-cancelling work alike.
            recovering = sum(1 for pending in self._pending if pending[-1]) if fresh else 0
            if recovering < RECOVERY_MAX_PENDING:
                break
            if recovering + self._recovery_waiting >= MAX_PENDING:
                return None
            # Taken with no await since the count, so a release cannot fall between.
            released = self._recovery_released
            self._recovery_waiting += 1
            try:
                async with asyncio.timeout_at(deadline):
                    await released.wait()
            except TimeoutError:
                return None  # never loaded: no failure, spend or load start recorded
            finally:
                self._recovery_waiting -= 1
        if work is None:
            if self._first_load_at is None:
                self._first_load_at = now
            self._last_load_started_at = now
            work = _Work(asyncio.create_task(
                self._load(event_id, origin_id, revision[str(origin_id)], fresh, deadline)),
                deadline=deadline)
            self._pending[key] = work
        work.waiters += 1
        try:
            if deadline < work.deadline:
                # Only a reader that waited can join work begun after it arrived,
                # bounded by a later request's deadline; it still leaves by its own.
                try:
                    async with asyncio.timeout_at(deadline):
                        quote = await asyncio.shield(work.task)
                except TimeoutError:
                    return None
            else:
                quote = await asyncio.shield(work.task)
            if quote is not None and not fresh:
                self._cached[key] = quote
                self._cached.move_to_end(key)
                while len(self._cached) > MAX_CACHED:
                    self._cached.popitem(last=False)
            return quote
        finally:
            work.waiters -= 1
            if work.waiters == 0:
                # One departing reader cannot cancel another's shared read.
                # The last one joins cleanup, even through repeated cancellation.
                if not work.task.done():
                    work.task.cancel()
                while not work.task.done():
                    try:
                        await asyncio.wait({work.task})
                    except asyncio.CancelledError:
                        continue
                if not work.task.cancelled():
                    work.task.exception()
                self._pending.pop(key, None)
                if fresh:
                    # Wake every current waiter; each re-reads admission itself.
                    self._recovery_released.set()
                    self._recovery_released = asyncio.Event()
